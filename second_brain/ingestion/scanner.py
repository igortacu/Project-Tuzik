"""Full-vault walk used to build the index from scratch."""

from collections.abc import Iterator
from pathlib import Path


class VaultScanner:
    """Walks a vault root and yields every markdown note's raw text.

    Uniform with VaultWatcher's output: downstream code consumes
    (filepath, raw_markdown) pairs regardless of which module produced them.
    """

    def __init__(self, vault_path: Path) -> None:
        self._vault_path = Path(vault_path)

    def scan(self) -> Iterator[tuple[Path, str]]:
        """Yield (path, raw_text) for every .md file under the vault root."""
        for path in sorted(self._vault_path.rglob("*.md")):
            if path.is_file():
                yield path, path.read_text(encoding="utf-8")
