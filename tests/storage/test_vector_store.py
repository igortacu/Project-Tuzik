from pathlib import Path

from second_brain.storage.vector_store import VectorStore


def _make_store(tmp_path: Path) -> VectorStore:
    return VectorStore(persist_path=str(tmp_path / "chroma"))


def test_upsert_and_query_returns_nearest_vector(tmp_path):
    store = _make_store(tmp_path)
    store.upsert("c1", [1.0, 0.0, 0.0], {"source_file": "a.md", "text": "chunk a"})
    store.upsert("c2", [0.0, 1.0, 0.0], {"source_file": "b.md", "text": "chunk b"})

    results = store.query([1.0, 0.0, 0.0], top_k=1)

    assert results[0]["chunk_id"] == "c1"
    assert results[0]["metadata"]["text"] == "chunk a"


def test_delete_by_source_removes_only_matching_chunks(tmp_path):
    store = _make_store(tmp_path)
    store.upsert("c1", [1.0, 0.0, 0.0], {"source_file": "a.md", "text": "chunk a"})
    store.upsert("c2", [0.0, 1.0, 0.0], {"source_file": "b.md", "text": "chunk b"})

    store.delete_by_source("a.md")

    results = store.query([1.0, 0.0, 0.0], top_k=5)
    assert [r["chunk_id"] for r in results] == ["c2"]


def test_delete_by_source_before_reinsert_prevents_stale_duplicates(tmp_path):
    store = _make_store(tmp_path)
    store.upsert("c1", [1.0, 0.0, 0.0], {"source_file": "a.md", "text": "old chunk"})

    store.delete_by_source("a.md")
    store.upsert("c1-new", [1.0, 0.0, 0.0], {"source_file": "a.md", "text": "new chunk"})

    results = store.query([1.0, 0.0, 0.0], top_k=5)
    assert [r["chunk_id"] for r in results] == ["c1-new"]


def test_query_respects_tag_filter(tmp_path):
    store = _make_store(tmp_path)
    store.upsert(
        "c1", [1.0, 0.0, 0.0], {"source_file": "a.md", "text": "career chunk", "tags": ["career"]}
    )
    store.upsert(
        "c2", [1.0, 0.0, 0.0], {"source_file": "b.md", "text": "personal chunk", "tags": ["personal"]}
    )

    results = store.query([1.0, 0.0, 0.0], top_k=5, filters={"tags": "career"})

    assert [r["chunk_id"] for r in results] == ["c1"]


def test_list_metadata_values_are_serialized_to_strings(tmp_path):
    store = _make_store(tmp_path)
    store.upsert(
        "c1",
        [1.0, 0.0, 0.0],
        {"source_file": "a.md", "text": "x", "tags": ["a", "b"], "outbound_links": ["Note X"]},
    )

    results = store.query([1.0, 0.0, 0.0], top_k=1)

    assert results[0]["metadata"]["tags"] == "a,b"
    assert results[0]["metadata"]["outbound_links"] == "Note X"
