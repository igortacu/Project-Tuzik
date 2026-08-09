"""Wires ingestion -> parsing -> embedding -> storage. Runs on file change and
on full rebuild.

get_embedding_client/get_vector_store/get_bm25_index are process-wide
singletons deliberately exposed (not underscore-private): query_pipeline.py
reuses these exact same instances rather than constructing its own. BM25Index
loads its records into memory once and never reloads from disk on its own --
two separate instances backed by the same JSON file would silently diverge,
so a write via one would be invisible to queries via the other for the
lifetime of the process. Sharing one instance is what makes "write, then
immediately query" work correctly within a single running bot.
"""

from pathlib import Path

from second_brain import config
from second_brain.embedding.client import EmbeddingClient
from second_brain.ingestion.scanner import VaultScanner
from second_brain.parsing.chunker import chunk_note
from second_brain.storage.bm25_index import BM25Index
from second_brain.storage.vector_store import VectorStore

_embedding_client: EmbeddingClient | None = None
_vector_store: VectorStore | None = None
_bm25_index: BM25Index | None = None


def get_embedding_client() -> EmbeddingClient:
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = EmbeddingClient()
    return _embedding_client


def get_vector_store() -> VectorStore:
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store


def get_bm25_index() -> BM25Index:
    global _bm25_index
    if _bm25_index is None:
        _bm25_index = BM25Index()
    return _bm25_index


def _relative_source(path: Path) -> str:
    """Vault-relative path used as the chunk/citation identity, e.g.
    "career_sigmoid.md" instead of an absolute, machine-specific path --
    keeps generated citations readable and eval expected_source values
    portable across machines. Falls back to the absolute path if
    config.VAULT_PATH isn't set or path isn't under it.
    """
    if config.VAULT_PATH:
        try:
            return str(Path(path).resolve().relative_to(Path(config.VAULT_PATH).resolve()))
        except ValueError:
            pass
    return str(path)


def index_file(path: Path, raw_text: str) -> None:
    """Index (or re-index) a single file.

    CRITICAL: delete_by_source(path) must be called on BOTH VectorStore and
    BM25Index before inserting the file's new chunks, or stale duplicate
    chunks persist and silently degrade retrieval.
    """
    source_file = _relative_source(path)
    vector_store = get_vector_store()
    bm25_index = get_bm25_index()

    vector_store.delete_by_source(source_file)
    bm25_index.delete_by_source(source_file)

    chunks = chunk_note(source_file, raw_text)
    if not chunks:
        return

    vectors = get_embedding_client().embed([chunk.text for chunk in chunks])

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
    source_file = _relative_source(path)
    get_vector_store().delete_by_source(source_file)
    get_bm25_index().delete_by_source(source_file)


def full_rebuild(vault_path: Path) -> None:
    """Walk the whole vault (via VaultScanner) and index every note."""
    for path, raw_text in VaultScanner(vault_path).scan():
        index_file(path, raw_text)
