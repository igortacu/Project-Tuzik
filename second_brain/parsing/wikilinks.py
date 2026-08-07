"""Extract [[Note Name]] and [[Note Name|alias]] outbound links from note body text."""

import re
from dataclasses import dataclass

# Excluding \n from the character class (not just [ and ]) is deliberate: it
# bounds a link attempt to a single line, so an unclosed "[[Note Name" can
# never greedily consume text up to an unrelated "]]" found later in the file.
_WIKILINK_RE = re.compile(r"\[\[([^\[\]\n]+)\]\]")


@dataclass
class WikiLink:
    raw: str
    target: str
    alias: str | None
    start: int
    end: int


def extract_wikilinks(body: str) -> list[WikiLink]:
    """Extract all [[Note Name]] / [[Note Name|alias]] links from body text.

    Heading/block references ([[Note#Heading]], [[Note#^blockid]]) have the
    target truncated at the first '#'. Links with an empty target after
    stripping (e.g. [[]], [[|alias]]) are skipped. Known limitation: links
    inside fenced code blocks are still extracted (no code-fence stripping).
    """
    links: list[WikiLink] = []
    for match in _WIKILINK_RE.finditer(body):
        group = match.group(1)
        left, _sep, right = group.partition("|")

        alias = right.strip() or None

        target_raw = left.strip()
        target = target_raw.split("#", 1)[0].strip() if "#" in target_raw else target_raw

        if not target:
            continue

        links.append(
            WikiLink(
                raw=match.group(0),
                target=target,
                alias=alias,
                start=match.start(),
                end=match.end(),
            )
        )
    return links
