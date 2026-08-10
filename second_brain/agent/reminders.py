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
