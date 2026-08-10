# Reminders for Murzik Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Murzik a working reminders feature (set/list/cancel via natural language) so it stops hallucinating reminder promises it can't keep.

**Architecture:** Reminders are rows in a disk-persisted `ReminderStore` (mirrors the existing `SaveBuffer` pattern), not individually scheduled `JobQueue` jobs -- a single recurring poller job (same pattern as `periodic_save_job`) checks every 30s for anything due and fires it. Three new model-facing tools (`set_reminder`, `list_reminders`, `cancel_reminder`) join the existing tool-calling registry in `second_brain/agent/tools.py`.

**Tech Stack:** Python 3.10, pytest, python-telegram-bot's JobQueue (APScheduler-backed) -- no new dependencies.

## Global Constraints

- Each reminder is fully independent: setting, editing, or cancelling one never touches another (confirmed with the project owner during brainstorming).
- Reminders must survive a bot restart -- persisted to `data/reminders.json`, loaded on construction, persisted after every mutation (exact same pattern as `second_brain/bot/memory.py`'s `SaveBuffer`).
- The model computes an absolute ISO 8601 timestamp for `fire_at` itself; no natural-language date parsing lives in this code.
- v1 includes list and cancel (per the project owner's explicit choice), not just set-and-fire.
- No recurring/repeating reminders, no reminder-editing-in-place, no slash-command UI -- out of scope per the design spec.
- Full spec: `docs/superpowers/specs/2026-08-10-reminders-design.md`.

---

### Task 1: ReminderStore + Reminder dataclass

**Files:**
- Create: `second_brain/agent/reminders.py`
- Test: `tests/agent/test_reminders.py`

**Interfaces:**
- Produces: `Reminder` dataclass (`id: str`, `chat_id: int`, `fire_at: datetime`, `message: str`); `ReminderStore` class with `add(chat_id: int, fire_at: datetime, message: str) -> Reminder`, `cancel(chat_id: int, reminder_id: str) -> bool`, `list_for_chat(chat_id: int) -> list[Reminder]`, `due(now: datetime) -> list[Reminder]`, `remove(reminder_id: str) -> None`; module-level `get_reminder_store() -> ReminderStore` singleton getter (same naming pattern as `index_pipeline.get_vector_store()`).
- Consumes: `config.REMINDER_STORE_PATH` (added in this task).

- [ ] **Step 1: Add the config value**

Add to `second_brain/config.py`, near the existing `SAVE_BUFFER_PATH` line (in the periodic-save section):

```python
# Reminders: persisted like SaveBuffer so a bot restart can't silently drop
# a pending reminder -- see agent/reminders.py.
REMINDER_STORE_PATH = "data/reminders.json"
```

- [ ] **Step 2: Write the failing tests**

Create `tests/agent/test_reminders.py`:

```python
from datetime import datetime, timedelta

from second_brain.agent.reminders import ReminderStore


def _make_store(tmp_path):
    return ReminderStore(persist_path=str(tmp_path / "reminders.json"))


def test_add_returns_reminder_with_matching_fields(tmp_path):
    store = _make_store(tmp_path)
    fire_at = datetime(2026, 8, 10, 15, 20)

    reminder = store.add(chat_id=1, fire_at=fire_at, message="take out the roast")

    assert reminder.chat_id == 1
    assert reminder.fire_at == fire_at
    assert reminder.message == "take out the roast"
    assert reminder.id


def test_list_for_chat_is_isolated_per_chat(tmp_path):
    store = _make_store(tmp_path)
    store.add(1, datetime(2026, 8, 10, 15, 0), "chat one reminder")
    store.add(2, datetime(2026, 8, 10, 16, 0), "chat two reminder")

    assert [r.message for r in store.list_for_chat(1)] == ["chat one reminder"]
    assert [r.message for r in store.list_for_chat(2)] == ["chat two reminder"]


def test_cancel_removes_reminder_belonging_to_the_chat(tmp_path):
    store = _make_store(tmp_path)
    reminder = store.add(1, datetime(2026, 8, 10, 15, 0), "cancel me")

    assert store.cancel(chat_id=1, reminder_id=reminder.id) is True
    assert store.list_for_chat(1) == []


def test_cancel_refuses_a_different_chats_reminder(tmp_path):
    store = _make_store(tmp_path)
    reminder = store.add(1, datetime(2026, 8, 10, 15, 0), "not yours")

    assert store.cancel(chat_id=2, reminder_id=reminder.id) is False
    assert [r.id for r in store.list_for_chat(1)] == [reminder.id]


def test_cancel_unknown_id_returns_false(tmp_path):
    store = _make_store(tmp_path)
    assert store.cancel(chat_id=1, reminder_id="nonexistent") is False


def test_due_returns_reminders_at_or_before_now(tmp_path):
    store = _make_store(tmp_path)
    now = datetime(2026, 8, 10, 15, 20)
    due_reminder = store.add(1, now - timedelta(minutes=1), "already due")
    store.add(1, now + timedelta(minutes=1), "not yet due")

    assert [r.id for r in store.due(now)] == [due_reminder.id]


def test_due_at_exact_boundary_is_included(tmp_path):
    store = _make_store(tmp_path)
    now = datetime(2026, 8, 10, 15, 20)
    reminder = store.add(1, now, "exactly now")

    assert [r.id for r in store.due(now)] == [reminder.id]


def test_remove_deletes_the_reminder(tmp_path):
    store = _make_store(tmp_path)
    reminder = store.add(1, datetime(2026, 8, 10, 15, 0), "temp")

    store.remove(reminder.id)

    assert store.list_for_chat(1) == []


def test_remove_unknown_id_does_not_raise(tmp_path):
    store = _make_store(tmp_path)
    store.remove("nonexistent")


def test_survives_a_simulated_restart(tmp_path):
    persist_path = str(tmp_path / "reminders.json")
    first = ReminderStore(persist_path=persist_path)
    reminder = first.add(1, datetime(2026, 8, 10, 15, 20), "survive restart")

    second = ReminderStore(persist_path=persist_path)

    assert [r.id for r in second.list_for_chat(1)] == [reminder.id]
    assert second.list_for_chat(1)[0].fire_at == reminder.fire_at
    assert second.list_for_chat(1)[0].message == "survive restart"


def test_cancel_persists_the_removal(tmp_path):
    persist_path = str(tmp_path / "reminders.json")
    first = ReminderStore(persist_path=persist_path)
    reminder = first.add(1, datetime(2026, 8, 10, 15, 0), "temp")
    first.cancel(chat_id=1, reminder_id=reminder.id)

    second = ReminderStore(persist_path=persist_path)

    assert second.list_for_chat(1) == []
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `pytest tests/agent/test_reminders.py -v`
Expected: FAIL / collection error -- `second_brain.agent.reminders` does not exist yet.

- [ ] **Step 4: Implement `second_brain/agent/reminders.py`**

```python
"""Reminder storage: isolated, independently fireable one-shot reminders.

Persisted to config.REMINDER_STORE_PATH so a bot restart (a deploy, a
crash) doesn't silently lose a pending reminder -- mirrors bot/memory.py's
SaveBuffer persistence pattern exactly (load on construction, persist after
every mutation). Reminders are not scheduled as individual JobQueue jobs --
see bot/telegram_bot.py's reminder_dispatch_job, which polls due() on a
short interval instead. That's what makes restart-survival free: this
store is the source of truth, not in-memory scheduler state.
"""

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime

from second_brain import config


@dataclass
class Reminder:
    id: str
    chat_id: int
    fire_at: datetime
    message: str


class ReminderStore:
    def __init__(self, persist_path: str | None = None) -> None:
        self._persist_path = persist_path or config.REMINDER_STORE_PATH
        self._reminders: dict[str, Reminder] = {}
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self._persist_path):
            return
        with open(self._persist_path, encoding="utf-8") as f:
            raw = json.load(f)
        self._reminders = {
            r["id"]: Reminder(
                id=r["id"],
                chat_id=r["chat_id"],
                fire_at=datetime.fromisoformat(r["fire_at"]),
                message=r["message"],
            )
            for r in raw
        }

    def _persist(self) -> None:
        os.makedirs(os.path.dirname(self._persist_path) or ".", exist_ok=True)
        raw = [
            {
                "id": r.id,
                "chat_id": r.chat_id,
                "fire_at": r.fire_at.isoformat(),
                "message": r.message,
            }
            for r in self._reminders.values()
        ]
        with open(self._persist_path, "w", encoding="utf-8") as f:
            json.dump(raw, f)

    def add(self, chat_id: int, fire_at: datetime, message: str) -> Reminder:
        reminder = Reminder(
            id=str(uuid.uuid4()), chat_id=chat_id, fire_at=fire_at, message=message
        )
        self._reminders[reminder.id] = reminder
        self._persist()
        return reminder

    def cancel(self, chat_id: int, reminder_id: str) -> bool:
        """Only removes the reminder if it belongs to chat_id -- one chat
        can never cancel another chat's reminder. False if the id doesn't
        exist or belongs to a different chat.
        """
        reminder = self._reminders.get(reminder_id)
        if reminder is None or reminder.chat_id != chat_id:
            return False
        del self._reminders[reminder_id]
        self._persist()
        return True

    def list_for_chat(self, chat_id: int) -> list[Reminder]:
        return [r for r in self._reminders.values() if r.chat_id == chat_id]

    def due(self, now: datetime) -> list[Reminder]:
        return [r for r in self._reminders.values() if r.fire_at <= now]

    def remove(self, reminder_id: str) -> None:
        self._reminders.pop(reminder_id, None)
        self._persist()


_reminder_store: ReminderStore | None = None


def get_reminder_store() -> ReminderStore:
    global _reminder_store
    if _reminder_store is None:
        _reminder_store = ReminderStore()
    return _reminder_store
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/agent/test_reminders.py -v`
Expected: PASS, all 12 tests green.

- [ ] **Step 6: Commit**

```bash
git add second_brain/agent/reminders.py tests/agent/test_reminders.py second_brain/config.py
git commit -m "feat: add ReminderStore with restart-surviving persistence"
```

---

### Task 2: Thread chat_id through the tool-calling stack

**Files:**
- Modify: `second_brain/agent/tools.py` (`execute_tool` signature)
- Modify: `second_brain/generation/llm_client.py` (`_run_tool_loop`, `LLMClient.generate_with_tools`)
- Modify: `second_brain/pipelines/query_pipeline.py` (`answer_query`)
- Modify: `second_brain/bot/telegram_bot.py` (`_answer_message`)
- Test: `tests/agent/test_tools.py` (extend)
- Test: `tests/generation/test_llm_client.py` (extend)
- Test: Create `tests/pipelines/test_query_pipeline.py`
- Test: `tests/bot/test_telegram_bot.py` (extend)

**Interfaces:**
- Consumes: nothing from Task 1 directly (this task is pure plumbing -- no reminder tool exists yet).
- Produces: `execute_tool(name, arguments, image_urls_out, chat_id=None)`; `LLMClient.generate_with_tools(prompt, system_prompt=None, history=None, chat_id=None)`; `query_pipeline.answer_query(query, top_k=None, filters=None, history=None, chat_id=None)`. `chat_id` defaults to `None` everywhere so every existing call site and test keeps working unchanged -- only `telegram_bot._answer_message` (which already has `chat_id` locally) is updated to actually pass it.

- [ ] **Step 1: Write the failing test for `execute_tool` accepting chat_id**

Add to `tests/agent/test_tools.py`:

```python
def test_execute_tool_accepts_optional_chat_id_without_breaking_existing_tools():
    result = tools.execute_tool(
        "get_directions_link", {"destination": "Airport"}, [], chat_id=42
    )
    assert "https://www.google.com/maps/dir/" in result
```

- [ ] **Step 2: Write the failing test for `generate_with_tools` forwarding chat_id**

Add to `tests/generation/test_llm_client.py`:

```python
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
```

- [ ] **Step 3: Write the failing test for `answer_query` forwarding chat_id**

Create `tests/pipelines/test_query_pipeline.py`:

```python
from unittest.mock import Mock, patch

from second_brain.generation.llm_client import ToolResult
from second_brain.pipelines import query_pipeline


def test_answer_query_forwards_chat_id_to_generate_with_tools():
    fake_llm = Mock()
    fake_llm.generate_with_tools.return_value = ToolResult(text="answer")
    fake_retriever = Mock()
    fake_retriever.retrieve.return_value = []

    with (
        patch("second_brain.pipelines.query_pipeline._get_llm_client", return_value=fake_llm),
        patch("second_brain.pipelines.query_pipeline._get_retriever", return_value=fake_retriever),
    ):
        query_pipeline.answer_query("what's on my calendar", chat_id=555)

    assert fake_llm.generate_with_tools.call_args.kwargs["chat_id"] == 555
```

- [ ] **Step 4: Write the failing test for `_answer_message` forwarding chat_id**

Add to `tests/bot/test_telegram_bot.py`:

```python
def test_answer_message_forwards_chat_id_to_answer_query():
    class _FakeChat:
        async def send_action(self, *a, **k):
            pass

    class _FakeMessage:
        chat = _FakeChat()

        async def reply_text(self, *a, **k):
            pass

    class _FakeUpdate:
        effective_chat = type("C", (), {"id": 777})()
        message = _FakeMessage()

    fake_result = type("R", (), {"text": "an answer", "image_urls": []})()

    with (
        patch(
            "second_brain.bot.telegram_bot.query_pipeline.answer_query",
            return_value=fake_result,
        ) as mock_answer,
        patch.object(telegram_bot._memory, "append"),
        patch.object(telegram_bot._save_buffer, "append"),
    ):
        asyncio.run(telegram_bot._answer_message(_FakeUpdate(), "hi"))

    assert mock_answer.call_args.kwargs["chat_id"] == 777
```

- [ ] **Step 5: Run all four new tests to verify they fail**

Run: `pytest tests/agent/test_tools.py::test_execute_tool_accepts_optional_chat_id_without_breaking_existing_tools tests/generation/test_llm_client.py::test_generate_with_tools_forwards_chat_id_to_execute_tool tests/pipelines/test_query_pipeline.py tests/bot/test_telegram_bot.py::test_answer_message_forwards_chat_id_to_answer_query -v`
Expected: FAIL -- `execute_tool()`/`generate_with_tools()`/`answer_query()` don't accept `chat_id` yet (`TypeError: unexpected keyword argument`), and `_answer_message` doesn't pass it.

- [ ] **Step 6: Add `chat_id` to `execute_tool`'s signature**

In `second_brain/agent/tools.py`, change the function signature:

```python
def execute_tool(
    name: str, arguments: dict, image_urls_out: list[str], chat_id: int | None = None
) -> str:
```

No branch inside the function uses `chat_id` yet -- Task 3 adds the branches that do.

- [ ] **Step 7: Thread `chat_id` through `llm_client.py`**

In `second_brain/generation/llm_client.py`, change `_run_tool_loop`:

```python
def _run_tool_loop(messages: list[dict], chat_id: int | None = None) -> ToolResult:
    ...
    for _round in range(config.MAX_TOOL_ROUNDS):
        message = _call_openrouter_message(messages, tools=tools_module.TOOLS_SCHEMA)
        tool_calls = message.get("tool_calls")
        if not tool_calls:
            content = message.get("content") or ""
            return ToolResult(text=_strip_thinking(content), image_urls=image_urls)

        messages.append(message)
        for call in tool_calls:
            name = call["function"]["name"]
            try:
                arguments = json.loads(call["function"]["arguments"])
            except (json.JSONDecodeError, TypeError):
                arguments = {}
            result_text = tools_module.execute_tool(
                name, arguments, image_urls, chat_id=chat_id
            )
            messages.append(
                {"role": "tool", "tool_call_id": call["id"], "content": result_text}
            )
    ...
```

(Only the `execute_tool(...)` call line and the function signature change -- the rest of `_run_tool_loop` is unchanged.)

And `LLMClient.generate_with_tools`:

```python
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
```

(Only the signature and the `_run_tool_loop(messages, chat_id=chat_id)` call change -- the rest of the method body, including the exception handling, is unchanged.)

- [ ] **Step 8: Thread `chat_id` through `query_pipeline.answer_query`**

In `second_brain/pipelines/query_pipeline.py`:

```python
def answer_query(
    query: str,
    top_k: int | None = None,
    filters: dict[str, Any] | None = None,
    history: list[tuple[str, str]] | None = None,
    chat_id: int | None = None,
) -> QueryResult:
    """..."""
    if _is_small_talk(query):
        text = _get_llm_client().generate(
            f"Message: {query}\nReply:",
            system_prompt=config.SYSTEM_PROMPT,
            history=history,
        )
        return QueryResult(text=text)

    resolved_top_k = top_k if top_k is not None else config.TOP_K
    chunks = _get_retriever().retrieve(query, resolved_top_k, filters)
    prompt = build_prompt(query, chunks)
    result = _get_llm_client().generate_with_tools(
        prompt, system_prompt=config.SYSTEM_PROMPT, history=history, chat_id=chat_id
    )
    return QueryResult(text=result.text, image_urls=result.image_urls)
```

(The small-talk path is unchanged -- it never calls tools, so `chat_id` isn't needed there.)

- [ ] **Step 9: Pass `chat_id` from `telegram_bot._answer_message`**

In `second_brain/bot/telegram_bot.py`, in `_answer_message`, change the `answer_query` call:

```python
    try:
        result = await asyncio.to_thread(
            query_pipeline.answer_query,
            question,
            history=_memory.get(chat_id),
            chat_id=chat_id,
        )
```

- [ ] **Step 10: Run the tests to verify they pass**

Run: `pytest tests/agent/test_tools.py tests/generation/test_llm_client.py tests/pipelines/test_query_pipeline.py tests/bot/test_telegram_bot.py -v`
Expected: PASS, including all pre-existing tests in these files (no regressions from the new default-`None` parameter).

- [ ] **Step 11: Run the full suite to confirm no regressions elsewhere**

Run: `pytest -v`
Expected: PASS, same pass count as before this task plus the new tests.

- [ ] **Step 12: Commit**

```bash
git add second_brain/agent/tools.py second_brain/generation/llm_client.py second_brain/pipelines/query_pipeline.py second_brain/bot/telegram_bot.py tests/agent/test_tools.py tests/generation/test_llm_client.py tests/pipelines/test_query_pipeline.py tests/bot/test_telegram_bot.py
git commit -m "refactor: thread chat_id through the tool-calling stack"
```

---

### Task 3: set_reminder / list_reminders / cancel_reminder tools

**Files:**
- Modify: `second_brain/agent/tools.py` (`TOOLS_SCHEMA`, `execute_tool` branches)
- Test: `tests/agent/test_tools.py` (extend)

**Interfaces:**
- Consumes: `second_brain.agent.reminders.get_reminder_store()`, `Reminder` (Task 1); `execute_tool(..., chat_id=...)` (Task 2).
- Produces: three new entries in `TOOLS_SCHEMA` the model can call; three new branches in `execute_tool`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/agent/test_tools.py`:

```python
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


def test_execute_tool_set_reminder_invalid_timestamp():
    result = tools.execute_tool(
        "set_reminder",
        {"message": "x", "fire_at": "not-a-real-timestamp"},
        [],
        chat_id=1,
    )
    assert "valid time" in result.lower() or "invalid" in result.lower()


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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/agent/test_tools.py -k reminder -v`
Expected: FAIL -- `set_reminder`/`list_reminders`/`cancel_reminder` aren't in `TOOLS_SCHEMA` or handled by `execute_tool` yet.

- [ ] **Step 3: Add the three tool schemas**

In `second_brain/agent/tools.py`, add the import and append to `TOOLS_SCHEMA` (after the existing `edit_vault_note` entry):

```python
from second_brain.agent import maps, reminders as reminders_module, vault_writer, web_search
```

```python
    {
        "type": "function",
        "function": {
            "name": "set_reminder",
            "description": "Set a one-shot reminder that will be sent as a message at a "
            "specific future time. Compute fire_at yourself from the current time and "
            "what Igor asked for (e.g. 'in 20 minutes', 'tomorrow at 9am').",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The exact message to send when the reminder fires.",
                    },
                    "fire_at": {
                        "type": "string",
                        "description": "ISO 8601 timestamp, e.g. 2026-08-10T15:20:00",
                    },
                },
                "required": ["message", "fire_at"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_reminders",
            "description": "List all pending reminders for the current chat.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_reminder",
            "description": "Cancel a pending reminder by its id (from list_reminders).",
            "parameters": {
                "type": "object",
                "properties": {"reminder_id": {"type": "string"}},
                "required": ["reminder_id"],
            },
        },
    },
```

- [ ] **Step 4: Add a module-level re-export for patchability**

Right below the imports in `second_brain/agent/tools.py`, add:

```python
get_reminder_store = reminders_module.get_reminder_store
```

(This lets tests patch `second_brain.agent.tools.get_reminder_store` directly, matching the existing convention where `execute_tool` calls things imported into this module's own namespace.)

- [ ] **Step 5: Add the three `execute_tool` branches**

In `second_brain/agent/tools.py`, add before the final `return f"Unknown tool: {name}"` line, and add `from datetime import datetime` to the top imports:

```python
    if name == "set_reminder":
        if chat_id is None:
            return "Reminders aren't available: no chat id for this request."
        try:
            fire_at = datetime.fromisoformat(arguments["fire_at"])
        except (KeyError, ValueError):
            return "That's not a valid time -- fire_at must be an ISO 8601 timestamp."
        reminder = get_reminder_store().add(chat_id, fire_at, arguments["message"])
        return f"Reminder set (id: {reminder.id})."

    if name == "list_reminders":
        if chat_id is None:
            return "Reminders aren't available: no chat id for this request."
        pending = get_reminder_store().list_for_chat(chat_id)
        if not pending:
            return "No pending reminders."
        return "\n".join(
            f"- [{r.id}] {r.fire_at.isoformat()}: {r.message}" for r in pending
        )

    if name == "cancel_reminder":
        if chat_id is None:
            return "Reminders aren't available: no chat id for this request."
        try:
            reminder_id = arguments["reminder_id"]
        except KeyError as exc:
            return f"Reminder cancel failed: missing required argument {exc.args[0]!r}."
        cancelled = get_reminder_store().cancel(chat_id=chat_id, reminder_id=reminder_id)
        return "Reminder cancelled." if cancelled else "No reminder found with that id."
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pytest tests/agent/test_tools.py -v`
Expected: PASS, all tests in the file green, including the new reminder ones.

- [ ] **Step 7: Run the full suite**

Run: `pytest -v`
Expected: PASS, no regressions.

- [ ] **Step 8: Commit**

```bash
git add second_brain/agent/tools.py tests/agent/test_tools.py
git commit -m "feat: add set_reminder/list_reminders/cancel_reminder tools"
```

---

### Task 4: reminder_dispatch_job

**Files:**
- Modify: `second_brain/bot/telegram_bot.py` (new job function + `main()` registration)
- Modify: `second_brain/config.py` (new interval constant)
- Test: `tests/bot/test_telegram_bot.py` (extend)

**Interfaces:**
- Consumes: `second_brain.agent.reminders.get_reminder_store()` (Task 1).
- Produces: `reminder_dispatch_job(context) -> None`, registered via `app.job_queue.run_repeating` in `main()`.

- [ ] **Step 1: Add the config value**

Add to `second_brain/config.py`, next to `REMINDER_STORE_PATH`:

```python
# How often reminder_dispatch_job polls for due reminders. A reminder that
# becomes due while the bot is down still fires on the next tick after
# restart, late rather than lost -- see misfire_grace_time on this job's
# registration in bot/telegram_bot.py.
REMINDER_DISPATCH_INTERVAL_SECONDS = 30
```

- [ ] **Step 2: Write the failing test**

Add to `tests/bot/test_telegram_bot.py`:

```python
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

from second_brain.agent.reminders import ReminderStore


def test_reminder_dispatch_job_sends_and_removes_due_reminders(tmp_path):
    store = ReminderStore(persist_path=str(tmp_path / "reminders.json"))
    due = store.add(1, datetime.now() - timedelta(minutes=1), "due reminder")
    store.add(1, datetime.now() + timedelta(hours=1), "not due yet")

    fake_context = type("Ctx", (), {"bot": type("Bot", (), {})()})()
    fake_context.bot.send_message = AsyncMock()

    with patch("second_brain.bot.telegram_bot.get_reminder_store", return_value=store):
        asyncio.run(telegram_bot.reminder_dispatch_job(fake_context))

    fake_context.bot.send_message.assert_called_once_with(chat_id=1, text="due reminder")
    remaining_ids = [r.id for r in store.list_for_chat(1)]
    assert due.id not in remaining_ids
    assert len(remaining_ids) == 1


def test_reminder_dispatch_job_skips_when_nothing_due(tmp_path):
    store = ReminderStore(persist_path=str(tmp_path / "reminders.json"))
    store.add(1, datetime.now() + timedelta(hours=1), "not due yet")

    fake_context = type("Ctx", (), {"bot": type("Bot", (), {})()})()
    fake_context.bot.send_message = AsyncMock()

    with patch("second_brain.bot.telegram_bot.get_reminder_store", return_value=store):
        asyncio.run(telegram_bot.reminder_dispatch_job(fake_context))

    fake_context.bot.send_message.assert_not_called()
    assert len(store.list_for_chat(1)) == 1


def test_reminder_dispatch_job_continues_after_one_send_failure(tmp_path):
    store = ReminderStore(persist_path=str(tmp_path / "reminders.json"))
    store.add(1, datetime.now() - timedelta(minutes=1), "fails to send")
    store.add(2, datetime.now() - timedelta(minutes=1), "sends fine")

    fake_context = type("Ctx", (), {"bot": type("Bot", (), {})()})()
    fake_context.bot.send_message = AsyncMock(side_effect=[Exception("boom"), None])

    with patch("second_brain.bot.telegram_bot.get_reminder_store", return_value=store):
        asyncio.run(telegram_bot.reminder_dispatch_job(fake_context))

    assert fake_context.bot.send_message.call_count == 2
    # the one that failed to send is still pending (not removed); the one
    # that sent successfully is gone
    remaining_messages = {r.message for r in store.list_for_chat(1) + store.list_for_chat(2)}
    assert remaining_messages == {"fails to send"}
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `pytest tests/bot/test_telegram_bot.py -k reminder_dispatch -v`
Expected: FAIL -- `telegram_bot.reminder_dispatch_job` and `telegram_bot.get_reminder_store` don't exist yet.

- [ ] **Step 4: Import and add the job function**

In `second_brain/bot/telegram_bot.py`, add to the imports:

```python
from second_brain.agent.reminders import get_reminder_store
```

Add the job function right after `periodic_save_job` (before `def main():`):

```python
async def reminder_dispatch_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Runs every config.REMINDER_DISPATCH_INTERVAL_SECONDS. Sends and
    removes any reminder whose fire_at has passed. A send failure leaves
    the reminder in place for the next tick to retry, rather than losing
    it -- same "late is fine, lost is not" philosophy as periodic_save_job's
    misfire_grace_time=None below.
    """
    store = get_reminder_store()
    for reminder in store.due(datetime.now()):
        try:
            await context.bot.send_message(chat_id=reminder.chat_id, text=reminder.message)
        except Exception:
            logger.exception(
                "Failed to send reminder id=%s to chat_id=%s", reminder.id, reminder.chat_id
            )
            continue
        store.remove(reminder.id)
```

- [ ] **Step 5: Register the job in `main()`**

In `second_brain/bot/telegram_bot.py`'s `main()`, after the existing `app.job_queue.run_repeating(periodic_save_job, ...)` block, add:

```python
    app.job_queue.run_repeating(
        reminder_dispatch_job,
        interval=config.REMINDER_DISPATCH_INTERVAL_SECONDS,
        first=config.REMINDER_DISPATCH_INTERVAL_SECONDS,
        job_kwargs={"misfire_grace_time": None},
    )
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pytest tests/bot/test_telegram_bot.py -v`
Expected: PASS, all tests in the file green.

- [ ] **Step 7: Run the full suite**

Run: `pytest -v`
Expected: PASS, no regressions.

- [ ] **Step 8: Commit**

```bash
git add second_brain/bot/telegram_bot.py second_brain/config.py tests/bot/test_telegram_bot.py
git commit -m "feat: dispatch due reminders via a recurring poll job"
```

---

### Task 5: System prompt update

**Files:**
- Modify: `second_brain/config.py` (`SYSTEM_PROMPT`)

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing consumed by later tasks -- this is a leaf change.

- [ ] **Step 1: Add a reminders paragraph to `SYSTEM_PROMPT`**

In `second_brain/config.py`, in the `SYSTEM_PROMPT` tuple, after the existing paragraph that ends `"...it returns a real, tappable link, not just a description."` and before the closing `)`, add a new string segment:

```python
    "\n\nYou also have reminder tools: set_reminder, list_reminders, and "
    "cancel_reminder. Use set_reminder when Igor asks to be reminded of "
    "something, computing fire_at yourself from the current time. The same "
    "honesty rule that applies to vault saves applies here even more "
    "directly: never say 'I'll remind you' or anything like it unless you "
    "actually called set_reminder and it succeeded -- a reminder you only "
    "promised in words will never fire.\n\n"
```

- [ ] **Step 2: Verify the prompt still builds without a syntax error**

Run: `python -c "from second_brain import config; print(len(config.SYSTEM_PROMPT))"`
Expected: prints an integer (the prompt's character count), no traceback.

- [ ] **Step 3: Run the full suite**

Run: `pytest -v`
Expected: PASS, no regressions (no test asserts the exact prompt text).

- [ ] **Step 4: Commit**

```bash
git add second_brain/config.py
git commit -m "docs: teach the system prompt about reminder tools and their honesty rule"
```

---

### Task 6: Live verification

**Files:** none (verification-only task; fix in the relevant earlier task's files if something surfaces a real bug, with its own normal commit, not folded into this task).

**Interfaces:**
- Consumes: the fully wired feature from Tasks 1-5, deployed and running (either locally via `docker compose up` or on the VPS -- whichever the project owner is actively using at the time this task runs).

- [ ] **Step 1: Deploy the change**

If testing locally: `docker compose up -d --build`. If testing on the VPS: `ssh root@37.27.32.169 'cd /opt/murzik && git pull && docker compose up -d --build'` (per `docs/deploy-runbook.md`'s "Future Code Updates" section).

- [ ] **Step 2: Set a real short-delay reminder via Telegram**

Send Murzik a message like "remind me in 2 minutes to check the oven." Confirm it replies acknowledging the reminder (not a false "I'll remind you" without a tool call -- check the logs for `Reminder set` if in doubt).

- [ ] **Step 3: Confirm it actually fires**

Wait ~2-3 minutes. Confirm a message arrives unprompted with roughly the content set in Step 2, at roughly the right time (within one `REMINDER_DISPATCH_INTERVAL_SECONDS` tick, i.e. within ~30s of the target).

- [ ] **Step 4: Confirm restart survival**

Set another reminder for ~3 minutes out. Immediately restart the bot (`docker restart murzik_bot` locally, or `ssh root@37.27.32.169 'docker restart murzik_bot'` on the VPS). Confirm the reminder still fires on schedule despite the restart.

- [ ] **Step 5: Confirm list and cancel work end-to-end**

Set two reminders. Ask "what reminders do I have?" and confirm both are listed. Ask to cancel one by describing it in natural language (not by pasting the raw id). Ask again and confirm only the other one remains, then let it fire or cancel it too to avoid a stray real notification.

- [ ] **Step 6: No commit needed for this task itself** -- if any step surfaces a real bug, fix it in the relevant file from Tasks 1-5 and commit that fix separately with a normal descriptive message.
