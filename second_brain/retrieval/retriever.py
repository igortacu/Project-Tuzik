"""Query -> retrieved chunks. Free of any LLM/prompting logic (retrieval must
not import anything from generation/).
"""

from dataclasses import dataclass
from typing import Any

from second_brain.embedding.client import EmbeddingClient
from second_brain.storage.bm25_index import BM25Index
from second_brain.storage.vector_store import VectorStore


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    metadata: dict[str, Any]
    score: float


class Retriever:
    """Embeds the query, fetches candidates from both VectorStore and
    BM25Index, and merges them via reciprocal rank fusion (RRF).
    """

    def __init__(
        self,
        embedding_client: EmbeddingClient,
        vector_store: VectorStore,
        bm25_index: BM25Index,
        rrf_k: int | None = None,
    ) -> None:
        raise NotImplementedError

    def retrieve(
        self,
        query: str,
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        raise NotImplementedError
