"""Local embedded vector store (Chroma), no server."""

from typing import Any

import chromadb

from second_brain import config

_COLLECTION_NAME = "chunks"
_OVERFETCH_MULTIPLIER = 5


def _sanitize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Chroma metadata values must be str/int/float/bool. Lists (tags,
    outbound_links) are joined into comma-separated strings; None values are
    dropped since Chroma rejects them outright.
    """
    sanitized: dict[str, Any] = {}
    for key, value in metadata.items():
        if value is None:
            continue
        if isinstance(value, list):
            sanitized[key] = ",".join(str(item) for item in value)
        else:
            sanitized[key] = value
    return sanitized


def _matches_filters(metadata: dict[str, Any], filters: dict[str, Any] | None) -> bool:
    """Shared by VectorStore and BM25Index. Handles 'tags' as either a list
    (BM25Index stores metadata as-is) or a comma-joined string (VectorStore
    sanitizes list metadata into strings before storing in Chroma).
    """
    if not filters:
        return True

    if "tags" in filters:
        wanted = filters["tags"]
        wanted_set = {wanted} if isinstance(wanted, str) else set(wanted)
        raw_have = metadata.get("tags")
        if not raw_have:
            have: set[str] = set()
        elif isinstance(raw_have, list):
            have = set(raw_have)
        else:
            have = set(str(raw_have).split(","))
        if not wanted_set & have:
            return False

    if "date_from" in filters or "date_to" in filters:
        date_value = metadata.get("date")
        if not date_value:
            return False
        if "date_from" in filters and str(date_value) < filters["date_from"]:
            return False
        if "date_to" in filters and str(date_value) > filters["date_to"]:
            return False

    return True


class VectorStore:
    """Wraps a local, embedded Chroma collection.

    CRITICAL: on file change, delete_by_source MUST be called before
    re-inserting new chunks for that file, or stale duplicate chunks persist
    and silently degrade retrieval.
    """

    def __init__(self, persist_path: str | None = None) -> None:
        client = chromadb.PersistentClient(path=persist_path or config.VECTOR_STORE_PATH)
        self._collection = client.get_or_create_collection(name=_COLLECTION_NAME)

    def upsert(self, chunk_id: str, vector: list[float], metadata: dict[str, Any]) -> None:
        self._collection.upsert(
            ids=[chunk_id],
            embeddings=[vector],
            metadatas=[_sanitize_metadata(metadata)],
        )

    def delete_by_source(self, filepath: str) -> None:
        """Remove every chunk whose metadata['source_file'] == filepath."""
        self._collection.delete(where={"source_file": filepath})

    def query(
        self,
        vector: list[float],
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        # Chroma's `where` only supports exact-match on scalar fields, which
        # can't express "tags list contains X" once tags are comma-joined.
        # Over-fetch and filter in Python instead of relying on `where`.
        candidate_k = top_k * _OVERFETCH_MULTIPLIER if filters else top_k
        results = self._collection.query(
            query_embeddings=[vector],
            n_results=candidate_k,
        )

        ids = results["ids"][0] if results["ids"] else []
        metadatas = results["metadatas"][0] if results["metadatas"] else []
        distances = results["distances"][0] if results["distances"] else []

        matches: list[dict[str, Any]] = []
        for chunk_id, metadata, distance in zip(ids, metadatas, distances):
            if not _matches_filters(metadata, filters):
                continue
            matches.append({"chunk_id": chunk_id, "metadata": metadata, "score": distance})
            if len(matches) >= top_k:
                break

        return matches
