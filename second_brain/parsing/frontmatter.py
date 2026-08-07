"""Extract YAML frontmatter (tags, date, aliases) from a note's raw text."""

import re
from dataclasses import dataclass
from typing import Any

import yaml

# Opening/closing delimiter lines allow trailing spaces/tabs but not newlines,
# so [ \t]* is used instead of \s* to keep the line-boundary semantics exact.
# \A anchors to the start of the (already \n-normalized) string. The closing
# delimiter is matched via MULTILINE ^ rather than folding a \n into the body
# group, so an empty block ("---\n---\n", zero content lines) still matches --
# folding \n into the body group would force at least one line of content.
_FRONTMATTER_RE = re.compile(
    r"\A---[ \t]*\n(.*?)^---[ \t]*\n?", re.DOTALL | re.MULTILINE
)


@dataclass
class FrontmatterResult:
    metadata: dict[str, Any]
    body: str
    has_frontmatter: bool
    parse_error: str | None


def parse_frontmatter(raw_text: str) -> FrontmatterResult:
    """Split raw note text into YAML frontmatter metadata and the remaining body.

    Never raises: malformed YAML, non-mapping YAML, and missing/unterminated
    delimiter blocks are all reported via the returned FrontmatterResult
    rather than an exception, so a single bad note can't crash indexing.
    """
    normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    match = _FRONTMATTER_RE.match(normalized)

    if not match:
        # No opening delimiter at all, or an opening delimiter with no
        # matching closing delimiter anywhere in the file. In both cases we
        # can't safely infer frontmatter was intended, so treat the whole
        # file as body text, unchanged.
        return FrontmatterResult(
            metadata={}, body=raw_text, has_frontmatter=False, parse_error=None
        )

    yaml_block = match.group(1)
    body = normalized[match.end() :]

    try:
        parsed = yaml.safe_load(yaml_block)
    except yaml.YAMLError as exc:
        return FrontmatterResult(
            metadata={}, body=body, has_frontmatter=True, parse_error=str(exc)
        )

    if parsed is None:
        # Empty block, or a block containing only comments.
        return FrontmatterResult(
            metadata={}, body=body, has_frontmatter=True, parse_error=None
        )

    if not isinstance(parsed, dict):
        return FrontmatterResult(
            metadata={},
            body=body,
            has_frontmatter=True,
            parse_error=f"frontmatter did not parse to a mapping (got {type(parsed).__name__})",
        )

    return FrontmatterResult(
        metadata=parsed, body=body, has_frontmatter=True, parse_error=None
    )


def normalize_tags(metadata: dict[str, Any]) -> list[str]:
    """Normalize the frontmatter 'tags' field into a flat, deduped list of
    plain strings, regardless of whether it was authored as a YAML list, a
    single word, or a comma/space-separated string.
    """
    raw = metadata.get("tags")
    if raw is None:
        return []

    if isinstance(raw, list):
        candidates = [str(item) for item in raw]
    elif isinstance(raw, str):
        if "," in raw:
            candidates = raw.split(",")
        elif any(ch.isspace() for ch in raw):
            candidates = raw.split()
        else:
            candidates = [raw]
    else:
        candidates = [str(raw)]

    tags: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        tag = candidate.strip().lstrip("#").strip()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)
    return tags
