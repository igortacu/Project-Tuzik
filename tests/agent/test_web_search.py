from unittest.mock import Mock, patch

import pytest
import requests

from second_brain import config
from second_brain.agent import web_search


@pytest.fixture(autouse=True)
def _fake_api_key(monkeypatch):
    monkeypatch.setattr(config, "BRAVE_SEARCH_API_KEY", "fake-key")


def _fake_response(json_data):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = json_data
    return response


def test_search_web_missing_api_key_raises(monkeypatch):
    monkeypatch.setattr(config, "BRAVE_SEARCH_API_KEY", None)
    with pytest.raises(web_search.WebSearchError):
        web_search.search_web("query")


def test_search_web_parses_results():
    payload = {
        "web": {
            "results": [
                {"title": "Result 1", "url": "https://a.example", "description": "First result"},
                {"title": "Result 2", "url": "https://b.example", "description": "Second result"},
            ]
        }
    }
    with patch("requests.get", return_value=_fake_response(payload)):
        results = web_search.search_web("some query")

    assert results == [
        {"title": "Result 1", "url": "https://a.example", "snippet": "First result"},
        {"title": "Result 2", "url": "https://b.example", "snippet": "Second result"},
    ]


def test_search_web_no_results_returns_empty_list():
    with patch("requests.get", return_value=_fake_response({"web": {"results": []}})):
        assert web_search.search_web("nothing") == []


def test_search_web_request_failure_raises_web_search_error():
    with patch("requests.get", side_effect=requests.ConnectionError("down")):
        with pytest.raises(web_search.WebSearchError):
            web_search.search_web("query")


def test_search_images_parses_urls():
    payload = {
        "results": [
            {"properties": {"url": "https://img1.example/a.jpg"}},
            {"properties": {"url": "https://img2.example/b.jpg"}},
        ]
    }
    with patch("requests.get", return_value=_fake_response(payload)):
        urls = web_search.search_images("cats")

    assert urls == ["https://img1.example/a.jpg", "https://img2.example/b.jpg"]


def test_search_images_hard_caps_at_config_max(monkeypatch):
    monkeypatch.setattr(config, "IMAGE_SEARCH_MAX_RESULTS", 2)
    payload = {
        "results": [
            {"properties": {"url": "https://img1.example"}},
            {"properties": {"url": "https://img2.example"}},
            {"properties": {"url": "https://img3.example"}},
        ]
    }
    with patch("requests.get", return_value=_fake_response(payload)) as mock_get:
        urls = web_search.search_images("cats", count=10)

    # requested count is clamped to config.IMAGE_SEARCH_MAX_RESULTS before the request
    assert mock_get.call_args.kwargs["params"]["count"] == 2
    assert len(urls) <= 2


def test_search_images_ignores_results_without_url_property():
    payload = {"results": [{"properties": {}}, {"no_properties": True}]}
    with patch("requests.get", return_value=_fake_response(payload)):
        assert web_search.search_images("query") == []
