"""LLM generation with a tiered fallback chain."""

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
    OPENROUTER_FREE = "openrouter_free"
    PAID_FALLBACK = "paid_fallback"
    OLLAMA_LOCAL = "ollama_local"


class AllTiersFailedError(RuntimeError):
    """Raised when the OpenRouter free tier, the paid fallback, and the local
    Ollama instance all failed to serve a request.
    """


def _call_openrouter(
    model_id: str, api_key: str, prompt: str, system_prompt: str | None
) -> str:
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    response = requests.post(
        _OPENROUTER_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": model_id, "messages": messages},
        timeout=_REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return _strip_thinking(response.json()["choices"][0]["message"]["content"])


def _call_ollama(prompt: str, system_prompt: str | None) -> str:
    payload = {"model": config.OLLAMA_MODEL_ID, "prompt": prompt, "stream": False}
    if system_prompt:
        payload["system"] = system_prompt

    response = requests.post(
        f"{config.OLLAMA_BASE_URL}/api/generate",
        json=payload,
        timeout=_REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return _strip_thinking(response.json()["response"])


class LLMClient:
    """generate() tries the OpenRouter free-tier model first (model ID from
    config, not hardcoded); on rate-limit/removal error, falls back to a
    configured paid model, then to a local Ollama instance. Logs which tier
    actually served each request.
    """

    def __init__(self) -> None:
        pass

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        if config.OPENROUTER_API_KEY:
            try:
                result = _call_openrouter(
                    config.OPENROUTER_MODEL_ID, config.OPENROUTER_API_KEY, prompt, system_prompt
                )
                logger.info(
                    "llm request served by tier=%s model=%s",
                    ServingTier.OPENROUTER_FREE.value,
                    config.OPENROUTER_MODEL_ID,
                )
                return result
            except requests.RequestException as exc:
                logger.warning(
                    "OpenRouter free-tier model failed (%s), falling back to paid tier", exc
                )

        # Paid fallback also goes through OpenRouter's OpenAI-compatible API
        # (same request shape), just with a different model id and API key --
        # avoids a second bespoke provider integration for a still-simple
        # config-driven fallback.
        paid_api_key = config.PAID_MODEL_API_KEY or config.OPENROUTER_API_KEY
        if paid_api_key:
            try:
                result = _call_openrouter(
                    config.FALLBACK_MODEL_ID, paid_api_key, prompt, system_prompt
                )
                logger.info(
                    "llm request served by tier=%s model=%s",
                    ServingTier.PAID_FALLBACK.value,
                    config.FALLBACK_MODEL_ID,
                )
                return result
            except requests.RequestException as exc:
                logger.warning(
                    "Paid fallback model failed (%s), falling back to local Ollama", exc
                )

        try:
            result = _call_ollama(prompt, system_prompt)
            logger.info(
                "llm request served by tier=%s model=%s",
                ServingTier.OLLAMA_LOCAL.value,
                config.OLLAMA_MODEL_ID,
            )
            return result
        except requests.RequestException as exc:
            raise AllTiersFailedError("All LLM serving tiers failed") from exc
