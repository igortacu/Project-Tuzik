from second_brain.retrieval.retriever import Retriever


class _FakeEmbeddingClient:
    def embed(self, texts):
        return [[0.0] for _ in texts]


class _FakeStore:
    """Duck-typed stand-in for VectorStore/BM25Index -- query() ignores its
    positional args and always returns the fixed result list it was built
    with, so tests can focus purely on Retriever's RRF merge logic.
    """

    def __init__(self, results):
        self._results = results

    def query(self, *args, **kwargs):
        return self._results


def _make_retriever(vector_results, bm25_results, rrf_k=60):
    return Retriever(
        embedding_client=_FakeEmbeddingClient(),
        vector_store=_FakeStore(vector_results),
        bm25_index=_FakeStore(bm25_results),
        rrf_k=rrf_k,
    )


def test_no_results_from_either_store():
    retriever = _make_retriever([], [])
    assert retriever.retrieve("query", top_k=5) == []


def test_result_only_in_vector_store_is_included():
    vector_results = [{"chunk_id": "c1", "metadata": {"text": "v1"}, "score": 0.1}]
    retriever = _make_retriever(vector_results, [])

    results = retriever.retrieve("query", top_k=5)

    assert [r.chunk_id for r in results] == ["c1"]
    assert results[0].text == "v1"


def test_result_appearing_in_both_stores_ranks_higher_than_single_store_hits():
    vector_results = [
        {"chunk_id": "c1", "metadata": {"text": "v1"}, "score": 0.1},
        {"chunk_id": "c2", "metadata": {"text": "v2"}, "score": 0.2},
    ]
    bm25_results = [
        {"chunk_id": "c2", "metadata": {"text": "v2b"}, "score": 5.0},
        {"chunk_id": "c3", "metadata": {"text": "v3"}, "score": 3.0},
    ]
    retriever = _make_retriever(vector_results, bm25_results, rrf_k=60)

    results = retriever.retrieve("query", top_k=3)

    # c2 (rank 2 in vector + rank 1 in bm25) outranks c1 (rank 1 in vector
    # only) and c3 (rank 2 in bm25 only).
    assert [r.chunk_id for r in results] == ["c2", "c1", "c3"]


def test_metadata_from_first_store_that_surfaced_the_chunk_wins():
    vector_results = [{"chunk_id": "c1", "metadata": {"text": "from-vector"}, "score": 0.1}]
    bm25_results = [{"chunk_id": "c1", "metadata": {"text": "from-bm25"}, "score": 5.0}]
    retriever = _make_retriever(vector_results, bm25_results)

    results = retriever.retrieve("query", top_k=5)

    assert results[0].text == "from-vector"


def test_top_k_truncates_merged_results():
    vector_results = [
        {"chunk_id": f"c{i}", "metadata": {"text": f"v{i}"}, "score": 0.1} for i in range(5)
    ]
    retriever = _make_retriever(vector_results, [])

    results = retriever.retrieve("query", top_k=2)

    assert len(results) == 2
