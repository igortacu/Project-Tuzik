"""LLM generation with a tiered fallback chain."""

from enum import Enum


class ServingTier(Enum):
    OPENROUTER_FREE = "openrouter_free"
    PAID_FALLBACK = "paid_fallback"
    OLLAMA_LOCAL = "ollama_local"


class LLMClient:
    """generate() tries the OpenRouter free-tier model first (model ID from
    config, not hardcoded); on rate-limit/removal error, falls back to a
    configured paid model, then to a local Ollama instance. Logs which tier
    actually served each request.
    """

    def __init__(self) -> None:
        raise NotImplementedError

    def generate(self, prompt: str) -> str:
        raise NotImplementedError
