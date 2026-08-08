"""Telegram bot front-end for query_pipeline.answer_query.

Long-polling only (the bot process reaches out to Telegram, nothing needs to
be publicly reachable) -- no server, no webhook, no FastAPI. Restricted to an
allow-listed set of Telegram user ids (config.TELEGRAM_ALLOWED_USER_IDS)
since anyone who finds the bot's username could otherwise message it.
"""

import asyncio
import logging
import re

import requests
from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from second_brain import config
from second_brain.agent import vault_writer
from second_brain.bot.memory import ConversationMemory
from second_brain.pipelines import query_pipeline

logger = logging.getLogger(__name__)

_MAX_MESSAGE_LENGTH = 4000  # Telegram's hard cap is 4096; leave some margin

# Matches the marker the model can put in its reply to trigger a sticker --
# see config.STICKERS and config.SYSTEM_PROMPT.
_STICKER_MARKER_RE = re.compile(r"\[\[sticker:(\w+)\]\]")

# Matches the marker the model can put in its reply to trigger a vault save --
# see config.SYSTEM_PROMPT and agent/vault_writer.py. No owner/secondary-user
# distinction yet -- everyone in TELEGRAM_ALLOWED_USER_IDS writes directly,
# by request (the approval flow for non-owner writes is a separate,
# not-yet-built piece).
_REMEMBER_MARKER_RE = re.compile(r"\[\[remember:([^|]+)\|(.*?)\]\]", re.DOTALL)

# In-process only, per chat -- cleared on restart. See bot/memory.py.
_memory = ConversationMemory(config.CONVERSATION_HISTORY_TURNS)

_START_MESSAGE = (
    f"Hey, I'm *{config.ASSISTANT_NAME}* — {config.OWNER_NAME}'s personal second brain "
    "on legs. Ask me anything about your notes and I'll dig it up (with receipts)."
)


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


def _strip_remember_marker(text: str) -> tuple[str, tuple[str, str] | None]:
    """Splits a raw model reply into (visible_text, (filename, content)).
    The second element is None if the reply had no [[remember:...]] marker.
    """
    match = _REMEMBER_MARKER_RE.search(text)
    remaining_text = re.sub(r"[ \t]{2,}", " ", _REMEMBER_MARKER_RE.sub("", text)).strip()
    if not match:
        return remaining_text, None
    filename, content = match.group(1).strip(), match.group(2).strip()
    return remaining_text, (filename, content)


async def _handle_remember_request(filename: str, content: str) -> str:
    """Performs the save and returns a confirmation string -- the bot's own
    words, not the model's, since the model isn't allowed to claim this
    happened in its own reply text (see SYSTEM_PROMPT).
    """
    try:
        path = await asyncio.to_thread(vault_writer.append_note, filename, content)
        return f"✅ Saved to `{config.MURZIK_NOTES_DIR}/{path.name}`."
    except vault_writer.VaultWriteError:
        logger.exception("Failed to save note (filename=%r)", filename)
        return "⚠️ Couldn't save that one -- check the logs."


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _reject_if_unauthorized(update):
        return
    await update.message.reply_text(_START_MESSAGE, parse_mode=ParseMode.MARKDOWN)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _reject_if_unauthorized(update):
        return

    question = update.message.text
    chat_id = update.effective_chat.id
    await update.message.chat.send_action(ChatAction.TYPING)

    try:
        answer = await asyncio.to_thread(
            query_pipeline.answer_query, question, history=_memory.get(chat_id)
        )
    except Exception:
        logger.exception("answer_query failed for question: %r", question)
        await update.message.reply_text("Something went wrong answering that -- check the logs.")
        return

    remaining_text, remember_request = _strip_remember_marker(answer)
    if remember_request is not None:
        confirmation = await _handle_remember_request(*remember_request)
        remaining_text = f"{remaining_text}\n\n{confirmation}" if remaining_text else confirmation

    remaining_text, sticker_category = _strip_sticker_marker(remaining_text)
    await _reply_with_possible_sticker(update, remaining_text, sticker_category)
    _memory.append(chat_id, question, remaining_text or answer)


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


def main() -> None:
    logging.basicConfig(level=logging.INFO)

    _warn_if_model_unknown()

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
    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, handle_message
        )
    )

    logger.info("Starting Telegram bot (long-polling)...")
    app.run_polling()


if __name__ == "__main__":
    main()
