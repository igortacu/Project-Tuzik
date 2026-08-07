"""Watches an Obsidian vault for markdown file changes."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ChangeType(Enum):
    CREATED = "created"
    MODIFIED = "modified"
    DELETED = "deleted"


@dataclass
class FileChanged:
    """A single debounced change event for one markdown file.

    Uniform with VaultScanner's output: downstream code consumes
    (filepath, raw_markdown) pairs regardless of which module produced them.
    """

    path: Path
    event_type: ChangeType
    raw_text: str | None  # None when event_type is DELETED


class VaultWatcher:
    """Wraps `watchdog` to watch .md files under a vault root, debouncing rapid
    successive save events into a single FileChanged per settle period.
    """

    def __init__(self, vault_path: Path, debounce_seconds: float = 1.0) -> None:
        raise NotImplementedError

    def watch(self, on_change: Callable[[FileChanged], None]) -> None:
        """Block, invoking on_change for each debounced file event until stopped."""
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def __iter__(self) -> Iterator[FileChanged]:
        """Alternative to watch(): yields FileChanged events as they settle."""
        raise NotImplementedError
