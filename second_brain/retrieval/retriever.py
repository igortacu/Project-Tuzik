"""Query -> retrieved chunks. Free of any LLM/prompting logic (retrieval must
not import anything from generation/).
"""

from dataclasses import dataclass
from typing import Any

from second_brain import config
from second_brain.embedding.client import EmbeddingClient
from second_brain.storage.bm25_index import BM25Index
from second_brain.storage.vector_store import VectorStore

_CANDIDATE_MULTIPLIER = 3


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
        self._embedding_client = embedding_client
        self._vector_store = vector_store
        self._bm25_index = bm25_index
        self._rrf_k = rrf_k if rrf_k is not None else config.RRF_K

    def retrieve(
        self,
        query: str,
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        candidate_k = max(top_k * _CANDIDATE_MULTIPLIER, top_k)

        query_vector = self._embedding_client.embed([query])[0]
        vector_results = self._vector_store.query(query_vector, candidate_k, filters)
        bm25_results = self._bm25_index.query(query, candidate_k, filters)

        scores: dict[str, float] = {}
        info: dict[str, dict[str, Any]] = {}

        for results in (vector_results, bm25_results):
            for rank, result in enumerate(results, start=1):
                chunk_id = result["chunk_id"]
                scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (self._rrf_k + rank)
                info.setdefault(chunk_id, result)

        ranked_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)[:top_k]

        return [
            RetrievedChunk(
                chunk_id=chunk_id,
                text=info[chunk_id]["metadata"].get("text", ""),
                metadata=info[chunk_id]["metadata"],
                score=scores[chunk_id],
            )
            for chunk_id in ranked_ids
        ]
