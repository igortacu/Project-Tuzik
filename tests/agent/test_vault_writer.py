import pytest

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


def test_append_note_creates_new_file(_isolated_vault):
    tmp_path, calls = _isolated_vault

    path = vault_writer.append_note("topic.md", "First fact.")

    assert path == tmp_path / config.MURZIK_NOTES_DIR / "topic.md"
    assert path.read_text() == "First fact.\n"
    assert len(calls) == 1
    assert calls[0][0] == path


def test_append_note_appends_with_blank_line_separator(_isolated_vault):
    vault_writer.append_note("topic.md", "First fact.")
    path = vault_writer.append_note("topic.md", "Second fact.")

    assert path.read_text() == "First fact.\n\nSecond fact.\n"


def test_append_note_creates_notes_dir_if_missing(_isolated_vault):
    tmp_path, _ = _isolated_vault
    notes_dir = tmp_path / config.MURZIK_NOTES_DIR
    assert not notes_dir.exists()

    vault_writer.append_note("topic.md", "content")

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
        vault_writer.append_note(filename, "content")

    # nothing written anywhere outside the notes dir
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert config.MURZIK_NOTES_DIR in path.parts


def test_append_note_requires_vault_path(monkeypatch):
    monkeypatch.setattr(config, "VAULT_PATH", None)

    with pytest.raises(vault_writer.VaultWriteError):
        vault_writer.append_note("topic.md", "content")


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
