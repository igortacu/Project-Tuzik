"""Speech-to-text via Groq's OpenAI-compatible transcription endpoint."""

import logging

import requests

from second_brain import config

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_SECONDS = 60


class SpeechToTextError(RuntimeError):
    """Raised when voice transcription is unavailable or fails."""


def transcribe_audio(audio_bytes: bytes, filename: str = "voice.ogg") -> str:
    if not config.GROQ_API_KEY:
        raise SpeechToTextError("GROQ_API_KEY not set in .env")
    if len(audio_bytes) > config.VOICE_TRANSCRIPTION_MAX_BYTES:
        raise SpeechToTextError("voice message is too large to transcribe")

    response = requests.post(
        config.GROQ_TRANSCRIPTION_URL,
        headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"},
        data={
            "model": config.GROQ_TRANSCRIPTION_MODEL_ID,
            "response_format": "json",
            "temperature": "0",
            "prompt": config.VOICE_TRANSCRIPTION_PROMPT,
        },
        files={"file": (filename, audio_bytes, "audio/ogg")},
        timeout=_REQUEST_TIMEOUT_SECONDS,
    )

    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise SpeechToTextError(f"Groq transcription request failed: {exc}") from exc

    try:
        text = response.json()["text"].strip()
    except (KeyError, TypeError, ValueError) as exc:
        raise SpeechToTextError("Groq returned an unexpected transcription response") from exc

    if not text:
        raise SpeechToTextError("Groq returned an empty transcription")

    logger.info("transcribed voice message with model=%s", config.GROQ_TRANSCRIPTION_MODEL_ID)
    return text
