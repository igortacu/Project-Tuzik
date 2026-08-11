"""LLM generation via a single OpenRouter free-tier model.

No fallback model, no paid tier, no local model, by request -- rate
limiting turned out to hit the whole OpenRouter account, not just one
model, so trying a second model on 429 didn't actually help, just added
complexity and latency.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, TypedDict

import requests
from langgraph.graph import END, START, StateGraph

from second_brain import config
from second_brain.agent import tools as tools_module

logger = logging.getLogger(__name__)

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_REQUEST_TIMEOUT_SECONDS = 30
_RATE_LIMIT_STATUS_CODE = 429

# Some free-tier models emit a visible reasoning/thinking block inline in the
# response content (rather than a separate API field) even when told not to.
# Strip it as a safety net -- the system prompt asks the model not to do this
# in the first place, but this covers the cases where it doesn't listen.
_THINKING_BLOCK_RE = re.compile(r"<(think|thinking|reasoning)>.*?</\1>", re.DOTALL | re.IGNORECASE)
# General safety net for any other XML/HTML-shaped tag that leaks into a
# reply -- rather than adding a new one-off regex every time the model
# drifts into a new markup format (DSML tool calls, stray HTML, etc.), strip
# anything tag-shaped after the specific, meaningful markup (thinking
# blocks, DSML tool calls -- parsed before this ever runs) has already been
# handled. Requires a letter right after < or </, so "x < 5 and y > 3"
# (math, not a tag) is left untouched -- a real tag's first character is
# always a letter.
_STRAY_TAG_RE = re.compile(r"</?[a-zA-Z][a-zA-Z0-9_:-]*(?:\s[^<>]*)?/?>")
_DSML_INVOKE_RE = re.compile(
    r"<\s*\|\s*DSML\s*\|\s*invoke\s+name=[\"'](?P<name>[\w_]+)[\"']\s*>"
    r"(?P<body>.*?)"
    r"</\s*\|\s*DSML\s*\|\s*invoke\s*>",
    re.DOTALL | re.IGNORECASE,
)
_DSML_PARAMETER_RE = re.compile(
    r"<\s*\|\s*DSML\s*\|\s*parameter\s+name=[\"'](?P<name>[\w_]+)[\"']"
    r"(?:\s+string=[\"']true[\"'])?\s*>"
    r"(?P<value>.*?)"
    r"</\s*\|\s*DSML\s*\|\s*parameter\s*>",
    re.DOTALL | re.IGNORECASE,
)
_RAW_TOOL_MARKUP_RE = re.compile(r"<\s*\|\s*DSML\s*\|", re.IGNORECASE)


def _strip_thinking(text: str) -> str:
    text = _THINKING_BLOCK_RE.sub("", text)
    text = _STRAY_TAG_RE.sub("", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def _parse_dsml_tool_calls(content: str) -> list[dict]:
    """Best-effort parser for models that leak DSML tool calls as text.

    OpenRouter sometimes returns raw DSML-ish markup in message.content even
    with tool_choice="auto". Convert that markup into the same shape as
    structured OpenAI tool calls so the normal execution loop can handle it.
    """
    calls = []
    for index, match in enumerate(_DSML_INVOKE_RE.finditer(content), start=1):
        arguments = {
            param.group("name"): param.group("value").strip()
            for param in _DSML_PARAMETER_RE.finditer(match.group("body"))
        }
        calls.append(
            {
                "id": f"raw_dsml_{index}",
                "type": "function",
                "function": {
                    "name": match.group("name"),
                    "arguments": json.dumps(arguments),
                },
            }
        )
    return calls


def _contains_raw_tool_markup(content: str) -> bool:
    return bool(_RAW_TOOL_MARKUP_RE.search(content))


class GenerationFailedError(RuntimeError):
    """Raised when the OpenRouter model failed for a reason other than
    rate-limiting (429 is handled separately -- see LLMClient.generate).
    """


@dataclass
class ToolResult:
    text: str
    image_urls: list[str] = field(default_factory=list)


class _ToolLoopState(TypedDict):
    messages: list[dict]
    image_urls: list[str]
    chat_id: int | None
    rounds: int
    pending_tool_calls: list[dict]
    result_text: str
    has_tool_calls: bool


def _build_messages(
    prompt: str, system_prompt: str | None, history: list[tuple[str, str]] | None
) -> list[dict]:
    messages = []
    effective_system_prompt = _build_system_prompt(system_prompt)
    if effective_system_prompt:
        messages.append({"role": "system", "content": effective_system_prompt})
    for role, content in history or ():
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": prompt})
    return messages


def _current_time_context() -> str:
    now = datetime.now().astimezone()
    timezone_name = now.tzname() or "local time"
    return (
        "Current local date/time for relative dates and reminders: "
        f"{now.isoformat(timespec='seconds')} ({timezone_name})."
    )


def _build_system_prompt(system_prompt: str | None) -> str:
    time_context = _current_time_context()
    if not system_prompt:
        return time_context
    return f"{system_prompt}\n\n{time_context}"


def _call_openrouter_message(messages: list[dict], tools: list[dict] | None = None) -> dict:
    """Returns the raw assistant message dict -- may have "content", or
    "tool_calls" instead of/alongside it.
    """
    payload = {"model": config.OPENROUTER_MODEL_ID.strip(), "messages": messages}
    if tools:
        payload["tools"] = tools
        # Without this, the configured model (deepseek/deepseek-v4-flash)
        # doesn't reliably use the structured tool_calls field -- it falls
        # back to leaking a raw pseudo-XML imitation of a tool call directly
        # into content instead. Confirmed via direct API testing: identical
        # request with tool_choice omitted vs "auto" was the only
        # difference between broken and working tool calls.
        payload["tool_choice"] = "auto"

    response = requests.post(
        _OPENROUTER_URL,
        headers={"Authorization": f"Bearer {config.OPENROUTER_API_KEY}"},
        json=payload,
        timeout=_REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]


def _call_openrouter(
    prompt: str,
    system_prompt: str | None,
    history: list[tuple[str, str]] | None = None,
) -> str:
    message = _call_openrouter_message(_build_messages(prompt, system_prompt, history))
    content = message.get("content")
    if not isinstance(content, str):
        # Seen in practice with the paid model: a 200 response whose content
        # is None instead of a string (no error, no explanation from the
        # API). Surface it as a clear failure instead of crashing on
        # .strip()/.sub() deeper in the call stack.
        raise GenerationFailedError(f"OpenRouter returned non-string content: {content!r}")
    return _strip_thinking(content)


def _agent_graph_node(state: _ToolLoopState) -> _ToolLoopState:
    """Calls the model once; LangGraph decides whether tools run next."""
    if state["rounds"] >= config.MAX_TOOL_ROUNDS:
        final_message = _call_openrouter_message(state["messages"], tools=None)
        content = final_message.get("content") or ""
        return {
            **state,
            "pending_tool_calls": [],
            "result_text": _strip_thinking(content),
            "has_tool_calls": False,
        }

    message = _call_openrouter_message(state["messages"], tools=tools_module.TOOLS_SCHEMA)
    tool_calls = message.get("tool_calls")
    if not tool_calls:
        content = message.get("content") or ""
        tool_calls = _parse_dsml_tool_calls(content)
        if not tool_calls:
            if _contains_raw_tool_markup(content):
                logger.warning("Model returned unparseable raw tool markup; suppressing it")
                return {
                    **state,
                    "pending_tool_calls": [],
                    "result_text": (
                        "N-am reusit sa rulez tool-ul corect. Mai incearca o data, te rog."
                    ),
                    "has_tool_calls": False,
                }
            return {
                **state,
                "pending_tool_calls": [],
                "result_text": _strip_thinking(content),
                "has_tool_calls": False,
            }
        message = {"role": "assistant", "content": None, "tool_calls": tool_calls}

    return {
        **state,
        "messages": state["messages"] + [message],
        "pending_tool_calls": tool_calls,
        "rounds": state["rounds"] + 1,
        "has_tool_calls": True,
    }


def _tool_graph_node(state: _ToolLoopState) -> _ToolLoopState:
    """Executes pending tool calls and appends tool-result messages."""
    messages = list(state["messages"])
    image_urls = list(state["image_urls"])
    for call in state["pending_tool_calls"]:
        name = call["function"]["name"]
        try:
            arguments = json.loads(call["function"]["arguments"])
        except (json.JSONDecodeError, TypeError):
            arguments = {}
        result_text = tools_module.execute_tool(
            name, arguments, image_urls, chat_id=state["chat_id"]
        )
        messages.append({"role": "tool", "tool_call_id": call["id"], "content": result_text})

    return {
        **state,
        "messages": messages,
        "image_urls": image_urls,
        "pending_tool_calls": [],
    }


def _route_after_agent(state: _ToolLoopState) -> Literal["tools", "__end__"]:
    return "tools" if state["has_tool_calls"] else END


def _build_tool_graph():
    graph = StateGraph(_ToolLoopState)
    graph.add_node("agent", _agent_graph_node)
    graph.add_node("tools", _tool_graph_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", _route_after_agent, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile()


_TOOL_GRAPH = _build_tool_graph()


def _run_tool_loop(messages: list[dict], chat_id: int | None = None) -> ToolResult:
    """Runs the tool-calling protocol via LangGraph.

    The graph has two nodes: "agent" calls OpenRouter, and "tools" executes
    vetted Murzik tools. It loops until the model returns final text or
    config.MAX_TOOL_ROUNDS is reached, then forces one final no-tools answer.
    """
    final_state = _TOOL_GRAPH.invoke(
        {
            "messages": messages,
            "image_urls": [],
            "chat_id": chat_id,
            "rounds": 0,
            "pending_tool_calls": [],
            "result_text": "",
            "has_tool_calls": False,
        }
    )
    return ToolResult(text=final_state["result_text"], image_urls=final_state["image_urls"])


class LLMClient:
    """generate() calls the single configured OpenRouter model
    (config.OPENROUTER_MODEL_ID). Accepts optional prior-turn history as
    [(role, content), ...] (role is "user" or "assistant"), inserted between
    the system message and the current prompt -- see bot/memory.py, which
    owns the actual per-chat history state; this class stays stateless
    across calls. On a 429 (rate limit), returns
    config.RATE_LIMIT_MESSAGE instead of raising -- rate limiting is an
    expected, recoverable condition, not a bug, so it gets an in-character
    reply rather than a generic error. If the *next* request also 429s right
    after that warning (the user didn't wait), it escalates to
    config.REPEATED_RATE_LIMIT_MESSAGE instead. A successful request resets
    the streak. Any other failure raises GenerationFailedError.

    generate_with_tools() is the same idea but runs the tool-calling loop
    (web_search/image_search/get_directions_link -- see agent/tools.py) and
    returns a ToolResult instead of a bare string.
    """

    def __init__(self) -> None:
        self._consecutive_rate_limits = 0

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        history: list[tuple[str, str]] | None = None,
    ) -> str:
        if not config.OPENROUTER_API_KEY:
            raise GenerationFailedError("OPENROUTER_API_KEY not set in .env")

        try:
            result = _call_openrouter(prompt, system_prompt, history)
            self._consecutive_rate_limits = 0
            logger.info("llm request served by model=%s", config.OPENROUTER_MODEL_ID)
            return result
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == _RATE_LIMIT_STATUS_CODE:
                self._consecutive_rate_limits += 1
                if self._consecutive_rate_limits >= 2:
                    logger.warning("OpenRouter rate-limited again (429) -- escalating reply")
                    return config.REPEATED_RATE_LIMIT_MESSAGE
                logger.warning("OpenRouter rate-limited (429), returning stock reply")
                return config.RATE_LIMIT_MESSAGE
            raise GenerationFailedError(f"OpenRouter request failed: {exc}") from exc
        except requests.RequestException as exc:
            raise GenerationFailedError(f"OpenRouter request failed: {exc}") from exc
        except (KeyError, IndexError) as exc:
            # Malformed/unexpected response shape (missing "choices", empty
            # list, etc.) -- same defensive intent as the non-string content
            # check in _call_openrouter, just for structure instead of type.
            raise GenerationFailedError(f"OpenRouter returned an unexpected response shape: {exc}") from exc

    def generate_with_tools(
        self,
        prompt: str,
        system_prompt: str | None = None,
        history: list[tuple[str, str]] | None = None,
        chat_id: int | None = None,
    ) -> ToolResult:
        if not config.OPENROUTER_API_KEY:
            raise GenerationFailedError("OPENROUTER_API_KEY not set in .env")

        messages = _build_messages(prompt, system_prompt, history)
        try:
            result = _run_tool_loop(messages, chat_id=chat_id)
            self._consecutive_rate_limits = 0
            logger.info("llm request served by model=%s (tools)", config.OPENROUTER_MODEL_ID)
            return result
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == _RATE_LIMIT_STATUS_CODE:
                self._consecutive_rate_limits += 1
                if self._consecutive_rate_limits >= 2:
                    logger.warning("OpenRouter rate-limited again (429) -- escalating reply")
                    return ToolResult(text=config.REPEATED_RATE_LIMIT_MESSAGE)
                logger.warning("OpenRouter rate-limited (429), returning stock reply")
                return ToolResult(text=config.RATE_LIMIT_MESSAGE)
            raise GenerationFailedError(f"OpenRouter request failed: {exc}") from exc
        except requests.RequestException as exc:
            raise GenerationFailedError(f"OpenRouter request failed: {exc}") from exc
        except (KeyError, IndexError) as exc:
            raise GenerationFailedError(f"OpenRouter returned an unexpected response shape: {exc}") from exc
