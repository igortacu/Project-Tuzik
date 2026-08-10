"""Telegram bot front-end for query_pipeline.answer_query.

Long-polling only (the bot process reaches out to Telegram, nothing needs to
be publicly reachable) -- no server, no webhook, no FastAPI. Restricted to an
allow-listed set of Telegram user ids (config.TELEGRAM_ALLOWED_USER_IDS)
since anyone who finds the bot's username could otherwise message it.
"""

import asyncio
import logging
import re
import threading
from datetime import datetime
from pathlib import Path

import requests
from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from second_brain import config
from second_brain.agent import vault_writer
from second_brain.agent.reminders import get_reminder_store
from second_brain.bot.memory import ConversationMemory, SaveBuffer
from second_brain.generation.conversation_summarizer import (
    SUMMARIZER_SYSTEM_PROMPT,
    build_summarizer_prompt,
    is_nothing_to_save,
)
from second_brain.generation.llm_client import LLMClient
from second_brain.generation.speech_to_text import SpeechToTextError, transcribe_audio
from second_brain.ingestion.watcher import ChangeType, FileChanged, VaultWatcher
from second_brain.pipelines import index_pipeline, query_pipeline

logger = logging.getLogger(__name__)

_MAX_MESSAGE_LENGTH = 4000  # Telegram's hard cap is 4096; leave some margin
_TELEGRAM_TOKEN_IN_URL_RE = re.compile(r"bot\d+:[^/\s]+")

# Matches the marker the model can put in its reply to trigger a sticker --
# see config.STICKERS and config.SYSTEM_PROMPT.
_STICKER_MARKER_RE = re.compile(r"\[\[sticker:(\w+)\]\]")

# In-process only, per chat -- cleared on restart. See bot/memory.py.
_memory = ConversationMemory(config.CONVERSATION_HISTORY_TURNS)

# Unbounded per-chat accumulation, drained by the periodic save job below.
# Separate from _memory (which is a bounded window for LLM context) --
# this is raw material for the periodic vault save, not conversational
# context, and it must survive being drained without truncation.
_save_buffer = SaveBuffer()

# Own LLMClient instance, separate from query_pipeline's -- summarization is
# a distinct task with its own system prompt and its own rate-limit-streak
# state, not a chat reply.
_summarizer_llm_client = LLMClient()

_START_MESSAGE = (
    f"Hey, I'm *{config.ASSISTANT_NAME}* — {config.OWNER_NAME}'s personal second brain "
    "on legs. Ask me anything about your notes and I'll dig it up (with receipts)."
)


def _redact_telegram_tokens(value):
    if isinstance(value, str):
        text = value
    else:
        text = str(value)
    if "bot" in text:
        return _TELEGRAM_TOKEN_IN_URL_RE.sub("bot[REDACTED]", text)
    return value


class _TelegramTokenRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact_telegram_tokens(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(_redact_telegram_tokens(arg) for arg in record.args)
        elif isinstance(record.args, dict):
            record.args = {key: _redact_telegram_tokens(value) for key, value in record.args.items()}
        return True


def _install_log_redaction() -> None:
    redaction_filter = _TelegramTokenRedactionFilter()
    for logger_name in ("httpx", "telegram", "telegram.ext", __name__):
        logging.getLogger(logger_name).addFilter(redaction_filter)


def _is_authorized(user_id: int) -> bool:
    return user_id in config.TELEGRAM_ALLOWED_USER_IDS


async def _reject_if_unauthorized(update: Update) -> bool:
    """True (and replies) if the sender isn't authorized. Every handler that
    can produce a reply must call this first -- there's no other gate.
    """
    user_id = update.effective_user.id
    if _is_authorized(user_id):
        return False
    await update.message.reply_text(
        f"Not authorized. Your Telegram user id is {user_id} -- add it to "
        "TELEGRAM_ALLOWED_USER_IDS in .env to use this bot."
    )
    return True


async def _reply_in_chunks(update: Update, text: str) -> None:
    for start in range(0, len(text), _MAX_MESSAGE_LENGTH):
        chunk = text[start : start + _MAX_MESSAGE_LENGTH]
        try:
            await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)
        except BadRequest:
            # The model's Markdown wasn't valid Telegram Markdown (unmatched
            # * or _, etc.) -- fall back to plain text rather than dropping
            # the answer.
            await update.message.reply_text(chunk)


def _strip_sticker_marker(text: str) -> tuple[str, str | None]:
    """Splits a raw model reply into (visible_text, sticker_category).
    sticker_category is None if the reply had no [[sticker:CATEGORY]] marker.
    """
    match = _STICKER_MARKER_RE.search(text)
    remaining_text = re.sub(r"[ \t]{2,}", " ", _STICKER_MARKER_RE.sub("", text)).strip()
    return remaining_text, (match.group(1) if match else None)


async def _reply_with_possible_sticker(
    update: Update, remaining_text: str, sticker_category: str | None
) -> None:
    if remaining_text:
        await _reply_in_chunks(update, remaining_text)

    if sticker_category is None:
        return

    file_id = config.STICKERS.get(sticker_category)
    if file_id:
        await update.message.reply_sticker(file_id)
    else:
        logger.warning("Model requested unknown sticker category: %r", sticker_category)


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _reject_if_unauthorized(update):
        return
    await update.message.reply_text(_START_MESSAGE, parse_mode=ParseMode.MARKDOWN)


async def _answer_message(update: Update, question: str) -> None:
    chat_id = update.effective_chat.id
    await update.message.chat.send_action(ChatAction.TYPING)

    try:
        result = await asyncio.to_thread(
            query_pipeline.answer_query,
            question,
            history=_memory.get(chat_id),
            chat_id=chat_id,
        )
    except Exception:
        logger.exception("answer_query failed for question: %r", question)
        await update.message.reply_text("Something went wrong answering that -- check the logs.")
        return

    remaining_text, sticker_category = _strip_sticker_marker(result.text)
    await _reply_with_possible_sticker(update, remaining_text, sticker_category)
    for image_url in result.image_urls:
        try:
            await update.message.reply_photo(photo=image_url)
        except BadRequest:
            logger.warning("Failed to send image from web search: %s", image_url)

    final_text = remaining_text or result.text
    _memory.append(chat_id, question, final_text)
    _save_buffer.append(chat_id, question, final_text)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _reject_if_unauthorized(update):
        return

    question = update.message.text
    await _answer_message(update, question)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _reject_if_unauthorized(update):
        return

    voice = update.message.voice
    if voice.file_size and voice.file_size > config.VOICE_TRANSCRIPTION_MAX_BYTES:
        await update.message.reply_text("Voice message is too large to transcribe.")
        return

    await update.message.chat.send_action(ChatAction.TYPING)
    try:
        telegram_file = await voice.get_file()
        audio_bytes = bytes(await telegram_file.download_as_bytearray())
        question = await asyncio.to_thread(transcribe_audio, audio_bytes, "telegram-voice.ogg")
    except SpeechToTextError as exc:
        logger.warning("voice transcription failed: %s", exc)
        await update.message.reply_text(f"Voice transcription isn't available right now: {exc}")
        return
    except Exception:
        logger.exception("failed to download/transcribe voice message")
        await update.message.reply_text("Something went wrong transcribing that voice message.")
        return

    await _answer_message(update, question)


def _warn_if_model_unknown() -> None:
    """Best-effort startup check: a typo'd/removed OPENROUTER_MODEL_ID (e.g.
    a 404, not a 429) fails every single query with no fallback -- catch it
    here so it's obvious at startup instead of buried in query error logs.
    Never blocks startup: skips silently if the check itself fails.
    """
    try:
        response = requests.get("https://openrouter.ai/api/v1/models", timeout=10)
        response.raise_for_status()
        known_ids = {m["id"] for m in response.json()["data"]}
    except requests.RequestException:
        return

    if config.OPENROUTER_MODEL_ID.strip() not in known_ids:
        logger.warning(
            "config.OPENROUTER_MODEL_ID=%r was not found in OpenRouter's current "
            "model list -- every query will fail until this is fixed. Check "
            "https://openrouter.ai/models for a valid model id.",
            config.OPENROUTER_MODEL_ID,
        )


def _on_vault_change(change: FileChanged) -> None:
    """Re-indexes a note after an edit made outside the bot (e.g. directly in
    Obsidian). Runs on the watcher's own background thread, not the bot's
    event loop -- index_pipeline calls are blocking, that's fine here.
    """
    try:
        if change.event_type == ChangeType.DELETED:
            index_pipeline.delete_file(change.path)
        else:
            index_pipeline.index_file(change.path, change.raw_text)
        logger.info(
            "Re-indexed external vault change: %s (%s)", change.path, change.event_type.value
        )
    except Exception:
        logger.exception("Failed to re-index vault change: %s", change.path)


def _start_vault_watcher() -> None:
    """Watches the vault for changes made outside the bot (editing a note
    directly in Obsidian, deleting one, etc.) so they're picked up live
    instead of only on the next `second_brain index` run. Runs in a daemon
    thread -- doesn't block startup or prevent the process from exiting.
    """
    if not config.VAULT_PATH:
        logger.warning("OBSIDIAN_VAULT_PATH not set -- not watching for external vault changes.")
        return
    watcher = VaultWatcher(Path(config.VAULT_PATH))
    thread = threading.Thread(target=watcher.watch, args=(_on_vault_change,), daemon=True)
    thread.start()
    logger.info("Watching vault for external changes: %s", config.VAULT_PATH)


async def _compress_and_save_chat(chat_id: int, turns: list[tuple[str, str]]) -> None:
    prompt = build_summarizer_prompt(turns)
    compressed = await asyncio.to_thread(
        _summarizer_llm_client.generate, prompt, system_prompt=SUMMARIZER_SYSTEM_PROMPT
    )

    if is_nothing_to_save(compressed):
        logger.info(
            "Periodic save: nothing worth saving for chat_id=%s (%d turns)", chat_id, len(turns)
        )
        return

    filename = f"conversation_{chat_id}.md"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    content = f"## {timestamp}\n\n{compressed.strip()}"
    path = await asyncio.to_thread(vault_writer.append_note, filename, content)
    logger.info("Periodic save: wrote %d turns to %s", len(turns), path)


async def periodic_save_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Runs every config.PERIODIC_SAVE_INTERVAL_SECONDS. Drains each chat's
    SaveBuffer and compresses+saves it -- chats with nothing buffered (no
    new messages since the last run) are skipped entirely: no save, no
    empty note.
    """
    for chat_id in list(_save_buffer.chat_ids()):
        turns = _save_buffer.drain(chat_id)
        if not turns:
            continue
        try:
            await _compress_and_save_chat(chat_id, turns)
        except Exception:
            logger.exception("Periodic save failed for chat_id=%s", chat_id)


async def reminder_dispatch_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Runs every config.REMINDER_DISPATCH_INTERVAL_SECONDS. Sends and
    removes any reminder whose fire_at has passed. A send failure leaves
    the reminder in place for the next tick to retry, rather than losing
    it -- same "late is fine, lost is not" philosophy as periodic_save_job's
    misfire_grace_time=None below.
    """
    store = get_reminder_store()
    for reminder in store.due(datetime.now()):
        try:
            await context.bot.send_message(chat_id=reminder.chat_id, text=reminder.message)
        except Exception:
            logger.exception(
                "Failed to send reminder id=%s to chat_id=%s", reminder.id, reminder.chat_id
            )
            continue
        store.remove(reminder.id)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    _install_log_redaction()

    _warn_if_model_unknown()
    _start_vault_watcher()

    if not config.TELEGRAM_BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN not set in .env")
    if not config.TELEGRAM_ALLOWED_USER_IDS:
        logger.warning(
            "TELEGRAM_ALLOWED_USER_IDS is empty -- nobody is authorized yet. "
            "Message the bot once to get your user id, then add it to .env."
        )

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    # Restrict to private (1:1) chats: if this bot is ever added to a group,
    # its replies -- which contain personal note content -- would otherwise
    # be visible to everyone in that group, not just the authorized user.
    app.add_handler(CommandHandler("start", handle_start, filters=filters.ChatType.PRIVATE))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.VOICE, handle_voice))
    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, handle_message
        )
    )
    app.job_queue.run_repeating(
        periodic_save_job,
        interval=config.PERIODIC_SAVE_INTERVAL_SECONDS,
        first=config.PERIODIC_SAVE_FIRST_DELAY_SECONDS,
        # Without this, APScheduler silently drops (not just delays) a run
        # that's late by more than its default misfire grace time -- which
        # happens constantly on a laptop that sleeps: the whole process
        # freezes during sleep, so the scheduled fire time passes while
        # nothing is running, and on wake the job is considered "too late"
        # and skipped entirely rather than run late. Confirmed via APScheduler's
        # own warning log: "Run time of job ... was missed by 0:52:29". A late
        # save is far better than a silently dropped one for something this
        # infrequent, so allow unlimited lateness.
        job_kwargs={"misfire_grace_time": None},
    )
    app.job_queue.run_repeating(
        reminder_dispatch_job,
        interval=config.REMINDER_DISPATCH_INTERVAL_SECONDS,
        first=config.REMINDER_DISPATCH_INTERVAL_SECONDS,
        job_kwargs={"misfire_grace_time": None},
    )

    logger.info("Starting Telegram bot (long-polling)...")
    app.run_polling()


if __name__ == "__main__":
    main()
