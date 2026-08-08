"""Wires retrieval -> generation. Runs per user query. Shares no logic with
index_pipeline.py beyond EmbeddingClient.
"""

from typing import Any

from second_brain import config
from second_brain.embedding.client import EmbeddingClient
from second_brain.generation.llm_client import LLMClient
from second_brain.generation.prompt_builder import build_prompt
from second_brain.retrieval.retriever import Retriever
from second_brain.storage.bm25_index import BM25Index
from second_brain.storage.vector_store import VectorStore

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
) -> str:
    """Retrieve relevant chunks, build a prompt, and generate an answer."""
    resolved_top_k = top_k if top_k is not None else config.TOP_K
    chunks = _get_retriever().retrieve(query, resolved_top_k, filters)
    prompt = build_prompt(query, chunks)
    return _get_llm_client().generate(prompt, system_prompt=config.SYSTEM_PROMPT)
