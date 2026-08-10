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
