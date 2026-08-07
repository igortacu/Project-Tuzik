"""Local embedded vector store (Chroma), no server."""

from typing import Any


class VectorStore:
    """Wraps a local, embedded Chroma collection.

    CRITICAL: on file change, delete_by_source MUST be called before
    re-inserting new chunks for that file, or stale duplicate chunks persist
    and silently degrade retrieval.
    """

    def __init__(self, persist_path: str | None = None) -> None:
        raise NotImplementedError

    def upsert(self, chunk_id: str, vector: list[float], metadata: dict[str, Any]) -> None:
        raise NotImplementedError

    def delete_by_source(self, filepath: str) -> None:
        """Remove every chunk whose metadata['source_file'] == filepath."""
        raise NotImplementedError

    def query(
        self,
        vector: list[float],
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError
