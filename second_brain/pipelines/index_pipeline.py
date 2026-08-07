"""Wires ingestion -> parsing -> embedding -> storage. Runs on file change and
on full rebuild. Shares no logic with query_pipeline.py beyond EmbeddingClient.
"""

from pathlib import Path


def index_file(path: Path, raw_text: str) -> None:
    """Index (or re-index) a single file.

    CRITICAL: delete_by_source(path) must be called on BOTH VectorStore and
    BM25Index before inserting the file's new chunks, or stale duplicate
    chunks persist and silently degrade retrieval.
    """
    raise NotImplementedError


def delete_file(path: Path) -> None:
    """Remove a deleted note's chunks from both stores."""
    raise NotImplementedError


def full_rebuild(vault_path: Path) -> None:
    """Walk the whole vault (via VaultScanner) and index every note."""
    raise NotImplementedError
