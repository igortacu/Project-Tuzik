"""Wires retrieval -> generation. Runs per user query. Shares no logic with
index_pipeline.py beyond EmbeddingClient.
"""

import re
from typing import Any

from second_brain import config
from second_brain.embedding.client import EmbeddingClient
from second_brain.generation.llm_client import LLMClient
from second_brain.generation.prompt_builder import build_prompt
from second_brain.retrieval.retriever import Retriever
from second_brain.storage.bm25_index import BM25Index
from second_brain.storage.vector_store import VectorStore

# Retrieval always returns top_k candidates regardless of relevance (no
# confidence threshold anywhere in the pipeline), so a small free model
# handed a "context" block for a plain "hello" will often reference it
# anyway even when told not to -- unreliable no matter how the system prompt
# is worded. Skip retrieval entirely for greeting-shaped messages instead of
# relying on the model to ignore context it shouldn't have been given.
_SMALL_TALK_PHRASES = {
    "hi", "hello", "hey", "yo", "sup", "hiya", "howdy",
    "salut", "buna", "buna ziua", "servus", "noroc",
    "privet", "zdorova", "kak dela", "chto novogo",
    "ce faci", "ce mai faci", "alio, ceo tam?",
}
_PUNCTUATION_RE = re.compile(r"[^\w\s]")


def _is_small_talk(query: str) -> bool:
    text = _PUNCTUATION_RE.sub("", query.lower()).strip()
    text = re.sub(rf"\b{re.escape(config.ASSISTANT_NAME.lower())}\b", "", text).strip()
    text = re.sub(r"\s+", " ", text)
    return text in _SMALL_TALK_PHRASES or len(text.split()) <= 1

# Lazily-created, process-wide singletons -- same rationale as
# pipelines/index_pipeline.py: the embedding model and store connections are
# expensive to (re)open and answer_query() is meant to be called repeatedly.
_retriever: Retriever | None = None
_llm_client: LLMClient | None = None


def _get_retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        _retriever = Retriever(EmbeddingClient(), VectorStore(), BM25Index())
    return _retriever


def _get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client


def answer_query(
    query: str,
    top_k: int | None = None,
    filters: dict[str, Any] | None = None,
    history: list[tuple[str, str]] | None = None,
) -> str:
    """Retrieve relevant chunks, build a prompt, and generate an answer.

    Skips retrieval entirely for small-talk-shaped messages -- see
    _is_small_talk. history is optional prior-turn context (see
    bot/memory.py) -- this function stays stateless itself, the caller owns
    conversation state and passes it in.
    """
    if _is_small_talk(query):
        return _get_llm_client().generate(
            f"Message: {query}\nReply:",
            system_prompt=config.SYSTEM_PROMPT,
            history=history,
        )

    resolved_top_k = top_k if top_k is not None else config.TOP_K
    chunks = _get_retriever().retrieve(query, resolved_top_k, filters)
    prompt = build_prompt(query, chunks)
    return _get_llm_client().generate(prompt, system_prompt=config.SYSTEM_PROMPT, history=history)
