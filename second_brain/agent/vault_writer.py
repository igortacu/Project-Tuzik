"""Restricted write access to the Obsidian vault.

Murzik may only create or append to files under config.MURZIK_NOTES_DIR --
never anywhere else in the vault. It may also edit existing Markdown files in
the vault by exact text replacement. There is no delete-file function anywhere
in this module: that isn't a permission check to bypass, the capability simply
doesn't exist in the API surface.
"""

from datetime import date
from pathlib import Path

import yaml

from second_brain import config
from second_brain.parsing.frontmatter import parse_frontmatter
from second_brain.pipelines import index_pipeline


class VaultWriteError(RuntimeError):
    """Raised when a write is attempted outside the allowed subfolder, or
    the vault path isn't configured.
    """


def _notes_dir() -> Path:
    notes_dir = (_vault_root() / config.MURZIK_NOTES_DIR).resolve()
    notes_dir.mkdir(parents=True, exist_ok=True)
    return notes_dir


def _vault_root() -> Path:
    if not config.VAULT_PATH:
        raise VaultWriteError("OBSIDIAN_VAULT_PATH not set in .env")
    return Path(config.VAULT_PATH).resolve()


def _safe_path(filename: str) -> Path:
    """Resolves filename against the notes dir and verifies the result is
    still strictly inside it -- blocks "../" traversal (or an absolute path)
    regardless of what filename the model produces.
    """
    notes_dir = _notes_dir()
    candidate = (notes_dir / filename).resolve()
    if candidate == notes_dir or notes_dir not in candidate.parents:
        raise VaultWriteError(
            f"refusing to write outside {config.MURZIK_NOTES_DIR}/: {filename!r}"
        )
    return candidate


def _safe_existing_markdown_path(filename: str) -> Path:
    """Resolves filename against the vault root and verifies the result is an
    existing Markdown file inside the vault.
    """
    vault_root = _vault_root()
    candidate = (vault_root / filename).resolve()
    if candidate == vault_root or vault_root not in candidate.parents:
        raise VaultWriteError(f"refusing to edit outside vault: {filename!r}")
    if candidate.suffix.lower() != ".md":
        raise VaultWriteError(f"refusing to edit non-Markdown file: {filename!r}")
    if not candidate.is_file():
        raise VaultWriteError(f"refusing to create missing vault note: {filename!r}")
    return candidate


def _render_frontmatter(metadata: dict) -> str:
    return "---\n" + yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True) + "---\n"


def _has_usable_frontmatter(parsed) -> bool:
    """True if parsed frontmatter is present, parsed cleanly, and non-empty
    -- the condition under which it's safe to read/rewrite it. A malformed
    or empty frontmatter block is left alone rather than risking data loss.
    """
    return (
        parsed.has_frontmatter
        and not parsed.parse_error
        and isinstance(parsed.metadata, dict)
        and bool(parsed.metadata)
    )


def append_note(
    category: str, filename: str, content: str, tags: list[str] | None = None
) -> Path:
    """Create Murzik Notes/<category>/<filename> if it doesn't exist, else
    append content as a new paragraph and bump the note's frontmatter
    "updated" date. Re-indexes the file afterward so it's immediately
    retrievable. Returns the path written.
    """
    if category not in config.VAULT_CATEGORIES:
        raise VaultWriteError(
            f"unknown category {category!r}; must be one of {config.VAULT_CATEGORIES}"
        )
    if "/" in filename or "\\" in filename:
        raise VaultWriteError(f"filename must not contain a path separator: {filename!r}")

    path = _safe_path(f"{category}/{filename}")
    path.parent.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    already_has_content = path.exists() and path.stat().st_size > 0

    if already_has_content:
        existing_raw = path.read_text(encoding="utf-8")
        parsed = parse_frontmatter(existing_raw)
        if _has_usable_frontmatter(parsed):
            metadata = dict(parsed.metadata)
            body = parsed.body
        else:
            metadata = {"tags": tags or [category.lower()], "created": today, "source": "murzik"}
            body = existing_raw
        metadata["updated"] = today
        new_body = body.rstrip("\n") + "\n\n" + content.strip() + "\n"
        full_text = _render_frontmatter(metadata) + new_body
    else:
        metadata = {
            "tags": tags or [category.lower()],
            "created": today,
            "updated": today,
            "source": "murzik",
        }
        full_text = _render_frontmatter(metadata) + content.strip() + "\n"

    path.write_text(full_text, encoding="utf-8")
    index_pipeline.index_file(path, full_text)
    return path


def edit_existing_note(filename: str, old_text: str, new_text: str) -> Path:
    """Edit an existing Markdown note by replacing exactly one text snippet.

    Refuses to create files, edit outside the vault, edit non-Markdown files,
    or replace an old_text snippet that is missing or appears multiple times.
    If the note has usable frontmatter, bumps its "updated" date -- notes
    without frontmatter (e.g. Igor's own, not Murzik's) are left structurally
    untouched. Re-indexes the file afterward so the edit is immediately
    retrievable.
    """
    if not old_text:
        raise VaultWriteError("old_text must be non-empty")

    path = _safe_existing_markdown_path(filename)
    raw_text = path.read_text(encoding="utf-8")
    count = raw_text.count(old_text)
    if count == 0:
        raise VaultWriteError("old_text was not found in the target note")
    if count > 1:
        raise VaultWriteError("old_text appears multiple times; provide a larger unique snippet")

    updated_text = raw_text.replace(old_text, new_text, 1)

    parsed = parse_frontmatter(updated_text)
    if _has_usable_frontmatter(parsed):
        metadata = dict(parsed.metadata)
        metadata["updated"] = date.today().isoformat()
        updated_text = _render_frontmatter(metadata) + parsed.body

    path.write_text(updated_text, encoding="utf-8")
    index_pipeline.index_file(path, updated_text)
    return path
