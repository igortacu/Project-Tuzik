"""Restricted write access to the Obsidian vault.

Murzik may only create or append to files under config.MURZIK_NOTES_DIR --
never anywhere else in the vault. It may also edit existing Markdown files in
the vault by exact text replacement. There is no delete-file function anywhere
in this module: that isn't a permission check to bypass, the capability simply
doesn't exist in the API surface.
"""

from pathlib import Path

from second_brain import config
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


def append_note(filename: str, content: str) -> Path:
    """Create filename under Murzik Notes/ if it doesn't exist, else append
    content as a new paragraph. Re-indexes the file afterward so it's
    immediately retrievable. Returns the path written.
    """
    path = _safe_path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)

    already_has_content = path.exists() and path.stat().st_size > 0
    with open(path, "a", encoding="utf-8") as f:
        if already_has_content:
            # append_note always leaves the file ending in a single "\n", so
            # one more "\n" here produces exactly one blank line between
            # paragraphs, not two.
            f.write("\n")
        f.write(content.strip() + "\n")

    index_pipeline.index_file(path, path.read_text(encoding="utf-8"))
    return path


def edit_existing_note(filename: str, old_text: str, new_text: str) -> Path:
    """Edit an existing Markdown note by replacing exactly one text snippet.

    Refuses to create files, edit outside the vault, edit non-Markdown files,
    or replace an old_text snippet that is missing or appears multiple times.
    Re-indexes the file afterward so the edit is immediately retrievable.
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
    path.write_text(updated_text, encoding="utf-8")

    index_pipeline.index_file(path, updated_text)
    return path
