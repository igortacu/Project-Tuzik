"""Runs eval.test_questions.QUESTIONS through the retriever and reports which
source notes were retrieved vs expected, so retrieval quality can be measured
before/after chunking or embedding changes.

Deliberately talks to the Retriever directly rather than routing through
pipelines.query_pipeline: answer_query() only returns a final answer string,
with no way to inspect which source notes were actually used, and this is a
retrieval-quality diagnostic that shouldn't need (or pay for) an LLM call.
"""

from dataclasses import dataclass

from second_brain import config
from second_brain.embedding.client import EmbeddingClient
from second_brain.eval.test_questions import QUESTIONS, EvalQuestion
from second_brain.retrieval.retriever import Retriever
from second_brain.storage.bm25_index import BM25Index
from second_brain.storage.vector_store import VectorStore

# Sentinel expected_source for negative-control questions ("should retrieve
# nothing / low confidence"). Not scored: retrieval always returns top_k
# results regardless of relevance (there's no confidence threshold anywhere
# in the pipeline), so there's no automatic way to check "retrieved nothing".
_NEGATIVE_CONTROL = "NONE"


@dataclass
class EvalResult:
    question: EvalQuestion
    retrieved_sources: list[str]
    # None: negative control, or expected_source not filled in yet -- not
    # scored, reported for manual review instead.
    hit: bool | None


@dataclass
class EvalReport:
    results: list[EvalResult]
    recall: float  # fraction of *scored* questions where expected_source was retrieved


def run_eval(top_k: int | None = None) -> EvalReport:
    resolved_top_k = top_k if top_k is not None else config.TOP_K
    retriever = Retriever(EmbeddingClient(), VectorStore(), BM25Index())

    results: list[EvalResult] = []
    for question in QUESTIONS:
        chunks = retriever.retrieve(question.question, resolved_top_k)
        retrieved_sources = [chunk.metadata.get("source_file", "") for chunk in chunks]

        if not question.expected_source or question.expected_source == _NEGATIVE_CONTROL:
            hit = None
        elif isinstance(question.expected_source, list):
            # Multi-note question: the answer genuinely requires pulling
            # chunks from every listed note, not just one of them.
            hit = all(src in retrieved_sources for src in question.expected_source)
        else:
            hit = question.expected_source in retrieved_sources

        results.append(EvalResult(question=question, retrieved_sources=retrieved_sources, hit=hit))

    scored = [r for r in results if r.hit is not None]
    recall = sum(r.hit for r in scored) / len(scored) if scored else 0.0
    return EvalReport(results=results, recall=recall)


if __name__ == "__main__":
    report = run_eval()
    for result in report.results:
        status = "SKIP" if result.hit is None else ("HIT " if result.hit else "MISS")
        print(
            f"[{status}] {result.question.question!r} "
            f"expected={result.question.expected_source!r} "
            f"retrieved={result.retrieved_sources}"
        )
    scored = [r for r in report.results if r.hit is not None]
    hits = sum(r.hit for r in scored)
    skipped = len(report.results) - len(scored)
    print(f"\nRecall: {report.recall:.2%} ({hits}/{len(scored)} scored, {skipped} skipped)")
