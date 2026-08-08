"""Formats retrieved chunks into a context block for the LLM prompt.

Persona, tone, and citation/formatting rules live in config.SYSTEM_PROMPT
(sent as the system-role message) -- this module only builds the user-role
turn: retrieved context plus the question.
"""

from second_brain.retrieval.retriever import RetrievedChunk


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

    return f"Context:\n{context_block}\n\nQuestion: {query}\nAnswer:"
