# Structured Vault Writes for Murzik Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Murzik's unstructured vault writes (one growing per-chat chronological log, ad-hoc filenames, no frontmatter) with a fixed-but-extensible category/frontmatter structure.

**Architecture:** A fixed list of categories (`config.VAULT_CATEGORIES`) constrains the folder a note can live in; `vault_writer.append_note` composes the path and manages YAML frontmatter itself rather than trusting the model to. The periodic-save summarizer switches from free prose to a small structured text format that's deterministically parsed into category/filename/tags/content.

**Tech Stack:** Python 3.10, pytest, PyYAML (already a dependency), the existing `second_brain.parsing.frontmatter` module.

## Global Constraints

- `config.VAULT_CATEGORIES = ["People", "Finance", "Projects", "Life", "Misc"]` — a plain list, extensible by editing this one place, never by the model inventing a new folder name.
- `append_note`'s new signature is `append_note(category: str, filename: str, content: str, tags: list[str] | None = None) -> Path` — this is a breaking change with no backward-compat shim (small personal project, no external callers besides this codebase).
- Every note Murzik creates gets frontmatter: `tags`, `created`, `updated`, `source: murzik`. On append to an existing note, `created`/`tags` are preserved, only `updated` changes.
- `edit_existing_note` can still target any Markdown file in the vault (unchanged scope) — it only bumps `updated` if the target already has frontmatter, never forces this schema onto a file that didn't already have one.
- Periodic saves must never crash or silently lose a real save due to a parsing hiccup in the summarizer's output — malformed output degrades to a safe fallback (category `Misc`, a timestamp-derived filename), never an exception.
- Reminder-setting exchanges are never treated as vault-note-worthy by the periodic-save summarizer.
- Full spec: `docs/superpowers/specs/2026-08-11-vault-structure-design.md`.

---

### Task 1: config.VAULT_CATEGORIES + append_note rewrite (category, frontmatter, path composition)

**Files:**
- Modify: `second_brain/config.py`
- Modify: `second_brain/agent/vault_writer.py`
- Test: `tests/agent/test_vault_writer.py` (rewrite — every existing `append_note` call needs the new signature)

**Interfaces:**
- Consumes: `second_brain.parsing.frontmatter.parse_frontmatter(raw_text) -> FrontmatterResult(metadata, body, has_frontmatter, parse_error)` (already exists, do not modify).
- Produces: `append_note(category: str, filename: str, content: str, tags: list[str] | None = None) -> Path`, raising `VaultWriteError` for an unknown category, a `filename` containing `/` or `\`, path traversal, or a missing `VAULT_PATH` (all pre-existing behaviors extended, not replaced). `_render_frontmatter(metadata: dict) -> str` (private helper Task 2 also uses).

- [ ] **Step 1: Add the category list to config**

Add to `second_brain/config.py`, near `MURZIK_NOTES_DIR`:

```python
# Fixed set of folders Murzik's own vault writes can land in -- extensible
# by editing this list, never by the model inventing a new folder name on
# the fly. See docs/superpowers/specs/2026-08-11-vault-structure-design.md.
VAULT_CATEGORIES = ["People", "Finance", "Projects", "Life", "Misc"]
```

- [ ] **Step 2: Rewrite `tests/agent/test_vault_writer.py`**

Replace the entire file with:

```python
from datetime import date

import pytest
import yaml

from second_brain import config
from second_brain.agent import vault_writer


@pytest.fixture(autouse=True)
def _isolated_vault(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "VAULT_PATH", str(tmp_path))
    # index_file requires the full embedding/storage stack -- not what these
    # tests are about, so replace it with a no-op and just assert it's called.
    calls = []
    monkeypatch.setattr(
        "second_brain.pipelines.index_pipeline.index_file",
        lambda path, raw_text: calls.append((path, raw_text)),
    )
    return tmp_path, calls


def _read_frontmatter(path):
    raw = path.read_text(encoding="utf-8")
    assert raw.startswith("---\n")
    _, _, rest = raw.partition("---\n")
    yaml_block, _, body = rest.partition("---\n")
    return yaml.safe_load(yaml_block), body


def test_append_note_creates_new_file_with_frontmatter(_isolated_vault):
    tmp_path, calls = _isolated_vault

    path = vault_writer.append_note("Finance", "topic.md", "First fact.")

    assert path == tmp_path / config.MURZIK_NOTES_DIR / "Finance" / "topic.md"
    metadata, body = _read_frontmatter(path)
    assert metadata["tags"] == ["finance"]
    assert metadata["created"] == date.today().isoformat()
    assert metadata["updated"] == date.today().isoformat()
    assert metadata["source"] == "murzik"
    assert body == "First fact.\n"
    assert len(calls) == 1
    assert calls[0][0] == path


def test_append_note_uses_explicit_tags_when_given(_isolated_vault):
    path = vault_writer.append_note("Finance", "topic.md", "content", tags=["investing", "etf"])

    metadata, _ = _read_frontmatter(path)
    assert metadata["tags"] == ["investing", "etf"]


def test_append_note_rejects_unknown_category(_isolated_vault):
    with pytest.raises(vault_writer.VaultWriteError, match="unknown category"):
        vault_writer.append_note("NotACategory", "topic.md", "content")


@pytest.mark.parametrize("category", config.VAULT_CATEGORIES)
def test_append_note_accepts_every_fixed_category(_isolated_vault, category):
    path = vault_writer.append_note(category, "topic.md", "content")
    assert path.parent.name == category


def test_append_note_rejects_filename_with_path_separator(_isolated_vault):
    with pytest.raises(vault_writer.VaultWriteError, match="path separator"):
        vault_writer.append_note("Finance", "sub/topic.md", "content")


def test_append_note_appends_with_blank_line_separator_and_bumps_updated(_isolated_vault):
    vault_writer.append_note("Finance", "topic.md", "First fact.")

    path = vault_writer.append_note("Finance", "topic.md", "Second fact.")

    metadata, body = _read_frontmatter(path)
    assert body == "First fact.\n\nSecond fact.\n"
    assert metadata["updated"] == date.today().isoformat()


def test_append_note_preserves_created_and_tags_on_append(_isolated_vault):
    vault_writer.append_note("Finance", "topic.md", "First fact.", tags=["etf"])

    path = vault_writer.append_note("Finance", "topic.md", "Second fact.")

    metadata, _ = _read_frontmatter(path)
    assert metadata["created"] == date.today().isoformat()
    assert metadata["tags"] == ["etf"]


def test_append_note_creates_notes_dir_if_missing(_isolated_vault):
    tmp_path, _ = _isolated_vault
    notes_dir = tmp_path / config.MURZIK_NOTES_DIR
    assert not notes_dir.exists()

    vault_writer.append_note("Misc", "topic.md", "content")

    assert notes_dir.is_dir()


@pytest.mark.parametrize(
    "filename",
    [
        "../outside.md",
        "../../etc/passwd",
        "/etc/passwd",
        "..",
    ],
)
def test_append_note_rejects_path_traversal(_isolated_vault, filename):
    tmp_path, _ = _isolated_vault

    with pytest.raises(vault_writer.VaultWriteError):
        vault_writer.append_note("Misc", filename, "content")

    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert config.MURZIK_NOTES_DIR in path.parts


def test_append_note_requires_vault_path(monkeypatch):
    monkeypatch.setattr(config, "VAULT_PATH", None)

    with pytest.raises(vault_writer.VaultWriteError):
        vault_writer.append_note("Misc", "topic.md", "content")


# --- edit_existing_note (Task 2 adds frontmatter-bump behavior) ---


def test_edit_existing_note_replaces_unique_snippet(_isolated_vault):
    tmp_path, calls = _isolated_vault
    path = tmp_path / "project.md"
    path.write_text("Docker is wanted.\nWedding is pending.\n", encoding="utf-8")

    edited = vault_writer.edit_existing_note("project.md", "Docker is wanted.", "Docker is done.")

    assert edited == path
    assert path.read_text(encoding="utf-8") == "Docker is done.\nWedding is pending.\n"
    assert calls[-1] == (path, "Docker is done.\nWedding is pending.\n")


def test_edit_existing_note_allows_subfolders(_isolated_vault):
    tmp_path, _ = _isolated_vault
    folder = tmp_path / "Projects"
    folder.mkdir()
    path = folder / "lucauto.md"
    path.write_text("status: old\n", encoding="utf-8")

    vault_writer.edit_existing_note("Projects/lucauto.md", "old", "done")

    assert path.read_text(encoding="utf-8") == "status: done\n"


@pytest.mark.parametrize("filename", ["missing.md", "notes.txt"])
def test_edit_existing_note_refuses_create_or_non_markdown(_isolated_vault, filename):
    with pytest.raises(vault_writer.VaultWriteError):
        vault_writer.edit_existing_note(filename, "old", "new")


@pytest.mark.parametrize("filename", ["../outside.md", "/etc/passwd"])
def test_edit_existing_note_rejects_path_traversal(_isolated_vault, filename):
    with pytest.raises(vault_writer.VaultWriteError):
        vault_writer.edit_existing_note(filename, "old", "new")


def test_edit_existing_note_rejects_missing_snippet(_isolated_vault):
    tmp_path, _ = _isolated_vault
    (tmp_path / "project.md").write_text("one thing\n", encoding="utf-8")

    with pytest.raises(vault_writer.VaultWriteError, match="not found"):
        vault_writer.edit_existing_note("project.md", "other thing", "new thing")


def test_edit_existing_note_rejects_ambiguous_snippet(_isolated_vault):
    tmp_path, _ = _isolated_vault
    (tmp_path / "project.md").write_text("same\nsame\n", encoding="utf-8")

    with pytest.raises(vault_writer.VaultWriteError, match="multiple"):
        vault_writer.edit_existing_note("project.md", "same", "new")


def test_edit_existing_note_requires_non_empty_old_text(_isolated_vault):
    tmp_path, _ = _isolated_vault
    (tmp_path / "project.md").write_text("same\n", encoding="utf-8")

    with pytest.raises(vault_writer.VaultWriteError, match="non-empty"):
        vault_writer.edit_existing_note("project.md", "", "new")
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `pytest tests/agent/test_vault_writer.py -v`
Expected: FAIL — `append_note()` doesn't accept a `category` argument yet (`TypeError`), and the frontmatter-reading tests fail since no frontmatter is written yet.

- [ ] **Step 4: Rewrite `second_brain/agent/vault_writer.py`**

Replace the file's imports and `append_note` function (leave `VaultWriteError`, `_notes_dir`, `_vault_root`, `_safe_path`, `_safe_existing_markdown_path` unchanged):

```python
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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/agent/test_vault_writer.py -v`
Expected: PASS, all tests green.

- [ ] **Step 6: Run the full suite**

Run: `pytest -v`
Expected: FAIL only in `tests/agent/test_tools.py` (still calling the old `append_note(filename, content)` signature) and possibly `tests/bot/test_telegram_bot.py` (`_compress_and_save_chat` tests) -- both fixed in later tasks. Confirm no *other* file fails.

- [ ] **Step 7: Commit**

```bash
git add second_brain/config.py second_brain/agent/vault_writer.py tests/agent/test_vault_writer.py
git commit -m "feat: enforce categories and frontmatter on Murzik's vault writes"
```

---

### Task 2: edit_existing_note frontmatter-bump verification

**Files:**
- Test: `tests/agent/test_vault_writer.py` (append new tests -- `edit_existing_note`'s frontmatter-bump behavior was already implemented in Task 1's rewrite; this task adds the tests that were deferred to keep Task 1 focused on `append_note`)

**Interfaces:**
- Consumes: `vault_writer.append_note` (Task 1, to create a note with real frontmatter to then edit) and `vault_writer.edit_existing_note` (Task 1's already-modified version).
- Produces: nothing new for later tasks -- this task is pure verification of behavior Task 1 already implemented.

- [ ] **Step 1: Write the failing tests**

Append to `tests/agent/test_vault_writer.py`:

```python
def test_edit_existing_note_bumps_updated_when_frontmatter_present(_isolated_vault, monkeypatch):
    path = vault_writer.append_note("Projects", "status.md", "Status: in progress.")

    # Simulate the note having been created on an earlier day so the bump
    # is actually observable rather than a no-op equal-to-today comparison.
    metadata, body = _read_frontmatter(path)
    metadata["created"] = "2020-01-01"
    metadata["updated"] = "2020-01-01"
    path.write_text(vault_writer._render_frontmatter(metadata) + body, encoding="utf-8")

    vault_writer.edit_existing_note("Projects/status.md", "in progress", "done")

    new_metadata, new_body = _read_frontmatter(path)
    assert new_metadata["updated"] == date.today().isoformat()
    assert new_metadata["created"] == "2020-01-01"
    assert "Status: done." in new_body


def test_edit_existing_note_leaves_notes_without_frontmatter_untouched(_isolated_vault):
    tmp_path, _ = _isolated_vault
    path = tmp_path / "plain.md"
    path.write_text("Docker is wanted.\n", encoding="utf-8")

    vault_writer.edit_existing_note("plain.md", "wanted", "done")

    result = path.read_text(encoding="utf-8")
    assert result == "Docker is done.\n"
    assert not result.startswith("---")
```

- [ ] **Step 2: Run the tests**

Run: `pytest tests/agent/test_vault_writer.py -k "frontmatter_present or without_frontmatter" -v`
Expected: PASS -- Task 1's `edit_existing_note` already implements this behavior, so no implementation changes are needed in this task, only these two verifying tests.

If either test unexpectedly fails, that means Task 1's implementation has a bug -- fix `second_brain/agent/vault_writer.py`'s `edit_existing_note` to match the docstring behavior described in Task 1 before proceeding.

- [ ] **Step 3: Run the full `test_vault_writer.py` file**

Run: `pytest tests/agent/test_vault_writer.py -v`
Expected: PASS, all tests green (Task 1's tests plus these two new ones).

- [ ] **Step 4: Commit**

```bash
git add tests/agent/test_vault_writer.py
git commit -m "test: verify edit_existing_note's frontmatter-bump behavior"
```

---

### Task 3: tools.py schema + execute_tool changes

**Files:**
- Modify: `second_brain/agent/tools.py`
- Test: `tests/agent/test_tools.py`

**Interfaces:**
- Consumes: `vault_writer.append_note(category, filename, content, tags=None)` (Task 1).
- Produces: `append_vault_note` tool now requires `category` and accepts optional `tags` in its arguments; `execute_tool`'s branch passes both through.

- [ ] **Step 1: Write the failing tests**

In `tests/agent/test_tools.py`, replace the existing `test_execute_tool_append_vault_note` and `test_execute_tool_append_vault_note_missing_argument` with:

```python
def test_execute_tool_append_vault_note():
    with patch(
        "second_brain.agent.vault_writer.append_note",
        return_value="/vault/Murzik Notes/Projects/project_updates.md",
    ) as mock_append:
        result = tools.execute_tool(
            "append_vault_note",
            {
                "category": "Projects",
                "filename": "project_updates.md",
                "content": "Docker is deployed.",
            },
            [],
        )

    mock_append.assert_called_once_with(
        "Projects", "project_updates.md", "Docker is deployed.", None
    )
    assert "Saved to vault note" in result
    assert "project_updates.md" in result


def test_execute_tool_append_vault_note_with_tags():
    with patch(
        "second_brain.agent.vault_writer.append_note",
        return_value="/vault/Murzik Notes/Finance/investing.md",
    ) as mock_append:
        tools.execute_tool(
            "append_vault_note",
            {
                "category": "Finance",
                "filename": "investing.md",
                "content": "ETF plan.",
                "tags": ["etf", "investing"],
            },
            [],
        )

    mock_append.assert_called_once_with(
        "Finance", "investing.md", "ETF plan.", ["etf", "investing"]
    )


def test_execute_tool_append_vault_note_missing_category():
    result = tools.execute_tool(
        "append_vault_note",
        {"filename": "project_updates.md", "content": "x"},
        [],
    )

    assert "missing required argument" in result


def test_execute_tool_append_vault_note_missing_content():
    result = tools.execute_tool(
        "append_vault_note",
        {"category": "Misc", "filename": "project_updates.md"},
        [],
    )

    assert "missing required argument" in result
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/agent/test_tools.py -k append_vault_note -v`
Expected: FAIL -- the schema and `execute_tool` branch don't handle `category`/`tags` yet.

- [ ] **Step 3: Update the tool schema**

In `second_brain/agent/tools.py`, add the import at the top:

```python
from second_brain import config
```

Replace the `append_vault_note` entry in `TOOLS_SCHEMA`:

```python
    {
        "type": "function",
        "function": {
            "name": "append_vault_note",
            "description": "Create or append a Markdown note under Igor's restricted "
            "Murzik Notes/ vault folder, organized by category. Use only when Igor "
            "explicitly asks to remember, save, note down, or update notes with new "
            "information. This cannot edit or delete arbitrary existing vault files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": config.VAULT_CATEGORIES,
                        "description": "Pick the closest fit; use Misc if nothing fits.",
                    },
                    "filename": {
                        "type": "string",
                        "description": "Bare Markdown filename (no folders), e.g. "
                        "investment-plans.md. No path separators or ../ traversal.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Concise Markdown content to append.",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional extra tags beyond the category itself.",
                    },
                },
                "required": ["category", "filename", "content"],
            },
        },
    },
```

- [ ] **Step 4: Update the `execute_tool` branch**

Replace the existing `append_vault_note` branch in `execute_tool`:

```python
    if name == "append_vault_note":
        try:
            path = vault_writer.append_note(
                arguments["category"],
                arguments["filename"],
                arguments["content"],
                arguments.get("tags"),
            )
        except KeyError as exc:
            return f"Vault write failed: missing required argument {exc.args[0]!r}."
        except vault_writer.VaultWriteError as exc:
            return f"Vault write failed: {exc}"
        return f"Saved to vault note: {path}"
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/agent/test_tools.py -v`
Expected: PASS, all tests in the file green.

- [ ] **Step 6: Run the full suite**

Run: `pytest -v`
Expected: FAIL only in `tests/bot/test_telegram_bot.py`'s `_compress_and_save_chat` tests (fixed in Task 5). Confirm nothing else fails.

- [ ] **Step 7: Commit**

```bash
git add second_brain/agent/tools.py tests/agent/test_tools.py
git commit -m "feat: require category (and accept tags) on the append_vault_note tool"
```

---

### Task 4: Structured summarizer output + parse_summarizer_output

**Files:**
- Modify: `second_brain/generation/conversation_summarizer.py`
- Test: `tests/generation/test_conversation_summarizer.py`

**Interfaces:**
- Consumes: `config.VAULT_CATEGORIES` (Task 1).
- Produces: `SummarizedNote` dataclass (`category: str`, `filename: str`, `tags: list[str]`, `content: str`); `parse_summarizer_output(compressed: str) -> SummarizedNote` (never raises). Task 5 consumes both.

- [ ] **Step 1: Write the failing tests**

Add to `tests/generation/test_conversation_summarizer.py` (keep the existing tests unchanged, add these):

```python
from second_brain.generation.conversation_summarizer import (
    SummarizedNote,
    build_summarizer_prompt,
    build_transcript,
    is_nothing_to_save,
    parse_summarizer_output,
)


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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/generation/test_conversation_summarizer.py -v`
Expected: FAIL -- `SummarizedNote`/`parse_summarizer_output` don't exist yet.

- [ ] **Step 3: Implement**

Replace `second_brain/generation/conversation_summarizer.py`'s `SUMMARIZER_SYSTEM_PROMPT` and add the new dataclass and function:

```python
"""Compresses a raw conversation transcript into a durable note, or signals
that nothing in it was worth saving.

A distinct task from the chat persona in config.SYSTEM_PROMPT -- this gets
its own, narrower system prompt rather than reusing Murzik's. Used by the
periodic vault-save job in bot/telegram_bot.py.
"""

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


def parse_summarizer_output(compressed: str) -> SummarizedNote:
    """Parses the CATEGORY/FILENAME/TAGS/--- format SUMMARIZER_SYSTEM_PROMPT
    instructs the model to produce. Never raises -- a malformed or
    incomplete response degrades to a safe fallback (category Misc, a
    timestamp-derived filename, the raw text as content) rather than losing
    the save entirely.
    """
    text = compressed.strip()
    header, separator, body = text.partition("\n---\n")
    if not separator:
        return SummarizedNote(
            category=_DEFAULT_CATEGORY,
            filename=_fallback_filename(),
            tags=[_DEFAULT_CATEGORY.lower()],
            content=text,
        )

    category = _DEFAULT_CATEGORY
    filename = _fallback_filename()
    tags: list[str] = []
    for line in header.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().upper()
        value = value.strip()
        if key == "CATEGORY" and value in config.VAULT_CATEGORIES:
            category = value
        elif key == "FILENAME" and value:
            filename = value if value.endswith(".md") else f"{value}.md"
        elif key == "TAGS" and value:
            tags = [t.strip() for t in value.split(",") if t.strip()]

    if not tags:
        tags = [category.lower()]

    return SummarizedNote(category=category, filename=filename, tags=tags, content=body.strip())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/generation/test_conversation_summarizer.py -v`
Expected: PASS, all tests green (existing ones plus the new ones).

- [ ] **Step 5: Run the full suite**

Run: `pytest -v`
Expected: FAIL only in `tests/bot/test_telegram_bot.py`'s `_compress_and_save_chat` tests (fixed in Task 5).

- [ ] **Step 6: Commit**

```bash
git add second_brain/generation/conversation_summarizer.py tests/generation/test_conversation_summarizer.py
git commit -m "feat: structured category/filename output from the periodic-save summarizer"
```

---

### Task 5: Wire _compress_and_save_chat to the new flow

**Files:**
- Modify: `second_brain/bot/telegram_bot.py`
- Test: `tests/bot/test_telegram_bot.py`

**Interfaces:**
- Consumes: `parse_summarizer_output` (Task 4), `vault_writer.append_note(category, filename, content, tags)` (Task 1).
- Produces: nothing new for later tasks -- Task 6 is live verification only.

- [ ] **Step 1: Write the failing test**

In `tests/bot/test_telegram_bot.py`, replace `test_compress_and_save_chat_writes_when_something_to_save` with:

```python
def test_compress_and_save_chat_writes_when_something_to_save():
    fake_path = Path("/vault/Murzik Notes/People/igor.md")
    summarizer_output = (
        "CATEGORY: People\n"
        "FILENAME: igor.md\n"
        "TAGS: birthday\n"
        "---\n"
        "Igor's birthday is March 3rd."
    )
    with (
        patch(
            "second_brain.bot.telegram_bot._summarizer_llm_client.generate",
            return_value=summarizer_output,
        ),
        patch(
            "second_brain.bot.telegram_bot.vault_writer.append_note", return_value=fake_path
        ) as mock_append,
    ):
        asyncio.run(
            telegram_bot._compress_and_save_chat(
                123, [("my birthday is march 3", "noted, in a manner of speaking")]
            )
        )

    mock_append.assert_called_once_with(
        "People", "igor.md", "Igor's birthday is March 3rd.", ["birthday"]
    )
```

(`test_compress_and_save_chat_skips_when_nothing_to_save` is unchanged -- leave it as-is.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/bot/test_telegram_bot.py -k compress_and_save_chat -v`
Expected: FAIL -- `_compress_and_save_chat` still calls `vault_writer.append_note` with the old `(filename, content)` signature.

- [ ] **Step 3: Update the import and implementation**

In `second_brain/bot/telegram_bot.py`, update the import from `conversation_summarizer`:

```python
from second_brain.generation.conversation_summarizer import (
    SUMMARIZER_SYSTEM_PROMPT,
    build_summarizer_prompt,
    is_nothing_to_save,
    parse_summarizer_output,
)
```

Replace `_compress_and_save_chat`:

```python
async def _compress_and_save_chat(chat_id: int, turns: list[tuple[str, str]]) -> None:
    prompt = build_summarizer_prompt(turns)
    compressed = await asyncio.to_thread(
        _summarizer_llm_client.generate, prompt, system_prompt=SUMMARIZER_SYSTEM_PROMPT
    )

    if is_nothing_to_save(compressed):
        logger.info(
            "Periodic save: nothing worth saving for chat_id=%s (%d turns)", chat_id, len(turns)
        )
        return

    note = parse_summarizer_output(compressed)
    path = await asyncio.to_thread(
        vault_writer.append_note, note.category, note.filename, note.content, note.tags
    )
    logger.info(
        "Periodic save: wrote %d turns to %s (category=%s)", len(turns), path, note.category
    )
```

If `datetime` is no longer used anywhere else in `telegram_bot.py` after removing the old timestamp-heading line, remove its now-unused import; if it's still used elsewhere in the file (check with `grep -n "datetime" second_brain/bot/telegram_bot.py`), leave the import as-is.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/bot/test_telegram_bot.py -v`
Expected: PASS, all tests in the file green.

- [ ] **Step 5: Run the full suite**

Run: `pytest -v`
Expected: PASS, full green suite, no regressions anywhere.

- [ ] **Step 6: Commit**

```bash
git add second_brain/bot/telegram_bot.py tests/bot/test_telegram_bot.py
git commit -m "feat: route periodic saves through categorized, frontmattered notes"
```

---

### Task 6: Live verification

**Files:** none (verification-only task; fix in the relevant earlier task's files if something surfaces a real bug, with its own normal commit, not folded into this task).

**Interfaces:**
- Consumes: the fully wired feature from Tasks 1-5, deployed and running (this project deploys to a VPS via `git pull && docker compose up -d --build`, per `docs/deploy-runbook.md`'s "Future Code Updates" section -- push to origin first, then pull+rebuild on the VPS).

- [ ] **Step 1: Deploy the change**

Push to origin, then on the VPS: `ssh root@37.27.32.169 'cd /opt/murzik && git pull --ff-only && docker compose up -d --build'`. Confirm clean startup via `docker compose logs murzik --tail 15` (no traceback, normal `Starting Telegram bot (long-polling)...` / job-registration lines).

- [ ] **Step 2: Explicit save in two different categories**

Send Murzik two separate explicit "remember this" requests that clearly belong to different categories (e.g. a personal fact about someone -> People, a project status update -> Projects). Confirm each reply says the note was saved. Then check the actual vault files on the Mac (Obsidian, or `ls "/Users/igortacu/Desktop/TuzikVault/TuzikVault/Murzik Notes/"`) once Syncthing has propagated: confirm two separate files exist under the correct category subfolders, each with a real frontmatter block at the top (`tags`, `created`, `updated`, `source: murzik`) and the actual content below it.

- [ ] **Step 3: Real periodic save**

Have a real conversation with Murzik containing something durable (not a reminder). Wait for the next periodic save (or trigger one manually if that's faster during testing). Confirm the resulting note lands under a sensible category subfolder with correct frontmatter, not in a flat `conversation_<chat_id>.md` file.

- [ ] **Step 4: Confirm reminder-setting produces no vault note**

Set a reminder via Murzik. Wait for the next periodic save to run. Confirm no new vault note was created for that exchange (check `docker compose logs murzik --tail 50` on the VPS for a `Periodic save: nothing worth saving` log line, or confirm no unexpected new file appears in the vault).

- [ ] **Step 5: No commit needed for this task itself** -- if any step surfaces a real bug, fix it in the relevant file from Tasks 1-5 and commit that fix separately with a normal descriptive message.
