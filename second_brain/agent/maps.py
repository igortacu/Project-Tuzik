"""Builds Google Maps directions deep-links. No API key needed -- this just
constructs a URL; Google Maps (the app or web) does the actual routing.
"""

from urllib.parse import quote

_VALID_MODES = {"driving", "walking", "bicycling", "transit"}


def build_directions_link(destination: str, origin: str | None = None, mode: str = "driving") -> str:
    if mode not in _VALID_MODES:
        mode = "driving"

    params = f"api=1&destination={quote(destination)}&travelmode={mode}"
    if origin:
        params += f"&origin={quote(origin)}"
    return f"https://www.google.com/maps/dir/?{params}"
