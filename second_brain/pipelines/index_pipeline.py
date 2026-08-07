"""Wires ingestion -> parsing -> embedding -> storage. Runs on file change and
on full rebuild. Shares no logic with query_pipeline.py beyond EmbeddingClient.
"""

from pathlib import Path

from second_brain.embedding.client import EmbeddingClient
from second_brain.ingestion.scanner import VaultScanner
from second_brain.parsing.chunker import chunk_note
from second_brain.storage.bm25_index import BM25Index
from second_brain.storage.vector_store import VectorStore

# Lazily-created, process-wide singletons: the embedding model and both store
# connections are expensive to (re)open, and index_file/delete_file are meant
# to be called repeatedly (once per debounced file-change event).
_embedding_client: EmbeddingClient | None = None
_vector_store: VectorStore | None = None
_bm25_index: BM25Index | None = None


def _get_embedding_client() -> EmbeddingClient:
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = EmbeddingClient()
    return _embedding_client


def _get_vector_store() -> VectorStore:
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store


def _get_bm25_index() -> BM25Index:
    global _bm25_index
    if _bm25_index is None:
        _bm25_index = BM25Index()
    return _bm25_index


def index_file(path: Path, raw_text: str) -> None:
    """Index (or re-index) a single file.

    CRITICAL: delete_by_source(path) must be called on BOTH VectorStore and
    BM25Index before inserting the file's new chunks, or stale duplicate
    chunks persist and silently degrade retrieval.
    """
    source_file = str(path)
    vector_store = _get_vector_store()
    bm25_index = _get_bm25_index()

    vector_store.delete_by_source(source_file)
    bm25_index.delete_by_source(source_file)

    chunks = chunk_note(source_file, raw_text)
    if not chunks:
        return

    vectors = _get_embedding_client().embed([chunk.text for chunk in chunks])

    for chunk, vector in zip(chunks, vectors):
        metadata = {
            "source_file": chunk.source_file,
            "heading_path": chunk.heading_path,
            "tags": chunk.tags,
            "outbound_links": chunk.outbound_links,
            "text": chunk.text,
        }
        vector_store.upsert(chunk.chunk_id, vector, metadata)
        bm25_index.upsert(chunk.chunk_id, chunk.text, metadata)


def delete_file(path: Path) -> None:
    """Remove a deleted note's chunks from both stores."""
    source_file = str(path)
    _get_vector_store().delete_by_source(source_file)
    _get_bm25_index().delete_by_source(source_file)


def full_rebuild(vault_path: Path) -> None:
    """Walk the whole vault (via VaultScanner) and index every note."""
    for path, raw_text in VaultScanner(vault_path).scan():
        index_file(path, raw_text)
