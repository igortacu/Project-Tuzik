from pathlib import Path

from second_brain.storage.bm25_index import BM25Index


def _make_index(tmp_path: Path) -> BM25Index:
    return BM25Index(persist_path=str(tmp_path / "bm25.json"))


def test_query_empty_index_returns_no_results(tmp_path):
    index = _make_index(tmp_path)
    assert index.query("anything", top_k=5) == []


def test_upsert_and_query_finds_matching_chunk(tmp_path):
    index = _make_index(tmp_path)
    index.upsert("c1", "The interview went well at Sigmoid Corp.", {"source_file": "a.md"})
    index.upsert("c2", "Grocery list: eggs, milk, bread.", {"source_file": "b.md"})

    results = index.query("Sigmoid Corp interview", top_k=5)

    assert results[0]["chunk_id"] == "c1"
    assert results[0]["metadata"]["text"] == "The interview went well at Sigmoid Corp."


def test_upsert_overwrites_existing_chunk_id(tmp_path):
    index = _make_index(tmp_path)
    index.upsert("c1", "original text", {"source_file": "a.md"})
    index.upsert("c1", "updated text", {"source_file": "a.md"})

    results = index.query("updated", top_k=5)

    assert len(results) == 1
    assert results[0]["metadata"]["text"] == "updated text"


def test_delete_by_source_removes_only_matching_chunks(tmp_path):
    index = _make_index(tmp_path)
    index.upsert("c1", "note a content", {"source_file": "a.md"})
    index.upsert("c2", "note b content", {"source_file": "b.md"})

    index.delete_by_source("a.md")

    remaining_ids = {r["chunk_id"] for r in index.query("content", top_k=5)}
    assert remaining_ids == {"c2"}


def test_delete_by_source_before_reinsert_prevents_stale_duplicates(tmp_path):
    index = _make_index(tmp_path)
    index.upsert("c1", "old chunk for note a", {"source_file": "a.md"})

    index.delete_by_source("a.md")
    index.upsert("c1-new", "new chunk for note a", {"source_file": "a.md"})

    results = index.query("chunk note a", top_k=5)
    assert [r["chunk_id"] for r in results] == ["c1-new"]


def test_query_respects_tag_filter(tmp_path):
    index = _make_index(tmp_path)
    index.upsert("c1", "career notes about interviews", {"source_file": "a.md", "tags": ["career"]})
    index.upsert("c2", "personal notes about interviews", {"source_file": "b.md", "tags": ["personal"]})

    results = index.query("interviews", top_k=5, filters={"tags": "career"})

    assert [r["chunk_id"] for r in results] == ["c1"]


def test_persistence_reloads_across_instances(tmp_path):
    persist_path = str(tmp_path / "bm25.json")
    first = BM25Index(persist_path=persist_path)
    first.upsert("c1", "persisted chunk text", {"source_file": "a.md"})

    second = BM25Index(persist_path=persist_path)
    results = second.query("persisted chunk", top_k=5)

    assert [r["chunk_id"] for r in results] == ["c1"]
