import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

from telegram.error import BadRequest

from second_brain.agent.reminders import ReminderStore
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


def test_strip_sticker_marker_accepts_bang_format_with_space():
    text, category = telegram_bot._strip_sticker_marker(
        "Acuma nu mai ai scuze. !sticker: done_with_you"
    )
    assert text == "Acuma nu mai ai scuze."
    assert category == "done_with_you"


def test_strip_sticker_marker_accepts_bang_format_without_space():
    text, category = telegram_bot._strip_sticker_marker("Cu placere, sefu'. !sticker:cheers")
    assert text == "Cu placere, sefu'."
    assert category == "cheers"


def test_strip_sticker_marker_normalizes_hyphenated_category():
    text, category = telegram_bot._strip_sticker_marker("Gata. !sticker: done-with-you")
    assert text == "Gata."
    assert category == "done_with_you"


def test_reply_with_possible_sticker_does_not_raise_when_telegram_rejects_sticker():
    class _FakeMessage:
        reply_sticker = AsyncMock(side_effect=BadRequest("wrong file identifier"))
        reply_text = AsyncMock()

    class _FakeUpdate:
        message = _FakeMessage()

    asyncio.run(telegram_bot._reply_with_possible_sticker(_FakeUpdate(), "", "shrug"))

    _FakeMessage.reply_sticker.assert_awaited_once()
    _FakeMessage.reply_text.assert_not_awaited()


def test_sanitize_assistant_text_for_storage_removes_raw_dsml_block():
    raw = (
        "before\n"
        '< | DSML | tool_calls>< | DSML | invoke name="web_search">'
        '< | DSML | parameter name="query" string="true">x</ | DSML | parameter>'
        "</ | DSML | invoke></ | DSML | tool_calls>\n"
        "after"
    )

    assert telegram_bot._sanitize_assistant_text_for_storage(raw) == "before\n\nafter"


def test_sanitize_assistant_text_for_storage_suppresses_malformed_dsml():
    assert "DSML" not in telegram_bot._sanitize_assistant_text_for_storage("< | DSML | broken>")


def test_telegram_token_redaction_filter_scrubs_log_args():
    class UrlLike:
        def __str__(self):
            return "https://api.telegram.org/bot123456:secret-token/getMe"

    record = logging.LogRecord(
        name="httpx",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='HTTP Request: POST %s "HTTP/1.1 200 OK"',
        args=(UrlLike(),),
        exc_info=None,
    )

    assert telegram_bot._TelegramTokenRedactionFilter().filter(record)
    assert record.getMessage() == (
        'HTTP Request: POST https://api.telegram.org/bot[REDACTED]/getMe '
        '"HTTP/1.1 200 OK"'
    )
    assert telegram_bot._redact_telegram_tokens("Starting Telegram bot") == "Starting Telegram bot"


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
    fake_path = Path("/vault/Murzik Notes/People/igor.md")
    summarizer_output = (
        "CATEGORY: People\n"
        "FILENAME: igor.md\n"
        "TAGS: birthday\n"
        "---\n"
        "Igor's birthday is March 3rd."
    )
    with (
        patch(
            "second_brain.bot.telegram_bot._summarizer_llm_client.generate",
            return_value=summarizer_output,
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

    mock_append.assert_called_once_with(
        "People", "igor.md", "Igor's birthday is March 3rd.", ["birthday"]
    )


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
    # successful save clears the buffered turn -- a second run with nothing new does nothing
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


def test_periodic_save_job_keeps_buffer_when_compress_fails(tmp_path):
    buffer = SaveBuffer(persist_path=str(tmp_path / "save_buffer.json"))
    buffer.append(1, "important question", "important answer")

    async def _failing_compress_and_save(chat_id, turns):
        raise RuntimeError("temporary failure")

    with (
        patch("second_brain.bot.telegram_bot._save_buffer", buffer),
        patch(
            "second_brain.bot.telegram_bot._compress_and_save_chat",
            side_effect=_failing_compress_and_save,
        ),
    ):
        asyncio.run(telegram_bot.periodic_save_job(context=None))

    assert buffer.peek(1) == [("important question", "important answer")]


def test_answer_message_forwards_chat_id_to_answer_query():
    class _FakeChat:
        async def send_action(self, *a, **k):
            pass

    class _FakeMessage:
        chat = _FakeChat()

        async def reply_text(self, *a, **k):
            pass

    class _FakeUpdate:
        effective_chat = type("C", (), {"id": 777})()
        message = _FakeMessage()

    fake_result = type("R", (), {"text": "an answer", "image_urls": []})()

    with (
        patch(
            "second_brain.bot.telegram_bot.query_pipeline.answer_query",
            return_value=fake_result,
        ) as mock_answer,
        patch.object(telegram_bot._memory, "append"),
        patch.object(telegram_bot._save_buffer, "append"),
    ):
        asyncio.run(telegram_bot._answer_message(_FakeUpdate(), "hi"))

    assert mock_answer.call_args.kwargs["chat_id"] == 777


def test_answer_message_stores_sanitized_assistant_text():
    class _FakeChat:
        async def send_action(self, *a, **k):
            pass

    class _FakeMessage:
        chat = _FakeChat()

        async def reply_text(self, *a, **k):
            pass

    class _FakeUpdate:
        effective_chat = type("C", (), {"id": 777})()
        message = _FakeMessage()

    raw_reply = (
        "visible answer\n"
        '< | DSML | tool_calls>< | DSML | invoke name="web_search">'
        '< | DSML | parameter name="query" string="true">x</ | DSML | parameter>'
        "</ | DSML | invoke></ | DSML | tool_calls>"
    )
    fake_result = type("R", (), {"text": raw_reply, "image_urls": []})()

    with (
        patch(
            "second_brain.bot.telegram_bot.query_pipeline.answer_query",
            return_value=fake_result,
        ),
        patch.object(telegram_bot._memory, "append") as mock_memory_append,
        patch.object(telegram_bot._save_buffer, "append") as mock_save_buffer_append,
    ):
        asyncio.run(telegram_bot._answer_message(_FakeUpdate(), "hi"))

    mock_memory_append.assert_called_once_with(777, "hi", "visible answer")
    mock_save_buffer_append.assert_called_once_with(777, "hi", "visible answer")


def test_reminder_dispatch_job_sends_and_removes_due_reminders(tmp_path):
    store = ReminderStore(persist_path=str(tmp_path / "reminders.json"))
    due = store.add(1, datetime.now() - timedelta(minutes=1), "due reminder")
    store.add(1, datetime.now() + timedelta(hours=1), "not due yet")

    fake_context = type("Ctx", (), {"bot": type("Bot", (), {})()})()
    fake_context.bot.send_message = AsyncMock()

    with patch("second_brain.bot.telegram_bot.get_reminder_store", return_value=store):
        asyncio.run(telegram_bot.reminder_dispatch_job(fake_context))

    fake_context.bot.send_message.assert_called_once_with(chat_id=1, text="due reminder")
    remaining_ids = [r.id for r in store.list_for_chat(1)]
    assert due.id not in remaining_ids
    assert len(remaining_ids) == 1


def test_reminder_dispatch_job_skips_when_nothing_due(tmp_path):
    store = ReminderStore(persist_path=str(tmp_path / "reminders.json"))
    store.add(1, datetime.now() + timedelta(hours=1), "not due yet")

    fake_context = type("Ctx", (), {"bot": type("Bot", (), {})()})()
    fake_context.bot.send_message = AsyncMock()

    with patch("second_brain.bot.telegram_bot.get_reminder_store", return_value=store):
        asyncio.run(telegram_bot.reminder_dispatch_job(fake_context))

    fake_context.bot.send_message.assert_not_called()
    assert len(store.list_for_chat(1)) == 1


def test_reminder_dispatch_job_continues_after_one_send_failure(tmp_path):
    store = ReminderStore(persist_path=str(tmp_path / "reminders.json"))
    store.add(1, datetime.now() - timedelta(minutes=1), "fails to send")
    store.add(2, datetime.now() - timedelta(minutes=1), "sends fine")

    fake_context = type("Ctx", (), {"bot": type("Bot", (), {})()})()
    fake_context.bot.send_message = AsyncMock(side_effect=[Exception("boom"), None])

    with patch("second_brain.bot.telegram_bot.get_reminder_store", return_value=store):
        asyncio.run(telegram_bot.reminder_dispatch_job(fake_context))

    assert fake_context.bot.send_message.call_count == 2
    # the one that failed to send is still pending (not removed); the one
    # that sent successfully is gone
    remaining_messages = {r.message for r in store.list_for_chat(1) + store.list_for_chat(2)}
    assert remaining_messages == {"fails to send"}
