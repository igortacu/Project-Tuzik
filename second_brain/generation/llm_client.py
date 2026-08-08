"""LLM generation: two free-tier OpenRouter models, primary then fallback.

No paid tier, no local model -- OpenRouter free tier only, by request. An
earlier version also tried a "paid" tier and local Ollama, but the "paid"
model id turned out to not be a real chat model (it returned garbage like a
literal "User Safety: safe" instead of an answer) and Ollama was slower than
the free API tier anyway on this hardware.
"""

import logging
import re
from enum import Enum

import requests

from second_brain import config

logger = logging.getLogger(__name__)

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_REQUEST_TIMEOUT_SECONDS = 30

# Some free-tier models emit a visible reasoning/thinking block inline in the
# response content (rather than a separate API field) even when told not to.
# Strip it as a safety net -- the system prompt asks the model not to do this
# in the first place, but this covers the cases where it doesn't listen.
_THINKING_BLOCK_RE = re.compile(r"<(think|thinking|reasoning)>.*?</\1>", re.DOTALL | re.IGNORECASE)


def _strip_thinking(text: str) -> str:
    return _THINKING_BLOCK_RE.sub("", text).strip()


class ServingTier(Enum):
    OPENROUTER_PRIMARY = "openrouter_primary"
    OPENROUTER_FALLBACK = "openrouter_fallback"


class AllTiersFailedError(RuntimeError):
    """Raised when both the primary and fallback OpenRouter free models failed."""


def _call_openrouter(model_id: str, prompt: str, system_prompt: str | None) -> str:
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    response = requests.post(
        _OPENROUTER_URL,
        headers={"Authorization": f"Bearer {config.OPENROUTER_API_KEY}"},
        json={"model": model_id, "messages": messages},
        timeout=_REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return _strip_thinking(response.json()["choices"][0]["message"]["content"])


class LLMClient:
    """generate() tries the primary OpenRouter free-tier model
    (config.OPENROUTER_MODEL_ID); on rate-limit/error, falls back to a second
    free OpenRouter model (config.OPENROUTER_FALLBACK_MODEL_ID). Logs which
    tier actually served each request.
    """

    def __init__(self) -> None:
        pass

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        if not config.OPENROUTER_API_KEY:
            raise AllTiersFailedError("OPENROUTER_API_KEY not set in .env")

        try:
            result = _call_openrouter(config.OPENROUTER_MODEL_ID, prompt, system_prompt)
            logger.info(
                "llm request served by tier=%s model=%s",
                ServingTier.OPENROUTER_PRIMARY.value,
                config.OPENROUTER_MODEL_ID,
            )
            return result
        except requests.RequestException as exc:
            logger.warning(
                "Primary free model failed (%s), falling back to secondary free model", exc
            )

        try:
            result = _call_openrouter(
                config.OPENROUTER_FALLBACK_MODEL_ID, prompt, system_prompt
            )
            logger.info(
                "llm request served by tier=%s model=%s",
                ServingTier.OPENROUTER_FALLBACK.value,
                config.OPENROUTER_FALLBACK_MODEL_ID,
            )
            return result
        except requests.RequestException as exc:
            raise AllTiersFailedError("Both OpenRouter free-tier models failed") from exc
