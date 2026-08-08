"""Telegram bot front-end for query_pipeline.answer_query.

Long-polling only (the bot process reaches out to Telegram, nothing needs to
be publicly reachable) -- no server, no webhook, no FastAPI. Restricted to an
allow-listed set of Telegram user ids (config.TELEGRAM_ALLOWED_USER_IDS)
since anyone who finds the bot's username could otherwise message it.
"""

import asyncio
import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from second_brain import config
from second_brain.pipelines import query_pipeline

logger = logging.getLogger(__name__)

_MAX_MESSAGE_LENGTH = 4000  # Telegram's hard cap is 4096; leave some margin


def _is_authorized(user_id: int) -> bool:
    return user_id in config.TELEGRAM_ALLOWED_USER_IDS


async def _reply_in_chunks(update: Update, text: str) -> None:
    for start in range(0, len(text), _MAX_MESSAGE_LENGTH):
        await update.message.reply_text(text[start : start + _MAX_MESSAGE_LENGTH])


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    if not _is_authorized(user_id):
        await update.message.reply_text(
            f"Not authorized. Your Telegram user id is {user_id} -- add it to "
            "TELEGRAM_ALLOWED_USER_IDS in .env to use this bot."
        )
        return

    question = update.message.text
    await update.message.chat.send_action(ChatAction.TYPING)

    try:
        answer = await asyncio.to_thread(query_pipeline.answer_query, question)
    except Exception:
        logger.exception("answer_query failed for question: %r", question)
        await update.message.reply_text("Something went wrong answering that -- check the logs.")
        return

    await _reply_in_chunks(update, answer)


def main() -> None:
    logging.basicConfig(level=logging.INFO)

    if not config.TELEGRAM_BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN not set in .env")
    if not config.TELEGRAM_ALLOWED_USER_IDS:
        logger.warning(
            "TELEGRAM_ALLOWED_USER_IDS is empty -- nobody is authorized yet. "
            "Message the bot once to get your user id, then add it to .env."
        )

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Starting Telegram bot (long-polling)...")
    app.run_polling()


if __name__ == "__main__":
    main()
