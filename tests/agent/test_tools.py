from unittest.mock import patch

from second_brain.agent import tools, web_search


def test_tools_schema_has_expected_function_names():
    names = {t["function"]["name"] for t in tools.TOOLS_SCHEMA}
    assert names == {"web_search", "image_search", "get_directions_link"}


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
