"""Formats retrieved chunks into a context block for the LLM prompt."""

from second_brain.retrieval.retriever import RetrievedChunk


def build_prompt(query: str, chunks: list[RetrievedChunk]) -> str:
    """Format retrieved chunks (with source filenames, so answers can cite
    sources) plus the user query into a single prompt string.
    """
    raise NotImplementedError
