from second_brain import config
from second_brain.generation.conversation_summarizer import (
    SummarizedNote,
    build_summarizer_prompt,
    build_transcript,
    is_nothing_to_save,
    parse_summarizer_output,
)


def test_build_transcript_labels_each_side_and_preserves_order():
    turns = [("q1", "a1"), ("q2", "a2")]
    transcript = build_transcript(turns)

    lines = transcript.split("\n")
    assert lines == [
        f"{config.OWNER_NAME}: q1",
        f"{config.ASSISTANT_NAME}: a1",
        f"{config.OWNER_NAME}: q2",
        f"{config.ASSISTANT_NAME}: a2",
    ]


def test_build_summarizer_prompt_includes_the_transcript():
    prompt = build_summarizer_prompt([("hello", "hi")])
    assert f"{config.OWNER_NAME}: hello" in prompt
    assert f"{config.ASSISTANT_NAME}: hi" in prompt


def test_is_nothing_to_save_matches_exact_sentinel():
    assert is_nothing_to_save(config.PERIODIC_SAVE_NOTHING_SENTINEL) is True
    assert is_nothing_to_save(f"  {config.PERIODIC_SAVE_NOTHING_SENTINEL}  ") is True


def test_is_nothing_to_save_false_for_real_content():
    assert is_nothing_to_save("Igor's birthday is March 3rd.") is False


def test_parse_summarizer_output_well_formed():
    compressed = (
        "CATEGORY: Finance\n"
        "FILENAME: investment-plans.md\n"
        "TAGS: finance, investing\n"
        "---\n"
        "Igor and Lori are investing in VWCE via Interactive Brokers."
    )

    note = parse_summarizer_output(compressed)

    assert note == SummarizedNote(
        category="Finance",
        filename="investment-plans.md",
        tags=["finance", "investing"],
        content="Igor and Lori are investing in VWCE via Interactive Brokers.",
    )


def test_parse_summarizer_output_adds_md_extension_if_missing():
    compressed = "CATEGORY: Misc\nFILENAME: some-topic\n---\ncontent"
    note = parse_summarizer_output(compressed)
    assert note.filename == "some-topic.md"


def test_parse_summarizer_output_defaults_tags_to_category_when_omitted():
    compressed = "CATEGORY: People\nFILENAME: igor.md\n---\ncontent"
    note = parse_summarizer_output(compressed)
    assert note.tags == ["people"]


def test_parse_summarizer_output_falls_back_to_misc_on_invalid_category():
    compressed = "CATEGORY: NotARealCategory\nFILENAME: topic.md\n---\ncontent"
    note = parse_summarizer_output(compressed)
    assert note.category == "Misc"
    assert note.filename == "topic.md"
    assert note.content == "content"


def test_parse_summarizer_output_falls_back_completely_on_malformed_response():
    note = parse_summarizer_output("just some free-form prose with no structure at all")

    assert note.category == "Misc"
    assert note.filename.endswith(".md")
    assert note.content == "just some free-form prose with no structure at all"


def test_parse_summarizer_output_never_raises_on_empty_string():
    note = parse_summarizer_output("")
    assert note.category == "Misc"
    assert note.content == ""


def test_parse_summarizer_output_tolerates_trailing_whitespace_on_separator():
    compressed = "CATEGORY: Finance\nFILENAME: topic.md\n---  \ncontent"
    note = parse_summarizer_output(compressed)
    assert note.category == "Finance"
    assert note.filename == "topic.md"
    assert note.content == "content"


def test_parse_summarizer_output_tolerates_crlf_line_endings():
    compressed = "CATEGORY: Finance\r\nFILENAME: topic.md\r\n---\r\ncontent"
    note = parse_summarizer_output(compressed)
    assert note.category == "Finance"
    assert note.filename == "topic.md"
    assert note.content == "content"


def test_parse_summarizer_output_matches_category_case_insensitively():
    compressed = "CATEGORY: finance\nFILENAME: topic.md\n---\ncontent"
    note = parse_summarizer_output(compressed)
    assert note.category == "Finance"


def test_parse_summarizer_output_does_not_lose_content_before_a_prose_horizontal_rule():
    compressed = (
        "Igor decided to move to Spain.\n\n---\n\nHe also bought a car."
    )
    note = parse_summarizer_output(compressed)
    assert note.category == "Misc"
    assert "Igor decided to move to Spain." in note.content
    assert "He also bought a car." in note.content
