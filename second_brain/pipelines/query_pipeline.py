"""Wires retrieval -> generation. Runs per user query. Shares no logic with
index_pipeline.py beyond EmbeddingClient.
"""

from typing import Any


def answer_query(
    query: str,
    top_k: int | None = None,
    filters: dict[str, Any] | None = None,
) -> str:
    """Retrieve relevant chunks, build a prompt, and generate an answer."""
    raise NotImplementedError
