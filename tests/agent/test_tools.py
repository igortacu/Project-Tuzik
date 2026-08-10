from unittest.mock import patch

from second_brain.agent import tools, web_search


def test_tools_schema_has_expected_function_names():
    names = {t["function"]["name"] for t in tools.TOOLS_SCHEMA}
    assert names == {
        "web_search",
        "image_search",
        "get_directions_link",
        "append_vault_note",
        "edit_vault_note",
        "set_reminder",
        "list_reminders",
        "cancel_reminder",
    }


def test_execute_tool_unknown_name():
    result = tools.execute_tool("nonexistent_tool", {}, [])
    assert "Unknown tool" in result


def test_execute_tool_web_search_formats_results():
    fake_results = [{"title": "T", "url": "https://x.example", "snippet": "S"}]
    with patch("second_brain.agent.web_search.search_web", return_value=fake_results):
        result = tools.execute_tool("web_search", {"query": "q"}, [])

    assert "T" in result
    assert "https://x.example" in result
    assert "S" in result


def test_execute_tool_web_search_no_results():
    with patch("second_brain.agent.web_search.search_web", return_value=[]):
        result = tools.execute_tool("web_search", {"query": "q"}, [])
    assert "No results" in result


def test_execute_tool_web_search_degrades_on_error():
    with patch(
        "second_brain.agent.web_search.search_web",
        side_effect=web_search.WebSearchError("no key"),
    ):
        result = tools.execute_tool("web_search", {"query": "q"}, [])
    assert "isn't available" in result.lower()


def test_execute_tool_image_search_populates_side_channel():
    image_urls_out = []
    with patch(
        "second_brain.agent.web_search.search_images",
        return_value=["https://img1.example", "https://img2.example"],
    ):
        result = tools.execute_tool("image_search", {"query": "cats"}, image_urls_out)

    assert image_urls_out == ["https://img1.example", "https://img2.example"]
    assert "2" in result


def test_execute_tool_image_search_no_results_leaves_side_channel_empty():
    image_urls_out = []
    with patch("second_brain.agent.web_search.search_images", return_value=[]):
        result = tools.execute_tool("image_search", {"query": "cats"}, image_urls_out)

    assert image_urls_out == []
    assert "No images" in result


def test_execute_tool_image_search_degrades_on_error():
    with patch(
        "second_brain.agent.web_search.search_images",
        side_effect=web_search.WebSearchError("no key"),
    ):
        result = tools.execute_tool("image_search", {"query": "q"}, [])
    assert "isn't available" in result.lower()


def test_execute_tool_get_directions_link():
    result = tools.execute_tool(
        "get_directions_link", {"destination": "Chisinau Airport"}, []
    )
    assert "https://www.google.com/maps/dir/" in result
    assert "Chisinau" in result


def test_execute_tool_append_vault_note():
    with patch(
        "second_brain.agent.vault_writer.append_note",
        return_value="/vault/Murzik Notes/project_updates.md",
    ) as mock_append:
        result = tools.execute_tool(
            "append_vault_note",
            {"filename": "project_updates.md", "content": "Docker is deployed."},
            [],
        )

    mock_append.assert_called_once_with("project_updates.md", "Docker is deployed.")
    assert "Saved to vault note" in result
    assert "project_updates.md" in result


def test_execute_tool_append_vault_note_missing_argument():
    result = tools.execute_tool(
        "append_vault_note",
        {"filename": "project_updates.md"},
        [],
    )

    assert "missing required argument" in result


def test_execute_tool_edit_vault_note():
    with patch(
        "second_brain.agent.vault_writer.edit_existing_note",
        return_value="/vault/project.md",
    ) as mock_edit:
        result = tools.execute_tool(
            "edit_vault_note",
            {
                "filename": "project.md",
                "old_text": "Docker is wanted.",
                "new_text": "Docker is done.",
            },
            [],
        )

    mock_edit.assert_called_once_with("project.md", "Docker is wanted.", "Docker is done.")
    assert "Edited vault note" in result
    assert "project.md" in result


def test_execute_tool_edit_vault_note_missing_argument():
    result = tools.execute_tool(
        "edit_vault_note",
        {"filename": "project.md", "old_text": "old"},
        [],
    )

    assert "missing required argument" in result


def test_execute_tool_accepts_optional_chat_id_without_breaking_existing_tools():
    result = tools.execute_tool(
        "get_directions_link", {"destination": "Airport"}, [], chat_id=42
    )
    assert "https://www.google.com/maps/dir/" in result


def test_tools_schema_includes_reminder_tools():
    names = {t["function"]["name"] for t in tools.TOOLS_SCHEMA}
    assert {"set_reminder", "list_reminders", "cancel_reminder"} <= names


def test_execute_tool_set_reminder():
    from datetime import datetime

    with patch("second_brain.agent.tools.get_reminder_store") as mock_get_store:
        mock_store = mock_get_store.return_value
        mock_store.add.return_value = type("R", (), {"id": "abc123"})()

        result = tools.execute_tool(
            "set_reminder",
            {"message": "take out the roast", "fire_at": "2026-08-10T15:20:00"},
            [],
            chat_id=1,
        )

    mock_store.add.assert_called_once_with(
        1, datetime(2026, 8, 10, 15, 20), "take out the roast"
    )
    assert "abc123" in result


def test_execute_tool_set_reminder_normalizes_offset_timestamp(monkeypatch):
    import time
    from datetime import datetime

    monkeypatch.setenv("TZ", "Europe/Chisinau")
    if hasattr(time, "tzset"):
        time.tzset()
    with patch("second_brain.agent.tools.get_reminder_store") as mock_get_store:
        mock_store = mock_get_store.return_value
        mock_store.add.return_value = type("R", (), {"id": "abc123"})()

        tools.execute_tool(
            "set_reminder",
            {"message": "take out the roast", "fire_at": "2026-08-10T15:20:00+03:00"},
            [],
            chat_id=1,
        )

    mock_store.add.assert_called_once_with(
        1, datetime(2026, 8, 10, 15, 20), "take out the roast"
    )


def test_execute_tool_set_reminder_invalid_timestamp():
    result = tools.execute_tool(
        "set_reminder",
        {"message": "x", "fire_at": "not-a-real-timestamp"},
        [],
        chat_id=1,
    )
    assert "valid time" in result.lower() or "invalid" in result.lower()


def test_execute_tool_set_reminder_missing_message():
    result = tools.execute_tool(
        "set_reminder",
        {"fire_at": "2026-08-10T15:20:00"},
        [],
        chat_id=1,
    )
    assert "missing required argument" in result


def test_execute_tool_set_reminder_missing_chat_id():
    result = tools.execute_tool(
        "set_reminder",
        {"message": "x", "fire_at": "2026-08-10T15:20:00"},
        [],
    )
    assert "not available" in result.lower() or "no chat" in result.lower()


def test_execute_tool_list_reminders_empty():
    with patch("second_brain.agent.tools.get_reminder_store") as mock_get_store:
        mock_get_store.return_value.list_for_chat.return_value = []
        result = tools.execute_tool("list_reminders", {}, [], chat_id=1)

    assert "no" in result.lower() or "none" in result.lower()


def test_execute_tool_list_reminders_formats_entries():
    from datetime import datetime

    fake_reminder = type(
        "R",
        (),
        {
            "id": "abc123",
            "chat_id": 1,
            "fire_at": datetime(2026, 8, 10, 15, 20),
            "message": "take out the roast",
        },
    )()
    with patch("second_brain.agent.tools.get_reminder_store") as mock_get_store:
        mock_get_store.return_value.list_for_chat.return_value = [fake_reminder]
        result = tools.execute_tool("list_reminders", {}, [], chat_id=1)

    assert "take out the roast" in result
    assert "abc123" in result


def test_execute_tool_cancel_reminder_success():
    with patch("second_brain.agent.tools.get_reminder_store") as mock_get_store:
        mock_get_store.return_value.cancel.return_value = True
        result = tools.execute_tool(
            "cancel_reminder", {"reminder_id": "abc123"}, [], chat_id=1
        )

    mock_get_store.return_value.cancel.assert_called_once_with(chat_id=1, reminder_id="abc123")
    assert "cancel" in result.lower()


def test_execute_tool_cancel_reminder_not_found():
    with patch("second_brain.agent.tools.get_reminder_store") as mock_get_store:
        mock_get_store.return_value.cancel.return_value = False
        result = tools.execute_tool(
            "cancel_reminder", {"reminder_id": "nonexistent"}, [], chat_id=1
        )

    assert "no reminder" in result.lower()
