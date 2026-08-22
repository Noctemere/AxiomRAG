from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Protocol


class DocumentStore(Protocol):
    async def save(self, storage_key: str, content: bytes) -> None:
        """Persist document bytes under a deterministic storage key."""
        ...

    async def read(self, storage_key: str) -> bytes:
        """Read document bytes previously persisted under a storage key."""
        ...


def content_sha256(content: bytes) -> str:
    """Return the lowercase SHA-256 digest used for content identity and deduplication."""
    return hashlib.sha256(content).hexdigest()


class LocalDocumentStore:
    """Development document store; production storage can implement DocumentStore."""

    def __init__(self, root: Path) -> None:
        self._root = root

    async def save(self, storage_key: str, content: bytes) -> None:
        path = self._safe_path(storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    async def read(self, storage_key: str) -> bytes:
        return self._safe_path(storage_key).read_bytes()

    def _safe_path(self, storage_key: str) -> Path:
        candidate = (self._root / storage_key).resolve()
        root = self._root.resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError("storage key escapes the document store root")
        return candidate