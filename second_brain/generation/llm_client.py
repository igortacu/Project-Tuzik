"""LLM generation via a single OpenRouter free-tier model.

No fallback model, no paid tier, no local model, by request -- rate
limiting turned out to hit the whole OpenRouter account, not just one
model, so trying a second model on 429 didn't actually help, just added
complexity and latency.
"""

import logging
import re

import requests

from second_brain import config

logger = logging.getLogger(__name__)

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_REQUEST_TIMEOUT_SECONDS = 30
_RATE_LIMIT_STATUS_CODE = 429

# Some free-tier models emit a visible reasoning/thinking block inline in the
# response content (rather than a separate API field) even when told not to.
# Strip it as a safety net -- the system prompt asks the model not to do this
# in the first place, but this covers the cases where it doesn't listen.
_THINKING_BLOCK_RE = re.compile(r"<(think|thinking|reasoning)>.*?</\1>", re.DOTALL | re.IGNORECASE)


def _strip_thinking(text: str) -> str:
    return _THINKING_BLOCK_RE.sub("", text).strip()


class GenerationFailedError(RuntimeError):
    """Raised when the OpenRouter model failed for a reason other than
    rate-limiting (429 is handled separately -- see LLMClient.generate).
    """


def _call_openrouter(prompt: str, system_prompt: str | None) -> str:
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    response = requests.post(
        _OPENROUTER_URL,
        headers={"Authorization": f"Bearer {config.OPENROUTER_API_KEY}"},
        json={"model": config.OPENROUTER_MODEL_ID, "messages": messages},
        timeout=_REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return _strip_thinking(response.json()["choices"][0]["message"]["content"])


class LLMClient:
    """generate() calls the single configured OpenRouter model
    (config.OPENROUTER_MODEL_ID). On a 429 (rate limit), returns
    config.RATE_LIMIT_MESSAGE instead of raising -- rate limiting is an
    expected, recoverable condition, not a bug, so it gets an in-character
    reply rather than a generic error. If the *next* request also 429s right
    after that warning (the user didn't wait), it escalates to
    config.REPEATED_RATE_LIMIT_MESSAGE instead. A successful request resets
    the streak. Any other failure raises GenerationFailedError.
    """

    def __init__(self) -> None:
        self._consecutive_rate_limits = 0

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        if not config.OPENROUTER_API_KEY:
            raise GenerationFailedError("OPENROUTER_API_KEY not set in .env")

        try:
            result = _call_openrouter(prompt, system_prompt)
            self._consecutive_rate_limits = 0
            logger.info("llm request served by model=%s", config.OPENROUTER_MODEL_ID)
            return result
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == _RATE_LIMIT_STATUS_CODE:
                self._consecutive_rate_limits += 1
                if self._consecutive_rate_limits >= 2:
                    logger.warning("OpenRouter rate-limited again (429) -- escalating reply")
                    return config.REPEATED_RATE_LIMIT_MESSAGE
                logger.warning("OpenRouter rate-limited (429), returning stock reply")
                return config.RATE_LIMIT_MESSAGE
            raise GenerationFailedError(f"OpenRouter request failed: {exc}") from exc
        except requests.RequestException as exc:
            raise GenerationFailedError(f"OpenRouter request failed: {exc}") from exc
