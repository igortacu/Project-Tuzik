"""Watches an Obsidian vault for markdown file changes."""

import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from queue import Empty, Queue

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


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


class _DebouncedHandler(FileSystemEventHandler):
    """Collapses rapid successive filesystem events for the same path into a
    single FileChanged, emitted debounce_seconds after the last event settles.
    """

    def __init__(self, debounce_seconds: float, emit: Callable[[FileChanged], None]) -> None:
        self._debounce_seconds = debounce_seconds
        self._emit = emit
        self._timers: dict[str, threading.Timer] = {}
        self._pending_type: dict[str, ChangeType] = {}
        self._lock = threading.Lock()

    def _schedule(self, path: str, event_type: ChangeType) -> None:
        if not path.endswith(".md"):
            return
        with self._lock:
            self._pending_type[path] = event_type
            existing = self._timers.get(path)
            if existing:
                existing.cancel()
            timer = threading.Timer(self._debounce_seconds, self._fire, args=(path,))
            timer.daemon = True
            self._timers[path] = timer
            timer.start()

    def _fire(self, path: str) -> None:
        with self._lock:
            event_type = self._pending_type.pop(path, ChangeType.MODIFIED)
            self._timers.pop(path, None)

        raw_text: str | None = None
        if event_type != ChangeType.DELETED:
            try:
                raw_text = Path(path).read_text(encoding="utf-8")
            except FileNotFoundError:
                event_type = ChangeType.DELETED

        self._emit(FileChanged(path=Path(path), event_type=event_type, raw_text=raw_text))

    def on_created(self, event) -> None:
        if not event.is_directory:
            self._schedule(event.src_path, ChangeType.CREATED)

    def on_modified(self, event) -> None:
        if not event.is_directory:
            self._schedule(event.src_path, ChangeType.MODIFIED)

    def on_deleted(self, event) -> None:
        if not event.is_directory:
            self._schedule(event.src_path, ChangeType.DELETED)

    def on_moved(self, event) -> None:
        if not event.is_directory:
            self._schedule(event.src_path, ChangeType.DELETED)
            self._schedule(event.dest_path, ChangeType.CREATED)


class VaultWatcher:
    """Wraps `watchdog` to watch .md files under a vault root, debouncing rapid
    successive save events into a single FileChanged per settle period.
    """

    def __init__(self, vault_path: Path, debounce_seconds: float = 1.0) -> None:
        self._vault_path = Path(vault_path)
        self._debounce_seconds = debounce_seconds
        self._observer: Observer | None = None

    def watch(self, on_change: Callable[[FileChanged], None]) -> None:
        """Block, invoking on_change for each debounced file event until stopped."""
        handler = _DebouncedHandler(self._debounce_seconds, on_change)
        self._observer = Observer()
        self._observer.schedule(handler, str(self._vault_path), recursive=True)
        self._observer.start()
        try:
            while self._observer.is_alive():
                self._observer.join(timeout=1.0)
        except KeyboardInterrupt:
            self.stop()

    def stop(self) -> None:
        if self._observer is not None:
            self._observer.stop()
            self._observer.join()
            self._observer = None

    def __iter__(self) -> Iterator[FileChanged]:
        """Alternative to watch(): yields FileChanged events as they settle."""
        queue: Queue[FileChanged] = Queue()
        handler = _DebouncedHandler(self._debounce_seconds, queue.put)
        observer = Observer()
        observer.schedule(handler, str(self._vault_path), recursive=True)
        observer.start()
        self._observer = observer
        try:
            while True:
                try:
                    yield queue.get(timeout=1.0)
                except Empty:
                    continue
        finally:
            observer.stop()
            observer.join()
