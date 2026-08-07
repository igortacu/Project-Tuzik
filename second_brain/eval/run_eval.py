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


@dataclass
class EvalResult:
    question: EvalQuestion
    retrieved_sources: list[str]
    hit: bool


@dataclass
class EvalReport:
    results: list[EvalResult]
    recall: float  # fraction of questions where expected_source was retrieved


def run_eval(top_k: int | None = None) -> EvalReport:
    resolved_top_k = top_k if top_k is not None else config.TOP_K
    retriever = Retriever(EmbeddingClient(), VectorStore(), BM25Index())

    results: list[EvalResult] = []
    for question in QUESTIONS:
        chunks = retriever.retrieve(question.question, resolved_top_k)
        retrieved_sources = [chunk.metadata.get("source_file", "") for chunk in chunks]
        results.append(
            EvalResult(
                question=question,
                retrieved_sources=retrieved_sources,
                hit=question.expected_source in retrieved_sources,
            )
        )

    recall = sum(r.hit for r in results) / len(results) if results else 0.0
    return EvalReport(results=results, recall=recall)


if __name__ == "__main__":
    report = run_eval()
    for result in report.results:
        status = "HIT " if result.hit else "MISS"
        print(
            f"[{status}] {result.question.question!r} "
            f"expected={result.question.expected_source!r} "
            f"retrieved={result.retrieved_sources}"
        )
    hits = sum(r.hit for r in report.results)
    print(f"\nRecall: {report.recall:.2%} ({hits}/{len(report.results)})")
