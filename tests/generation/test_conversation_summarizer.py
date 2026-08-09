from second_brain import config
from second_brain.generation.conversation_summarizer import (
    build_summarizer_prompt,
    build_transcript,
    is_nothing_to_save,
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
