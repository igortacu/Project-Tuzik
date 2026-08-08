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
from second_brain.pipelines import query_pipeline

logger = logging.getLogger(__name__)

_MAX_MESSAGE_LENGTH = 4000  # Telegram's hard cap is 4096; leave some margin

# Matches the marker the model can put in its reply to trigger a sticker --
# see config.STICKERS and config.SYSTEM_PROMPT.
_STICKER_MARKER_RE = re.compile(r"\[\[sticker:(\w+)\]\]")

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


async def _reply_with_possible_sticker(update: Update, text: str) -> None:
    """Sends text (if any remains) and/or a sticker, based on whether the
    model's reply included a [[sticker:CATEGORY]] marker.
    """
    match = _STICKER_MARKER_RE.search(text)
    remaining_text = re.sub(r"[ \t]{2,}", " ", _STICKER_MARKER_RE.sub("", text)).strip()

    if remaining_text:
        await _reply_in_chunks(update, remaining_text)

    if not match:
        return

    category = match.group(1)
    file_id = config.STICKERS.get(category)
    if file_id:
        await update.message.reply_sticker(file_id)
    else:
        logger.warning("Model requested unknown sticker category: %r", category)


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _reject_if_unauthorized(update):
        return
    await update.message.reply_text(_START_MESSAGE, parse_mode=ParseMode.MARKDOWN)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _reject_if_unauthorized(update):
        return

    question = update.message.text
    await update.message.chat.send_action(ChatAction.TYPING)

    try:
        answer = await asyncio.to_thread(query_pipeline.answer_query, question)
    except Exception:
        logger.exception("answer_query failed for question: %r", question)
        await update.message.reply_text("Something went wrong answering that -- check the logs.")
        return

    await _reply_with_possible_sticker(update, answer)


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

    if config.OPENROUTER_MODEL_ID not in known_ids:
        logger.warning(
            "config.OPENROUTER_MODEL_ID=%r was not found in OpenRouter's current "
            "model list -- every query will fail until this is fixed. Check "
            "https://openrouter.ai/models for a valid free-tier model id.",
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
