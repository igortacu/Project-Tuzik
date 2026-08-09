"""Web and image search via the Brave Search API."""

import requests

from second_brain import config

_WEB_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
_IMAGE_SEARCH_URL = "https://api.search.brave.com/res/v1/images/search"
_REQUEST_TIMEOUT_SECONDS = 10


class WebSearchError(RuntimeError):
    """Raised when Brave Search isn't configured or a request fails."""


def _headers() -> dict[str, str]:
    if not config.BRAVE_SEARCH_API_KEY:
        raise WebSearchError("BRAVE_SEARCH_API_KEY not set in .env")
    return {"X-Subscription-Token": config.BRAVE_SEARCH_API_KEY, "Accept": "application/json"}


def search_web(query: str, count: int = 5) -> list[dict[str, str]]:
    """Returns [{"title":, "url":, "snippet":}, ...], [] on no results."""
    try:
        response = requests.get(
            _WEB_SEARCH_URL,
            headers=_headers(),
            params={"q": query, "count": count},
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise WebSearchError(f"Brave web search failed: {exc}") from exc

    results = response.json().get("web", {}).get("results", [])[:count]
    return [
        {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("description", "")}
        for r in results
    ]


def search_images(query: str, count: int = 3) -> list[str]:
    """Returns up to count image URLs. count is hard-capped at
    config.IMAGE_SEARCH_MAX_RESULTS regardless of what's requested, so a
    single tool call can't spam the chat with dozens of photos.
    """
    count = min(count, config.IMAGE_SEARCH_MAX_RESULTS)
    try:
        response = requests.get(
            _IMAGE_SEARCH_URL,
            headers=_headers(),
            params={"q": query, "count": count},
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise WebSearchError(f"Brave image search failed: {exc}") from exc

    results = response.json().get("results", [])[:count]
    return [
        r["properties"]["url"] for r in results if "properties" in r and "url" in r["properties"]
    ]
