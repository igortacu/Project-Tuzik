"""Local lexical index (rank-bm25) used alongside VectorStore for hybrid retrieval.

Same method shape as vector_store.VectorStore (upsert / delete_by_source / query)
so retrieval/retriever.py can treat both indexes uniformly. Persists as a flat
JSON file of {chunk_id, text, metadata} records (config.BM25_INDEX_PATH) rather
than a pickle, for inspectability and to avoid pickle's code-execution risk on
load. The in-memory BM25 model is rebuilt from that JSON on startup, which is
cheap at this vault's scale (hundreds of notes).
"""

from typing import Any


class BM25Index:
    """CRITICAL: on file change, delete_by_source MUST be called before
    re-inserting new chunks for that file, or stale duplicate chunks persist
    and silently degrade retrieval — same rule as VectorStore.
    """

    def __init__(self, persist_path: str | None = None) -> None:
        raise NotImplementedError

    def upsert(self, chunk_id: str, text: str, metadata: dict[str, Any]) -> None:
        raise NotImplementedError

    def delete_by_source(self, filepath: str) -> None:
        """Remove every chunk whose metadata['source_file'] == filepath."""
        raise NotImplementedError

    def query(
        self,
        query_text: str,
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError
