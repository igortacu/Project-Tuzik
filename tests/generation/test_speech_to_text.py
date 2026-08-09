from unittest.mock import Mock, patch

import pytest
import requests

from second_brain import config
from second_brain.generation import speech_to_text


def _fake_response(payload: dict) -> Mock:
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = payload
    return response


def test_transcribe_audio_posts_to_groq(monkeypatch):
    monkeypatch.setattr(config, "GROQ_API_KEY", "fake-groq-key")
    audio = b"fake ogg bytes"

    with patch("requests.post", return_value=_fake_response({"text": "salut murzik"})) as mock_post:
        text = speech_to_text.transcribe_audio(audio, "voice.ogg")

    assert text == "salut murzik"
    kwargs = mock_post.call_args.kwargs
    assert kwargs["headers"]["Authorization"] == "Bearer fake-groq-key"
    assert kwargs["data"]["model"] == "whisper-large-v3-turbo"
    assert kwargs["data"]["response_format"] == "json"
    assert kwargs["files"]["file"] == ("voice.ogg", audio, "audio/ogg")


def test_transcribe_audio_requires_groq_key(monkeypatch):
    monkeypatch.setattr(config, "GROQ_API_KEY", None)

    with pytest.raises(speech_to_text.SpeechToTextError, match="GROQ_API_KEY"):
        speech_to_text.transcribe_audio(b"audio")


def test_transcribe_audio_rejects_oversized_audio(monkeypatch):
    monkeypatch.setattr(config, "GROQ_API_KEY", "fake-groq-key")
    monkeypatch.setattr(config, "VOICE_TRANSCRIPTION_MAX_BYTES", 3)

    with pytest.raises(speech_to_text.SpeechToTextError, match="too large"):
        speech_to_text.transcribe_audio(b"1234")


def test_transcribe_audio_rejects_empty_transcription(monkeypatch):
    monkeypatch.setattr(config, "GROQ_API_KEY", "fake-groq-key")

    with (
        patch("requests.post", return_value=_fake_response({"text": "  "})),
        pytest.raises(speech_to_text.SpeechToTextError, match="empty"),
    ):
        speech_to_text.transcribe_audio(b"audio")


def test_transcribe_audio_explains_unauthorized_key(monkeypatch):
    monkeypatch.setattr(config, "GROQ_API_KEY", "wrong-key")
    response = Mock()
    response.status_code = 401
    response.raise_for_status.side_effect = requests.HTTPError(response=response)

    with (
        patch("requests.post", return_value=response),
        pytest.raises(speech_to_text.SpeechToTextError, match="GroqCloud key"),
    ):
        speech_to_text.transcribe_audio(b"audio")
