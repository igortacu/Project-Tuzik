"""Formats retrieved chunks into a context block for the LLM prompt."""

from second_brain.retrieval.retriever import RetrievedChunk

_INSTRUCTIONS = (
    "You are answering a question using the notes below. Cite the source "
    "filename for any claim you make. If the notes don't contain the "
    "answer, say so."
)


def build_prompt(query: str, chunks: list[RetrievedChunk]) -> str:
    """Format retrieved chunks (with source filenames, so answers can cite
    sources) plus the user query into a single prompt string.
    """
    if not chunks:
        context_block = "(no relevant notes found)"
    else:
        sections = []
        for chunk in chunks:
            source = chunk.metadata.get("source_file", "unknown")
            heading_path = chunk.metadata.get("heading_path", "")
            header = f"Source: {source}" + (f" ({heading_path})" if heading_path else "")
            sections.append(f"{header}\n{chunk.text}")
        context_block = "\n\n---\n\n".join(sections)

    return f"{_INSTRUCTIONS}\n\nContext:\n{context_block}\n\nQuestion: {query}\nAnswer:"
