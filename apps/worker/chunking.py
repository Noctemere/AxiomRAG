from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from apps.worker.parser import ParsedBlock
from packages.contracts.models import DocumentChunk


class ChunkingService:
    """Convert parser blocks into bounded, provenance-preserving chunks."""

    def __init__(self, max_characters: int = 2_000) -> None:
        if max_characters < 1:
            raise ValueError("max_characters must be positive")
        self._max_characters = max_characters

    def chunk_blocks(self, blocks: list[ParsedBlock]) -> list[DocumentChunk]:
        """Split blocks on word boundaries while retaining source provenance."""
        chunks: list[DocumentChunk] = []
        for block in blocks:
            chunks.extend(self._chunk_block(block))
        return chunks

    def _chunk_block(self, block: ParsedBlock) -> list[DocumentChunk]:
        words = block.content.split()
        if not words:
            return []

        pieces: list[str] = []
        current: list[str] = []
        current_length = 0
        for word in words:
            separator_length = 1 if current else 0
            if current and current_length + separator_length + len(word) > self._max_characters:
                pieces.append(" ".join(current))
                current = []
                current_length = 0
            current.append(word)
            current_length += (1 if len(current) > 1 else 0) + len(word)
        if current:
            pieces.append(" ".join(current))

        return [
            DocumentChunk(
                chunk_id=uuid4(),
                document_id=block.provenance.document_id,
                tenant_id=block.tenant_id,
                content=piece,
                modality=block.modality,
                provenance=block.provenance,
                created_at=datetime.now(UTC),
            )
            for piece in pieces
        ]


class ChunkIdFactory:
    """Create deterministic IDs for chunk persistence boundaries in tests."""

    @staticmethod
    def new_id() -> UUID:
        """Return a new chunk identifier."""
        return uuid4()
