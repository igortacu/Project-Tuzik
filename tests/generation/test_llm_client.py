import json
from unittest.mock import Mock, patch

import requests

from second_brain import config
from second_brain.generation.llm_client import LLMClient


def _fake_ok_response(content: str) -> Mock:
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"choices": [{"message": {"content": content}}]}
    return response


def _fake_message_response(message: dict) -> Mock:
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"choices": [{"message": message}]}
    return response


def _fake_tool_call(call_id: str, name: str, arguments: dict) -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)},
            }
        ],
    }


def test_generate_without_history_sends_only_system_and_user_messages(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "fake-key")
    monkeypatch.setattr(
        "second_brain.generation.llm_client._current_time_context",
        lambda: "Current local date/time: test-now",
    )
    client = LLMClient()

    with patch("requests.post", return_value=_fake_ok_response("ok")) as mock_post:
        client.generate("question", system_prompt="be nice")

    sent_messages = mock_post.call_args.kwargs["json"]["messages"]
    assert sent_messages == [
        {"role": "system", "content": "be nice\n\nCurrent local date/time: test-now"},
        {"role": "user", "content": "question"},
    ]


def test_generate_with_history_inserts_prior_turns_between_system_and_current_prompt(
    monkeypatch,
):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "fake-key")
    monkeypatch.setattr(
        "second_brain.generation.llm_client._current_time_context",
        lambda: "Current local date/time: test-now",
    )
    client = LLMClient()
    history = [("user", "q1"), ("assistant", "a1")]

    with patch("requests.post", return_value=_fake_ok_response("ok")) as mock_post:
        client.generate("q2", system_prompt="be nice", history=history)

    sent_messages = mock_post.call_args.kwargs["json"]["messages"]
    assert sent_messages == [
        {"role": "system", "content": "be nice\n\nCurrent local date/time: test-now"},
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q2"},
    ]


def test_generate_without_system_prompt_still_sends_current_time(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "fake-key")
    monkeypatch.setattr(
        "second_brain.generation.llm_client._current_time_context",
        lambda: "Current local date/time: test-now",
    )
    client = LLMClient()

    with patch("requests.post", return_value=_fake_ok_response("ok")) as mock_post:
        client.generate("question")

    sent_messages = mock_post.call_args.kwargs["json"]["messages"]
    assert sent_messages == [
        {"role": "system", "content": "Current local date/time: test-now"},
        {"role": "user", "content": "question"},
    ]


# --- generate_with_tools ---


def test_generate_with_tools_no_tool_call_returns_text_directly(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "fake-key")
    client = LLMClient()
    response = _fake_message_response({"role": "assistant", "content": "plain answer"})

    with patch("requests.post", return_value=response) as mock_post:
        result = client.generate_with_tools("question")

    assert result.text == "plain answer"
    assert result.image_urls == []
    assert mock_post.call_count == 1


def test_generate_with_tools_executes_tool_and_returns_final_text(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "fake-key")
    client = LLMClient()

    tool_call_response = _fake_message_response(
        _fake_tool_call("call_1", "get_directions_link", {"destination": "Airport"})
    )
    final_response = _fake_message_response({"role": "assistant", "content": "Here's your link."})

    with patch("requests.post", side_effect=[tool_call_response, final_response]) as mock_post:
        result = client.generate_with_tools("how do I get to the airport")

    assert result.text == "Here's your link."
    assert mock_post.call_count == 2
    second_call_messages = mock_post.call_args_list[1].kwargs["json"]["messages"]
    assert any(m.get("role") == "tool" for m in second_call_messages)


def test_generate_with_tools_image_search_populates_image_urls(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "fake-key")
    client = LLMClient()

    tool_call_response = _fake_message_response(
        _fake_tool_call("c1", "image_search", {"query": "cats"})
    )
    final_response = _fake_message_response({"role": "assistant", "content": "here are some cats"})

    with (
        patch("requests.post", side_effect=[tool_call_response, final_response]),
        patch(
            "second_brain.agent.web_search.search_images",
            return_value=["https://img.example/1.jpg"],
        ),
    ):
        result = client.generate_with_tools("send me a cat photo")

    assert result.image_urls == ["https://img.example/1.jpg"]
    assert result.text == "here are some cats"


def test_generate_with_tools_caps_rounds_and_forces_final_answer(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "fake-key")
    monkeypatch.setattr(config, "MAX_TOOL_ROUNDS", 2)
    client = LLMClient()

    tool_call_response = _fake_message_response(
        _fake_tool_call("c", "web_search", {"query": "x"})
    )
    final_response = _fake_message_response({"role": "assistant", "content": "forced final answer"})

    with (
        patch(
            "requests.post",
            side_effect=[tool_call_response, tool_call_response, final_response],
        ) as mock_post,
        patch("second_brain.agent.web_search.search_web", return_value=[]),
    ):
        result = client.generate_with_tools("keep searching forever")

    assert result.text == "forced final answer"
    assert mock_post.call_count == 3
    assert "tools" not in mock_post.call_args_list[-1].kwargs["json"]


def test_generate_with_tools_rate_limited_returns_stock_reply(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "fake-key")
    client = LLMClient()

    fake_429 = Mock()
    fake_429.status_code = 429
    fake_429.raise_for_status.side_effect = requests.HTTPError(response=fake_429)

    with patch("requests.post", return_value=fake_429):
        result = client.generate_with_tools("question")

    assert result.text == config.RATE_LIMIT_MESSAGE
    assert result.image_urls == []


def test_generate_with_tools_sends_explicit_tool_choice_auto(monkeypatch):
    """Regression test: deepseek/deepseek-v4-flash doesn't reliably populate
    the structured tool_calls field without tool_choice explicitly set to
    "auto" -- confirmed via direct API testing. Without it, tool calls leak
    as raw text into content instead of being machine-parseable.
    """
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "fake-key")
    client = LLMClient()
    response = _fake_message_response({"role": "assistant", "content": "plain answer"})

    with patch("requests.post", return_value=response) as mock_post:
        client.generate_with_tools("question")

    assert mock_post.call_args.kwargs["json"]["tool_choice"] == "auto"


def test_generate_without_tools_omits_tool_choice(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "fake-key")
    client = LLMClient()

    with patch("requests.post", return_value=_fake_ok_response("ok")) as mock_post:
        client.generate("question")

    assert "tool_choice" not in mock_post.call_args.kwargs["json"]
    assert "tools" not in mock_post.call_args.kwargs["json"]


def test_generate_with_tools_forwards_chat_id_to_execute_tool(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "fake-key")
    client = LLMClient()

    tool_call_response = _fake_message_response(
        _fake_tool_call("c1", "web_search", {"query": "x"})
    )
    final_response = _fake_message_response({"role": "assistant", "content": "done"})

    with (
        patch("requests.post", side_effect=[tool_call_response, final_response]),
        patch("second_brain.agent.tools.execute_tool", return_value="result") as mock_execute,
    ):
        client.generate_with_tools("question", chat_id=999)

    mock_execute.assert_called_once_with("web_search", {"query": "x"}, [], chat_id=999)
