# Structured Vault Writes for Murzik — Design

## Context

Murzik's own vault writes (`second_brain/agent/vault_writer.py`'s `append_note`/`edit_existing_note`, and the periodic conversation-save job in `second_brain/bot/telegram_bot.py`) have no enforced structure. In practice this produced a messy `Murzik Notes/` folder: one giant per-chat chronological log (`conversation_<chat_id>.md`) mixing unrelated topics (deployment status, personal facts, investment plans, a reminder confirmation) under datestamped headings with inconsistent formatting, plus ad-hoc explicit-save files with no naming convention (`deployment_verification.md` next to `personal_igor_loredana.md`) and no frontmatter at all — despite the RAG pipeline already parsing and filtering on YAML frontmatter (`second_brain/parsing/frontmatter.py`) for every other note in the vault.

Reminders now have their own durable store (`ReminderStore`, see `docs/superpowers/specs/2026-08-10-reminders-design.md`), making it redundant for the periodic-save summarizer to also write a vault note recording that a reminder was set.

## Decisions

- **Organize by topic, not by chat.** A save about "Investment Plans" always lands in/updates the same note regardless of which chat or day it was discussed in, instead of accumulating chronologically in a per-chat log.
- **Enforced YAML frontmatter** on every note Murzik creates or appends to, using the RAG pipeline's existing `tags` field convention so these notes are filterable the same way the rest of the vault already is.
- **Topic subfolders under `Murzik Notes/`**, not a flat folder.
- **A fixed, enumerated category list** controls the subfolders — extensible by editing `config.py`, never by the model inventing a new folder name on the fly. This is what "fixed but extensible" means concretely, and it's the direct fix for how today's ad-hoc filenames happened.
- **Reminder-setting exchanges are excluded from periodic saves** — the reminder itself is the durable record now.
- **Migrating the 4 existing messy notes is explicitly out of scope** — this design governs what Murzik writes going forward only.

## Categories

`config.VAULT_CATEGORIES = ["People", "Finance", "Projects", "Life", "Misc"]` — derived from what's actually in the vault today (personal facts about named people, financial/investment planning, technical/dev project status, trip/preference/goal notes, and a catch-all for anything that doesn't fit). A plain list in `config.py`; adding a category later is a one-line edit, not a code change.

## Path structure

`Murzik Notes/<Category>/<filename>.md`, e.g. `Murzik Notes/Finance/investment-plans.md`, `Murzik Notes/People/igor-loredana.md`.

The model supplies `category` (tool-schema-enum-constrained to `config.VAULT_CATEGORIES` — an invalid value is a hard tool error, not silently accepted or auto-corrected) and a bare `filename` with no `/` in it. `vault_writer.py` composes the full nested path itself from validated parts, rather than trusting the model to spell a folder path correctly by hand every time — this is the actual mechanism that prevents the ad-hoc-filename drift from recurring.

## Frontmatter

Added by `vault_writer.py` itself, not left to the model to include in the `content` it sends:

```yaml
---
tags: [finance, investing]
created: 2026-08-11
updated: 2026-08-11
source: murzik
---
```

- `tags`: reuses `second_brain.parsing.frontmatter.normalize_tags()`'s existing field convention. The tool schema takes an optional `tags` list from the model; if omitted, defaults to `[category.lower()]`.
- `created`/`updated`: both set to today's date (`datetime.now().date().isoformat()`) on first creation of a note.
- `source: murzik`: distinguishes Murzik-authored notes from Igor's own, for future filtering.

**On append to an existing Murzik-authored note**: `vault_writer.py` parses the existing frontmatter via `parse_frontmatter()`, preserves `created` and `tags` unchanged, updates only `updated` to today's date, and re-serializes the frontmatter block before writing the file back with the new content appended to the body.

**`edit_existing_note`** can target *any* Markdown file in the vault (not just Murzik's own — this is unchanged from today). It bumps `updated` in the frontmatter only if the target file already has a frontmatter block; it never forces this schema onto a file that didn't already have one, since many of those are Igor's own notes with their own conventions.

## Component changes

**`second_brain/config.py`**: add `VAULT_CATEGORIES = ["People", "Finance", "Projects", "Life", "Misc"]`.

**`second_brain/agent/vault_writer.py`**:
- `append_note(category: str, filename: str, content: str, tags: list[str] | None = None) -> Path` — validates `category` against `config.VAULT_CATEGORIES` (raises `VaultWriteError` if not a member), builds the path as `Murzik Notes/<category>/<filename>` via the existing `_safe_path()` (already supports nested paths via `path.parent.mkdir(parents=True, exist_ok=True)`, no changes needed there), and handles frontmatter as described above (new file: full frontmatter block; existing file: parse-preserve-`created`/`tags`-bump-`updated`).
- `edit_existing_note(filename: str, old_text: str, new_text: str) -> Path` — unchanged signature and vault-wide scope; internally, after the existing exact-replacement logic, additionally bumps `updated` in frontmatter if present.

**`second_brain/agent/tools.py`**: `append_vault_note`'s tool schema gains a required `category` parameter (`type: string, enum: config.VAULT_CATEGORIES`) and an optional `tags` parameter (`type: array of string`). `execute_tool`'s `append_vault_note` branch passes both through to `vault_writer.append_note`.

**`second_brain/generation/conversation_summarizer.py`** (periodic save): the summarizer's system prompt gains instructions to (a) never treat a reminder-setting exchange as save-worthy, and (b) when something is worth saving, pick one of the fixed categories and a short topic filename rather than defaulting to a chronological per-chat log entry. The periodic-save code path in `telegram_bot.py`'s `_compress_and_save_chat` changes from always appending to `conversation_<chat_id>.md` to calling `vault_writer.append_note` with a category/filename the summarizer's output specifies.

## Testing

- `tests/agent/test_vault_writer.py`: category validation (valid categories succeed, an invalid one raises `VaultWriteError`), path composition (`Murzik Notes/<Category>/<filename>`), frontmatter on first creation (all fields present and correct), frontmatter preservation on append (`created`/`tags` unchanged, `updated` bumped), `edit_existing_note`'s conditional `updated`-bump behavior (bumped when frontmatter exists, untouched when it doesn't).
- `tests/agent/test_tools.py`: extend `append_vault_note` tests for the new `category`/`tags` parameters, including the invalid-category error path.
- `tests/generation/test_conversation_summarizer.py` and/or `tests/bot/test_telegram_bot.py`: the periodic-save path routes through `vault_writer.append_note` with a category, and reminder-setting exchanges are excluded (this may need to be a prompt-level instruction verified live rather than a pure unit test, since "was this exchange about setting a reminder" is a judgment call made by the LLM, not deterministic code).
- Live verification: ask Murzik to remember something in each of a couple of categories, confirm the resulting files land at the correct nested paths with correct frontmatter; trigger a periodic save and confirm it also lands correctly categorized; confirm a reminder-setting exchange does NOT produce a vault note.
