"""Local lexical index (rank-bm25) used alongside VectorStore for hybrid retrieval.

Same method shape as vector_store.VectorStore (upsert / delete_by_source / query)
so retrieval/retriever.py can treat both indexes uniformly. Persists as a flat
JSON file of {chunk_id, text, metadata} records (config.BM25_INDEX_PATH) rather
than a pickle, for inspectability and to avoid pickle's code-execution risk on
load. The in-memory BM25 model is rebuilt from that JSON lazily (on the next
query() after a write), which is cheap at this vault's scale (hundreds of
notes) and avoids re-tokenizing the whole corpus on every single upsert.
"""

import json
import os
import re
from typing import Any

from rank_bm25 import BM25Okapi

from second_brain import config
from second_brain.storage.vector_store import _matches_filters

_TOKEN_RE = re.compile(r"\w+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class BM25Index:
    """CRITICAL: on file change, delete_by_source MUST be called before
    re-inserting new chunks for that file, or stale duplicate chunks persist
    and silently degrade retrieval — same rule as VectorStore.
    """

    def __init__(self, persist_path: str | None = None) -> None:
        self._persist_path = persist_path or config.BM25_INDEX_PATH
        self._records: dict[str, dict[str, Any]] = {}
        self._chunk_ids: list[str] = []
        self._bm25: BM25Okapi | None = None
        self._dirty = True
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self._persist_path):
            return
        with open(self._persist_path, encoding="utf-8") as f:
            records = json.load(f)
        self._records = {record["chunk_id"]: record for record in records}

    def _persist(self) -> None:
        os.makedirs(os.path.dirname(self._persist_path) or ".", exist_ok=True)
        with open(self._persist_path, "w", encoding="utf-8") as f:
            json.dump(list(self._records.values()), f)

    def _ensure_built(self) -> None:
        if not self._dirty:
            return
        self._chunk_ids = list(self._records.keys())
        corpus = [_tokenize(self._records[cid]["text"]) for cid in self._chunk_ids]
        self._bm25 = BM25Okapi(corpus) if corpus else None
        self._dirty = False

    def upsert(self, chunk_id: str, text: str, metadata: dict[str, Any]) -> None:
        self._records[chunk_id] = {"chunk_id": chunk_id, "text": text, "metadata": metadata}
        self._dirty = True
        self._persist()

    def delete_by_source(self, filepath: str) -> None:
        """Remove every chunk whose metadata['source_file'] == filepath."""
        remaining = {
            cid: record
            for cid, record in self._records.items()
            if record["metadata"].get("source_file") != filepath
        }
        if len(remaining) == len(self._records):
            return
        self._records = remaining
        self._dirty = True
        self._persist()

    def query(
        self,
        query_text: str,
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self._ensure_built()
        if self._bm25 is None:
            return []

        scores = self._bm25.get_scores(_tokenize(query_text))
        ranked = sorted(zip(self._chunk_ids, scores), key=lambda pair: pair[1], reverse=True)

        matches: list[dict[str, Any]] = []
        for chunk_id, score in ranked:
            record = self._records[chunk_id]
            if not _matches_filters(record["metadata"], filters):
                continue
            # Fold text into the returned metadata dict so callers (Retriever)
            # can read chunk text uniformly regardless of which store a
            # result came from -- VectorStore's metadata already carries it.
            metadata_with_text = {**record["metadata"], "text": record["text"]}
            matches.append({"chunk_id": chunk_id, "metadata": metadata_with_text, "score": score})
            if len(matches) >= top_k:
                break

        return matches
