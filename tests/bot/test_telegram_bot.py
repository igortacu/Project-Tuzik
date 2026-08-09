import asyncio
from pathlib import Path
from unittest.mock import patch

from second_brain.bot import telegram_bot
from second_brain.bot.memory import SaveBuffer


def test_strip_sticker_marker_no_marker():
    text, category = telegram_bot._strip_sticker_marker("just a normal reply")
    assert text == "just a normal reply"
    assert category is None


def test_strip_sticker_marker_strips_and_extracts_category():
    text, category = telegram_bot._strip_sticker_marker("Da, evident. [[sticker:eye_roll]]")
    assert text == "Da, evident."
    assert category == "eye_roll"


def test_compress_and_save_chat_skips_when_nothing_to_save():
    with (
        patch(
            "second_brain.bot.telegram_bot._summarizer_llm_client.generate",
            return_value="NOTHING_TO_SAVE",
        ),
        patch("second_brain.bot.telegram_bot.vault_writer.append_note") as mock_append,
    ):
        asyncio.run(telegram_bot._compress_and_save_chat(123, [("hi", "hey")]))

    mock_append.assert_not_called()


def test_compress_and_save_chat_writes_when_something_to_save():
    fake_path = Path("/vault/Murzik Notes/conversation_123.md")
    with (
        patch(
            "second_brain.bot.telegram_bot._summarizer_llm_client.generate",
            return_value="Igor's birthday is March 3rd.",
        ),
        patch(
            "second_brain.bot.telegram_bot.vault_writer.append_note", return_value=fake_path
        ) as mock_append,
    ):
        asyncio.run(
            telegram_bot._compress_and_save_chat(
                123, [("my birthday is march 3", "noted, in a manner of speaking")]
            )
        )

    mock_append.assert_called_once()
    filename, content = mock_append.call_args.args
    assert filename == "conversation_123.md"
    assert "Igor's birthday is March 3rd." in content


def test_periodic_save_job_skips_chats_with_nothing_buffered(tmp_path):
    buffer = SaveBuffer(persist_path=str(tmp_path / "save_buffer.json"))
    buffer.append(1, "real question", "real answer")
    # chat 2 has never had anything appended -- drain(2) returns []

    calls = []

    async def _fake_compress_and_save(chat_id, turns):
        calls.append((chat_id, turns))

    with (
        patch("second_brain.bot.telegram_bot._save_buffer", buffer),
        patch(
            "second_brain.bot.telegram_bot._compress_and_save_chat",
            side_effect=_fake_compress_and_save,
        ),
    ):
        asyncio.run(telegram_bot.periodic_save_job(context=None))

    assert calls == [(1, [("real question", "real answer")])]
    # draining is destructive -- a second run with nothing new does nothing
    calls.clear()
    with (
        patch("second_brain.bot.telegram_bot._save_buffer", buffer),
        patch(
            "second_brain.bot.telegram_bot._compress_and_save_chat",
            side_effect=_fake_compress_and_save,
        ),
    ):
        asyncio.run(telegram_bot.periodic_save_job(context=None))
    assert calls == []
