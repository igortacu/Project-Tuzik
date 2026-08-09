"""Per-chat conversation history.

ConversationMemory (short-term, bounded LLM-context window) stays in-process
only, cleared on restart -- losing recent chat context after a restart is a
minor UX ding, nothing is permanently lost. SaveBuffer is different: it's the
raw material for the periodic vault save, and losing it silently on restart
means genuinely losing something Igor asked to be remembered -- so it
persists to disk.
"""

import json
import os
from collections import deque

from second_brain import config


class ConversationMemory:
    """Keeps the last max_turns (user, assistant) exchanges per chat_id."""

    def __init__(self, max_turns: int) -> None:
        self._max_turns = max_turns
        self._history: dict[int, deque[tuple[str, str]]] = {}

    def get(self, chat_id: int) -> list[tuple[str, str]]:
        """Returns [(role, content), ...] oldest first, role is "user" or
        "assistant". Empty list if there's no history for this chat yet.
        """
        return list(self._history.get(chat_id, ()))

    def append(self, chat_id: int, user_message: str, assistant_reply: str) -> None:
        history = self._history.setdefault(chat_id, deque(maxlen=self._max_turns * 2))
        history.append(("user", user_message))
        history.append(("assistant", assistant_reply))


class SaveBuffer:
    """Accumulates (user_message, assistant_reply) turns per chat_id since
    the last drain. Unbounded, unlike ConversationMemory -- meant to be
    periodically compressed and saved (see bot/telegram_bot.py's periodic
    job), then cleared via drain().

    Persisted to config.SAVE_BUFFER_PATH after every write, and reloaded on
    construction -- a bot restart before the next periodic save no longer
    silently discards whatever was buffered.
    """

    def __init__(self, persist_path: str | None = None) -> None:
        self._persist_path = persist_path or config.SAVE_BUFFER_PATH
        self._buffers: dict[int, list[tuple[str, str]]] = {}
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self._persist_path):
            return
        with open(self._persist_path, encoding="utf-8") as f:
            raw = json.load(f)
        self._buffers = {
            int(chat_id): [tuple(turn) for turn in turns] for chat_id, turns in raw.items()
        }

    def _persist(self) -> None:
        os.makedirs(os.path.dirname(self._persist_path) or ".", exist_ok=True)
        with open(self._persist_path, "w", encoding="utf-8") as f:
            json.dump({str(chat_id): turns for chat_id, turns in self._buffers.items()}, f)

    def append(self, chat_id: int, user_message: str, assistant_reply: str) -> None:
        self._buffers.setdefault(chat_id, []).append((user_message, assistant_reply))
        self._persist()

    def drain(self, chat_id: int) -> list[tuple[str, str]]:
        """Returns and clears the buffer for chat_id. Empty list if there's
        nothing buffered (e.g. no new messages since the last drain).
        """
        turns = self._buffers.pop(chat_id, [])
        if turns:
            self._persist()
        return turns

    def chat_ids(self) -> list[int]:
        return list(self._buffers.keys())
