# Reminders for Murzik — Design

## Context

Murzik already hallucinated a reminder promise in a real conversation ("Și în 20 de minute îți reamintesc" — "and I'll remind you in 20 minutes") with zero mechanism to back it up. There is no reminders feature today. Igor asked for one, specifying that each reminder timer must be "isolated, independent, for a given task" — confirmed during brainstorming to mean: setting, editing, or cancelling one reminder never touches any other pending reminder; multiple reminders can be in flight at once, each independently tracked.

The bot already runs 24/7 on a VPS (see `docs/superpowers/specs/2026-08-09-containerize-deploy-design.md`) and gets restarted for deploys, so reminders must survive a restart — losing a pending reminder silently on restart would just be the original bug in a new form.

## Decisions

- **Isolation**: each reminder is an independent record with its own id, chat, fire time, and message. No shared timers, no batching.
- **Restart survival**: reminders are persisted to disk (`data/reminders.json`), not held only in in-memory scheduler state.
- **Fire-time format**: the model computes an absolute ISO timestamp itself (it already has the current time available in context) rather than the tool doing natural-language date parsing. Keeps the tool's own logic simple.
- **Scope for v1**: includes list and cancel, not just set-and-fire, per Igor's explicit choice.

## Architecture

**Why not `JobQueue.run_once` per reminder**: the tool-execution code that creates a reminder (`execute_tool()` in `second_brain/agent/tools.py`) runs deep inside a synchronous call stack (`llm_client._run_tool_loop` → `LLMClient.generate_with_tools` → `query_pipeline.answer_query`, invoked via `asyncio.to_thread` from the bot's message handler) that has no access to the `Application`/`JobQueue` object living in `telegram_bot.py`. Threading that object down through every layer just to schedule one job is exactly the kind of layering violation the existing module boundaries (retrieval never imports generation, etc.) are meant to avoid.

**Chosen design**: reminders are rows in a persisted store, not scheduled jobs. One lightweight recurring job — the same pattern already used for `periodic_save_job` — polls the store every 30 seconds for anything due, sends it, and removes it. This is also what makes restart-survival free: the store is the source of truth, not in-memory scheduler state, so a restart just means the next poll tick picks up wherever it left off (including firing anything that became due while the bot was down, late rather than lost — same philosophy as the existing `misfire_grace_time=None` fix).

## Components

**`second_brain/agent/reminders.py`** (new) — `Reminder` dataclass (`id: str`, `chat_id: int`, `fire_at: datetime`, `message: str`) and `ReminderStore`, persisted to `data/reminders.json`, mirroring `second_brain/bot/memory.py`'s existing `SaveBuffer` persistence pattern exactly (load on `__init__`, persist after every mutation — no separate save step to forget):
- `add(chat_id, fire_at, message) -> Reminder`
- `cancel(chat_id, reminder_id) -> bool` — scoped to `chat_id`, so one chat can never list or cancel another chat's reminder (Igor and his wife each only see their own).
- `list_for_chat(chat_id) -> list[Reminder]`
- `due(now) -> list[Reminder]` — across all chats, for the dispatcher job.
- `remove(reminder_id) -> None`

**Three new tools** in `second_brain/agent/tools.py`'s `TOOLS_SCHEMA`, alongside the existing `web_search`/`image_search`/`get_directions_link`/`append_vault_note`/`edit_vault_note`:
- `set_reminder(message: str, fire_at: str)` — `fire_at` is an ISO 8601 timestamp.
- `list_reminders()` — no arguments; scoped to the calling chat via the plumbing change below. Lets the model answer "what reminders do I have?" and gives it the reminder ids it needs to resolve a later "cancel the foil one" to a specific id.
- `cancel_reminder(reminder_id: str)`.

**Plumbing change**: `execute_tool(name, arguments, image_urls_out)` currently has no notion of which chat is calling it. It needs a new `chat_id: int` parameter, threaded through the full call chain: `telegram_bot._answer_message` (already has `chat_id` locally) → `query_pipeline.answer_query(question, history=..., chat_id=chat_id)` → `LLMClient.generate_with_tools(..., chat_id=chat_id)` → `_run_tool_loop(messages, chat_id)` → `tools_module.execute_tool(name, arguments, image_urls_out, chat_id)`. This is required regardless of reminders specifically, since `list_reminders`/`cancel_reminder` must be scoped per-chat — but reminders are the first tool that needs it, so this plumbing lands as part of this feature.

**Dispatch**: one new recurring job in `telegram_bot.py`, `reminder_dispatch_job`, registered the same way as `periodic_save_job`:
```python
app.job_queue.run_repeating(
    reminder_dispatch_job,
    interval=config.REMINDER_DISPATCH_INTERVAL_SECONDS,
    first=config.REMINDER_DISPATCH_INTERVAL_SECONDS,
    job_kwargs={"misfire_grace_time": None},
)
```
Every tick: `_reminder_store.due(datetime.now())`, and for each due reminder, `context.bot.send_message(chat_id=reminder.chat_id, text=reminder.message)` followed by `_reminder_store.remove(reminder.id)`. The message text is composed once by the model at set-time (in-character, via the `message` argument to `set_reminder`) — no LLM call happens at fire-time, keeping the dispatcher trivial, cheap, and unable to fail on an OpenRouter outage.

**System prompt**: add a short paragraph to `config.SYSTEM_PROMPT` describing the three new tools and when to use them, and explicitly extend the existing "never claim something happened that didn't" honesty rule (already covers periodic saves) to cover reminders: the model must actually call `set_reminder`, never just say "I'll remind you" in prose without the tool call actually succeeding.

**`config.py`** additions: `REMINDER_STORE_PATH = "data/reminders.json"`, `REMINDER_DISPATCH_INTERVAL_SECONDS = 30`.

## Data flow example

1. Igor: "remind me in 20 minutes to take out the roast."
2. Model resolves "in 20 minutes" against the current time (already in its context) to an ISO timestamp, calls `set_reminder(message="🔥 Scoate friptura din cuptor!", fire_at="2026-08-10T15:20:00")`.
3. `execute_tool` calls `ReminderStore.add(chat_id, fire_at, message)`, which persists immediately to `data/reminders.json` and returns confirmation text fed back to the model, which relays it to Igor.
4. Bot restarts for an unrelated deploy at 15:05. `data/reminders.json` is a bind-mounted host path (same as `save_buffer.json` today), so the reminder survives.
5. At the next dispatcher tick at or after 15:20, `reminder_dispatch_job` finds it due, sends "🔥 Scoate friptura din cuptor!" to Igor's chat, removes it from the store.

## Error handling

- `set_reminder` with a `fire_at` that fails `datetime.fromisoformat()` parsing: `execute_tool` catches `ValueError` and returns a text error the model can relay ("that didn't parse as a valid time"), same pattern as the existing `KeyError` handling for missing tool arguments.
- `cancel_reminder` with an unknown or already-fired id, or an id belonging to a different chat: `ReminderStore.cancel` returns `False` (not an exception), `execute_tool` returns "no reminder with that id" text.
- `reminder_dispatch_job` wraps each individual send in its own try/except (matching `periodic_save_job`'s per-chat exception handling) so one failed Telegram send (e.g. bot blocked by the user) doesn't stop other due reminders in the same tick from firing.

## Testing

- `tests/agent/test_reminders.py`: `ReminderStore` persistence (survives a simulated restart, mirroring the existing `SaveBuffer` restart test), chat-scoped `cancel`/`list_for_chat` isolation, `due()` correctness around the boundary time.
- `tests/agent/test_tools.py`: new cases for `set_reminder`/`list_reminders`/`cancel_reminder` dispatch through `execute_tool`, including the invalid-timestamp and wrong-chat-cancel error paths.
- Live verification: set a real short-delay reminder (e.g. 1-2 minutes) via Telegram, confirm it fires with the right text at roughly the right time; restart the bot mid-wait for a pending reminder and confirm it still fires after restart; list reminders with more than one pending; cancel one by referencing it in natural language and confirm only that one is gone.

## Out of scope

- Recurring/repeating reminders (daily, weekly) — only one-shot reminders for v1.
- Editing an existing reminder's time/text in place (cancel + re-set covers this).
- Any reminder UI beyond natural-language chat (no `/reminders` slash command).
