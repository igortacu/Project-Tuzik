"""Compresses a raw conversation transcript into a durable note, or signals
that nothing in it was worth saving.

A distinct task from the chat persona in config.SYSTEM_PROMPT -- this gets
its own, narrower system prompt rather than reusing Murzik's. Used by the
periodic vault-save job in bot/telegram_bot.py.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime

from second_brain import config

SUMMARIZER_SYSTEM_PROMPT = (
    "You extract durable, worth-remembering information from a conversation "
    f"transcript between {config.ASSISTANT_NAME} and {config.OWNER_NAME} (or another "
    "authorized user). Durable means: personal facts, decisions, plans, preferences, "
    "or information that would be useful to recall in a future conversation -- not "
    "the back-and-forth of getting there, not questions already answered from "
    "existing notes, not small talk, and NOT a request to set a reminder -- reminders "
    "are stored and fired separately, so a note recording that one was set would just "
    "be redundant clutter.\n\n"
    "If nothing in the transcript is worth saving permanently, respond with exactly: "
    f"{config.PERIODIC_SAVE_NOTHING_SENTINEL}\n"
    "Nothing else in that case -- no explanation, no punctuation, just that exact "
    "string.\n\n"
    "Otherwise, respond in exactly this format:\n\n"
    "CATEGORY: <one of: " + ", ".join(config.VAULT_CATEGORIES) + ">\n"
    "FILENAME: <short-kebab-case-topic.md>\n"
    "TAGS: <comma-separated tags, optional>\n"
    "---\n"
    "<the actual note content, written in third person like an entry in someone's "
    "own notes -- not a transcript, not a summary of \"what was discussed\">"
)

_DEFAULT_CATEGORY = "Misc"
_STRUCTURED_HEADER_KEYS = {"CATEGORY", "FILENAME", "TAGS"}


@dataclass
class SummarizedNote:
    category: str
    filename: str
    tags: list[str] = field(default_factory=list)
    content: str = ""


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


def _fallback_filename() -> str:
    return f"note-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"


def _split_structured_note(text: str) -> tuple[str, str] | None:
    """Splits only the explicit summarizer header/body format.

    A prose horizontal rule in free-form fallback content must not be treated
    as the structured delimiter, or the content before it gets silently lost.
    """
    lines = text.split("\n")
    for index, line in enumerate(lines):
        if not re.fullmatch(r"-{3,}[ \t]*", line):
            continue

        header_lines = lines[:index]
        if not header_lines:
            return None

        saw_header = False
        for header_line in header_lines:
            if not header_line.strip():
                continue
            key, sep, _value = header_line.partition(":")
            if not sep or key.strip().upper() not in _STRUCTURED_HEADER_KEYS:
                return None
            saw_header = True

        if not saw_header:
            return None

        return "\n".join(header_lines), "\n".join(lines[index + 1 :])

    return None


def parse_summarizer_output(compressed: str) -> SummarizedNote:
    """Parses the CATEGORY/FILENAME/TAGS/--- format SUMMARIZER_SYSTEM_PROMPT
    instructs the model to produce. Never raises -- a malformed or
    incomplete response degrades to a safe fallback (category Misc, a
    timestamp-derived filename, the raw text as content) rather than losing
    the save entirely.
    """
    text = compressed.strip().replace("\r\n", "\n").replace("\r", "\n")
    parts = _split_structured_note(text)
    if parts is None:
        return SummarizedNote(
            category=_DEFAULT_CATEGORY,
            filename=_fallback_filename(),
            tags=[_DEFAULT_CATEGORY.lower()],
            content=text,
        )
    header, body = parts

    category_lookup = {c.lower(): c for c in config.VAULT_CATEGORIES}
    category = _DEFAULT_CATEGORY
    filename = _fallback_filename()
    tags: list[str] = []
    for line in header.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().upper()
        value = value.strip()
        if key == "CATEGORY" and value.lower() in category_lookup:
            category = category_lookup[value.lower()]
        elif key == "FILENAME" and value:
            filename = value if value.endswith(".md") else f"{value}.md"
        elif key == "TAGS" and value:
            tags = [t.strip() for t in value.split(",") if t.strip()]

    if not tags:
        tags = [category.lower()]

    return SummarizedNote(category=category, filename=filename, tags=tags, content=body.strip())
