"""Real Q&A pairs used to measure retrieval quality. Filled in by hand."""

from dataclasses import dataclass


@dataclass
class EvalQuestion:
    question: str
    expected_source: str  # expected source note filename (or path)


# Fill in with 15-20 real question/expected-source-note pairs.
QUESTIONS: list[EvalQuestion] = []
