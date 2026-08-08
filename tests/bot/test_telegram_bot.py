import asyncio
from pathlib import Path
from unittest.mock import patch

from second_brain.agent import vault_writer
from second_brain.bot import telegram_bot


def test_strip_sticker_marker_no_marker():
    text, category = telegram_bot._strip_sticker_marker("just a normal reply")
    assert text == "just a normal reply"
    assert category is None


def test_strip_sticker_marker_strips_and_extracts_category():
    text, category = telegram_bot._strip_sticker_marker("Da, evident. [[sticker:eye_roll]]")
    assert text == "Da, evident."
    assert category == "eye_roll"


def test_strip_remember_marker_no_marker():
    text, request = telegram_bot._strip_remember_marker("just a normal reply")
    assert text == "just a normal reply"
    assert request is None


def test_strip_remember_marker_extracts_filename_and_content():
    raw = "Sure. [[remember:Anniversary.md|Igor and Loredana married ~1 year ago.]]"
    text, request = telegram_bot._strip_remember_marker(raw)
    assert text == "Sure."
    assert request == ("Anniversary.md", "Igor and Loredana married ~1 year ago.")


def test_strip_remember_marker_handles_multiline_content():
    raw = "[[remember:notes.md|Line one.\nLine two.]] ok"
    text, request = telegram_bot._strip_remember_marker(raw)
    assert text == "ok"
    assert request == ("notes.md", "Line one.\nLine two.")


def test_handle_remember_request_success_returns_confirmation():
    fake_path = Path("/vault/Murzik Notes/x.md")
    with patch("second_brain.bot.telegram_bot.vault_writer.append_note", return_value=fake_path):
        result = asyncio.run(telegram_bot._handle_remember_request("x.md", "content"))

    assert "Saved" in result
    assert "x.md" in result


def test_handle_remember_request_failure_returns_error_message():
    def _raise(filename, content):
        raise vault_writer.VaultWriteError("nope")

    with patch("second_brain.bot.telegram_bot.vault_writer.append_note", side_effect=_raise):
        result = asyncio.run(telegram_bot._handle_remember_request("../escape.md", "content"))

    assert "Couldn't save" in result
