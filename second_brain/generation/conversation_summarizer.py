"""Compresses a raw conversation transcript into a durable note, or signals
that nothing in it was worth saving.

A distinct task from the chat persona in config.SYSTEM_PROMPT -- this gets
its own, narrower system prompt rather than reusing Murzik's. Used by the
periodic vault-save job in bot/telegram_bot.py.
"""

from second_brain import config

SUMMARIZER_SYSTEM_PROMPT = (
    "You extract durable, worth-remembering information from a conversation "
    f"transcript between {config.ASSISTANT_NAME} and {config.OWNER_NAME} (or another "
    "authorized user). Durable means: personal facts, decisions, plans, preferences, "
    "or information that would be useful to recall in a future conversation -- not "
    "the back-and-forth of getting there, not questions already answered from "
    "existing notes, not small talk. Write it as a concise markdown note in third "
    "person, like an entry in someone's own notes -- not a transcript, not a summary "
    "of \"what was discussed.\"\n\n"
    "If nothing in the transcript is worth saving permanently, respond with exactly: "
    f"{config.PERIODIC_SAVE_NOTHING_SENTINEL}\n"
    "Nothing else in that case -- no explanation, no punctuation, just that exact "
    "string."
)


def build_transcript(turns: list[tuple[str, str]]) -> str:
    """turns is [(user_message, assistant_reply), ...] in order."""
    lines = []
    for user_message, assistant_reply in turns:
        lines.append(f"{config.OWNER_NAME}: {user_message}")
        lines.append(f"{config.ASSISTANT_NAME}: {assistant_reply}")
    return "\n".join(lines)


def build_summarizer_prompt(turns: list[tuple[str, str]]) -> str:
    return f"Transcript:\n{build_transcript(turns)}\n\nExtract what's worth saving:"


def is_nothing_to_save(compressed: str) -> bool:
    return compressed.strip() == config.PERIODIC_SAVE_NOTHING_SENTINEL
