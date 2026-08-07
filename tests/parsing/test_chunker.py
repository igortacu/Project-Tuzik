from pathlib import Path

from second_brain.parsing.chunker import (
    chunk_note,
    estimate_tokens,
    make_chunk_id,
    split_by_headings,
    split_oversized_section,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# --- estimate_tokens ---


def test_estimate_tokens_char_based():
    assert estimate_tokens("a" * 400) == 100


def test_estimate_tokens_empty_string():
    assert estimate_tokens("") == 0


# --- split_by_headings ---


def test_split_by_headings_empty_body():
    assert split_by_headings("") == []


def test_split_by_headings_whitespace_only_body():
    assert split_by_headings("   \n\n  ") == []


def test_split_by_headings_no_headings():
    body = "Just a paragraph with no heading."
    assert split_by_headings(body) == [("", "Just a paragraph with no heading.")]


def test_split_by_headings_nested_levels():
    body = "# A\ncontent a\n## B\ncontent b\n### C\ncontent c\n## D\ncontent d\n"
    assert split_by_headings(body) == [
        ("A", "content a"),
        ("A > B", "content b"),
        ("A > B > C", "content c"),
        ("A > D", "content d"),
    ]


def test_split_by_headings_duplicate_heading_text_allowed():
    body = "# P1\n## Same\ntext1\n# P2\n## Same\ntext2\n"
    assert split_by_headings(body) == [
        ("P1 > Same", "text1"),
        ("P2 > Same", "text2"),
    ]


def test_split_by_headings_empty_title_still_occupies_stack_slot():
    body = "## \ncontent\n"
    assert split_by_headings(body) == [("", "content")]


def test_split_by_headings_headings_with_no_content_produce_no_section():
    body = "# A\n## B\ncontent\n"
    assert split_by_headings(body) == [("A > B", "content")]


# --- split_oversized_section ---


def test_split_oversized_section_under_cap_returns_unchanged():
    assert split_oversized_section("short text", 300) == ["short text"]


def test_split_oversized_section_paragraph_packing():
    p1, p2, p3 = "a" * 20, "b" * 20, "c" * 20
    text = f"{p1}\n\n{p2}\n\n{p3}"

    result = split_oversized_section(text, max_tokens=10)

    assert result == [f"{p1}\n\n{p2}", p3]


def test_split_oversized_section_sentence_fallback_for_oversized_paragraph():
    paragraph = "AAAAAAAA. BBBBBBBB. CCCCCCCC."

    result = split_oversized_section(paragraph, max_tokens=4)

    assert result == ["AAAAAAAA. BBBBBBBB.", "CCCCCCCC."]


def test_split_oversized_section_hard_slice_for_unsplittable_sentence():
    text = "c" * 44

    result = split_oversized_section(text, max_tokens=10)

    assert result == ["c" * 40, "c" * 4]


def test_split_oversized_section_recursive_paragraph_then_hard_slice():
    p1, p2, p3 = "a" * 20, "b" * 20, "c" * 44
    text = f"{p1}\n\n{p2}\n\n{p3}"

    result = split_oversized_section(text, max_tokens=10)

    assert result == [f"{p1}\n\n{p2}", "c" * 40, "c" * 4]


def test_split_oversized_section_no_paragraphs_returns_as_is():
    assert split_oversized_section("   ", max_tokens=1) == ["   "]


# --- make_chunk_id ---


def test_make_chunk_id_deterministic():
    id_a = make_chunk_id("file.md", "A > B", 0)
    id_b = make_chunk_id("file.md", "A > B", 0)
    assert id_a == id_b


def test_make_chunk_id_varies_by_index():
    assert make_chunk_id("file.md", "A > B", 0) != make_chunk_id("file.md", "A > B", 1)


def test_make_chunk_id_varies_by_source_file():
    assert make_chunk_id("file.md", "A > B", 0) != make_chunk_id("other.md", "A > B", 0)


# --- chunk_note ---


def test_chunk_note_empty_body_returns_no_chunks():
    assert chunk_note("empty.md", "") == []


def test_chunk_note_whitespace_only_body_returns_no_chunks():
    assert chunk_note("empty.md", "   \n\n  ") == []


def test_chunk_note_no_headings_single_chunk():
    chunks = chunk_note("no_headings.md", "Just a paragraph with no heading.")
    assert len(chunks) == 1
    assert chunks[0].heading_path == ""
    assert chunks[0].text == "Just a paragraph with no heading."
    assert chunks[0].source_file == "no_headings.md"
    assert chunks[0].tags == []


def test_chunk_note_frontmatter_parse_error_is_non_fatal():
    raw = "---\ntags: [unclosed\n---\n# Heading\ncontent\n"
    chunks = chunk_note("bad_frontmatter.md", raw)
    assert len(chunks) == 1
    assert chunks[0].tags == []
    assert chunks[0].text == "content"


def test_chunk_note_integration_with_sample_fixture():
    raw_text = (FIXTURES_DIR / "sample_note.md").read_text()
    source_file = "career.md"

    max_tokens = 100
    chunks = chunk_note(source_file, raw_text, max_tokens=max_tokens)

    # every chunk carries the note-wide frontmatter tags and source file
    assert all(chunk.tags == ["career", "interview"] for chunk in chunks)
    assert all(chunk.source_file == source_file for chunk in chunks)

    # chunk ids are unique within the note
    chunk_ids = [chunk.chunk_id for chunk in chunks]
    assert len(chunk_ids) == len(set(chunk_ids))

    # no chunk exceeds the token cap
    assert all(estimate_tokens(chunk.text) <= max_tokens for chunk in chunks)

    # the oversized "Interview Notes" section was split into more than one chunk
    interview_chunks = [
        c for c in chunks if c.heading_path == "Career > Sigmoid > Interview Notes"
    ]
    assert len(interview_chunks) > 1

    # the "Personal" section (small, no fallback needed) is a single chunk
    personal_chunks = [c for c in chunks if c.heading_path == "Career > Personal"]
    assert len(personal_chunks) == 1
    assert personal_chunks[0].outbound_links == ["Daily Journal"]

    # wikilinks in the opening sentence of Interview Notes are captured
    # per-chunk (not whole-note) on the first chunk that contains them
    assert interview_chunks[0].outbound_links == ["Jane Doe", "Sigmoid Corp"]
