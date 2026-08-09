"""Tool-calling registry: JSON schemas the model sees (TOOLS_SCHEMA), and
execute_tool() which actually runs one when the model calls it.
"""

from second_brain.agent import maps, web_search

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current information not in Igor's notes.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "image_search",
            "description": "Search the web for photos/images. Only call this when the user "
            "explicitly asks for a photo or picture, not proactively.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_directions_link",
            "description": "Build a Google Maps link with directions to a place.",
            "parameters": {
                "type": "object",
                "properties": {
                    "destination": {"type": "string"},
                    "origin": {
                        "type": "string",
                        "description": "Omit to let Maps use the user's current location",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["driving", "walking", "bicycling", "transit"],
                    },
                },
                "required": ["destination"],
            },
        },
    },
]


def execute_tool(name: str, arguments: dict, image_urls_out: list[str]) -> str:
    """Runs one tool call, returns the text fed back to the model.

    image_search additionally appends its URLs to image_urls_out -- a side
    channel the caller uses to actually send photos, since raw URLs in the
    model's own context don't get attached as Telegram photos on their own.

    Never raises: a failed search (e.g. BRAVE_SEARCH_API_KEY not configured)
    degrades to a text message the model can relay, rather than crashing the
    whole tool-call loop.
    """
    if name == "web_search":
        try:
            results = web_search.search_web(arguments["query"])
        except web_search.WebSearchError as exc:
            return f"Web search isn't available right now: {exc}"
        if not results:
            return "No results found."
        return "\n\n".join(f"{r['title']}\n{r['url']}\n{r['snippet']}" for r in results)

    if name == "image_search":
        try:
            urls = web_search.search_images(arguments["query"])
        except web_search.WebSearchError as exc:
            return f"Image search isn't available right now: {exc}"
        image_urls_out.extend(urls)
        return f"Found {len(urls)} image(s), queued to send directly." if urls else "No images found."

    if name == "get_directions_link":
        link = maps.build_directions_link(
            arguments["destination"], arguments.get("origin"), arguments.get("mode", "driving")
        )
        return f"Directions link: {link}"

    return f"Unknown tool: {name}"
