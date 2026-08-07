"""Split a note's body into chunks by heading (H1-H3), preserving heading path
as context, with a max token cap per chunk enforced via paragraph/sentence/
character-level fallback splitting for oversized sections.
"""

import hashlib
import re
from dataclasses import dataclass

from second_brain import config
from second_brain.parsing.frontmatter import normalize_tags, parse_frontmatter
from second_brain.parsing.wikilinks import extract_wikilinks

_HEADING_RE = re.compile(rf"^(#{{1,{config.CHUNK_HEADING_MAX_LEVEL}}})\s+(.*)$")
_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Chunk:
    text: str
    source_file: str
    heading_path: str
    tags: list[str]
    outbound_links: list[str]  # links found in THIS chunk's text, not whole-note
    chunk_id: str


def estimate_tokens(text: str) -> int:
    """Cheap char-based token approximation (no tokenizer dependency)."""
    return len(text) // config.CHARS_PER_TOKEN_APPROX


def split_by_headings(body: str) -> list[tuple[str, str]]:
    """Split body into (heading_path, section_text) pairs at H1-H(CHUNK_HEADING_MAX_LEVEL)
    boundaries. Content before the first heading (or an entirely headingless
    note) is returned with heading_path=''. An empty/whitespace-only body
    yields no sections.
    """
    if not body.strip():
        return []

    stack: list[tuple[int, str]] = []
    sections: list[tuple[str, str]] = []
    current_lines: list[str] = []

    def flush() -> None:
        text = "\n".join(current_lines).strip("\n")
        if text.strip():
            heading_path = " > ".join(title for _, title in stack if title)
            sections.append((heading_path, text))

    for line in body.split("\n"):
        match = _HEADING_RE.match(line)
        if match:
            flush()
            current_lines = []
            level = len(match.group(1))
            title = match.group(2).strip()
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
        else:
            current_lines.append(line)
    flush()

    return sections


def _greedy_pack(units: list[str], max_tokens: int, joiner: str) -> list[str]:
    packed: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for unit in units:
        unit_tokens = estimate_tokens(unit)
        if not current:
            current = [unit]
            current_tokens = unit_tokens
        elif current_tokens + unit_tokens <= max_tokens:
            current.append(unit)
            current_tokens += unit_tokens
        else:
            packed.append(joiner.join(current))
            current = [unit]
            current_tokens = unit_tokens
    if current:
        packed.append(joiner.join(current))
    return packed


def _hard_slice(text: str, max_tokens: int) -> list[str]:
    """Character-slice at the token-cap boundary, preferring to break at the
    nearest preceding whitespace within the last ~10% of the window so words
    aren't cut in half.
    """
    max_chars = max_tokens * config.CHARS_PER_TOKEN_APPROX
    if max_chars <= 0:
        return [text]

    pieces: list[str] = []
    remaining = text
    while len(remaining) > max_chars:
        window = remaining[:max_chars]
        search_start = int(max_chars * 0.9)
        break_at = window.rfind(" ", search_start)
        if break_at == -1:
            break_at = max_chars
        pieces.append(remaining[:break_at].rstrip())
        remaining = remaining[break_at:].lstrip()
    if remaining:
        pieces.append(remaining)
    return pieces


def _split_paragraph(paragraph: str, max_tokens: int) -> list[str]:
    """A single paragraph that alone exceeds the cap: fall back to
    sentence-boundary splitting, then character-level hard slicing if even a
    single sentence still overflows (e.g. an unbroken code block).
    """
    sentences = [s for s in _SENTENCE_SPLIT_RE.split(paragraph.strip()) if s.strip()]
    if len(sentences) <= 1:
        return _hard_slice(paragraph, max_tokens)

    packed = _greedy_pack(sentences, max_tokens, joiner=" ")
    result: list[str] = []
    for piece in packed:
        if estimate_tokens(piece) <= max_tokens:
            result.append(piece)
        else:
            result.extend(_hard_slice(piece, max_tokens))
    return result


def split_oversized_section(section_text: str, max_tokens: int) -> list[str]:
    """Enforce max_tokens on a section, falling back through paragraph ->
    sentence -> hard character-slice boundaries as needed.
    """
    if estimate_tokens(section_text) <= max_tokens:
        return [section_text]

    paragraphs = [p for p in _PARAGRAPH_SPLIT_RE.split(section_text.strip()) if p.strip()]
    if not paragraphs:
        return [section_text]

    packed = _greedy_pack(paragraphs, max_tokens, joiner="\n\n")

    result: list[str] = []
    for piece in packed:
        if estimate_tokens(piece) <= max_tokens:
            result.append(piece)
        else:
            # Greedy packing always isolates an over-cap paragraph into its
            # own piece, so this is exactly one oversized paragraph.
            result.extend(_split_paragraph(piece, max_tokens))
    return result


def make_chunk_id(source_file: str, heading_path: str, index: int) -> str:
    """Deterministic given (source_file, heading_path, index). Determinism is
    a nice-to-have for reproducible tests/log correlation, not a correctness
    requirement: index_pipeline always calls delete_by_source(filepath) before
    re-inserting a file's chunks, so id collisions/shifts across re-indexes of
    the same file are never a correctness issue.
    """
    raw = f"{source_file}|{heading_path}|{index}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def chunk_note(source_file: str, raw_text: str, max_tokens: int | None = None) -> list[Chunk]:
    """Parse frontmatter, split the body by heading, enforce the token cap
    per section, and return the flat ordered list of chunks for this note.

    An empty/whitespace-only body yields zero chunks (not an error) -- the
    caller should treat this as "delete_by_source + nothing to insert".
    """
    resolved_max_tokens = (
        max_tokens if max_tokens is not None else config.CHUNK_MAX_TOKENS
    )

    frontmatter_result = parse_frontmatter(raw_text)
    tags = normalize_tags(frontmatter_result.metadata)
    sections = split_by_headings(frontmatter_result.body)

    chunks: list[Chunk] = []
    index = 0
    for heading_path, section_text in sections:
        for piece in split_oversized_section(section_text, resolved_max_tokens):
            piece = piece.strip("\n")
            if not piece.strip():
                continue
            outbound_links = [link.target for link in extract_wikilinks(piece)]
            chunks.append(
                Chunk(
                    text=piece,
                    source_file=source_file,
                    heading_path=heading_path,
                    tags=tags,
                    outbound_links=outbound_links,
                    chunk_id=make_chunk_id(source_file, heading_path, index),
                )
            )
            index += 1

    return chunks
