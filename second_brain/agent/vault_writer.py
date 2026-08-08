"""Restricted write access to a dedicated subfolder of the vault.

Murzik may only create or append to files under config.MURZIK_NOTES_DIR --
never anywhere else in the vault. There is no delete function anywhere in
this module: that isn't a permission check to bypass, the capability simply
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
    if not config.VAULT_PATH:
        raise VaultWriteError("OBSIDIAN_VAULT_PATH not set in .env")
    notes_dir = (Path(config.VAULT_PATH) / config.MURZIK_NOTES_DIR).resolve()
    notes_dir.mkdir(parents=True, exist_ok=True)
    return notes_dir


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
