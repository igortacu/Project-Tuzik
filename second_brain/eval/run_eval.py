"""Runs eval.test_questions.QUESTIONS through query_pipeline and reports which
source notes were retrieved vs expected, so retrieval quality can be measured
before/after chunking or embedding changes.
"""

from dataclasses import dataclass

from second_brain.eval.test_questions import EvalQuestion


@dataclass
class EvalResult:
    question: EvalQuestion
    retrieved_sources: list[str]
    hit: bool


@dataclass
class EvalReport:
    results: list[EvalResult]
    recall: float  # fraction of questions where expected_source was retrieved


def run_eval(top_k: int = 5) -> EvalReport:
    raise NotImplementedError
