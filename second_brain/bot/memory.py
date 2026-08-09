"""In-process, per-chat conversation history (short-term memory).

Not persisted -- restarting the bot clears it, by design (simplest option;
nothing else in this project defaults to more infrastructure than it needs).
"""

from collections import deque


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
    """

    def __init__(self) -> None:
        self._buffers: dict[int, list[tuple[str, str]]] = {}

    def append(self, chat_id: int, user_message: str, assistant_reply: str) -> None:
        self._buffers.setdefault(chat_id, []).append((user_message, assistant_reply))

    def drain(self, chat_id: int) -> list[tuple[str, str]]:
        """Returns and clears the buffer for chat_id. Empty list if there's
        nothing buffered (e.g. no new messages since the last drain).
        """
        return self._buffers.pop(chat_id, [])

    def chat_ids(self) -> list[int]:
        return list(self._buffers.keys())
