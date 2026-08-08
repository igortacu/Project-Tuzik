from unittest.mock import Mock, patch

from second_brain import config
from second_brain.generation.llm_client import LLMClient


def _fake_ok_response(content: str) -> Mock:
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"choices": [{"message": {"content": content}}]}
    return response


def test_generate_without_history_sends_only_system_and_user_messages(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "fake-key")
    client = LLMClient()

    with patch("requests.post", return_value=_fake_ok_response("ok")) as mock_post:
        client.generate("question", system_prompt="be nice")

    sent_messages = mock_post.call_args.kwargs["json"]["messages"]
    assert sent_messages == [
        {"role": "system", "content": "be nice"},
        {"role": "user", "content": "question"},
    ]


def test_generate_with_history_inserts_prior_turns_between_system_and_current_prompt(
    monkeypatch,
):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "fake-key")
    client = LLMClient()
    history = [("user", "q1"), ("assistant", "a1")]

    with patch("requests.post", return_value=_fake_ok_response("ok")) as mock_post:
        client.generate("q2", system_prompt="be nice", history=history)

    sent_messages = mock_post.call_args.kwargs["json"]["messages"]
    assert sent_messages == [
        {"role": "system", "content": "be nice"},
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q2"},
    ]
