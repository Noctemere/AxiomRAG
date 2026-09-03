from uuid import uuid4

import pytest

from apps.worker.chunking import ChunkingService
from apps.worker.parser import ParsedBlock
from packages.contracts.models import Modality, Provenance


def make_block(content: str) -> ParsedBlock:
    """Create a parser block with valid source provenance for tests."""
    document_id = uuid4()
    return ParsedBlock(
        block_id=uuid4(),
        content=content,
        modality=Modality.TEXT,
        provenance=Provenance(document_id=document_id, page_number=2, region_id="p2-r1"),
        tenant_id=uuid4(),
    )


def test_chunking_preserves_content_and_provenance() -> None:
    """Verify chunks retain source identity and modality."""
    block = make_block("A short source paragraph")
    chunks = ChunkingService(max_characters=100).chunk_blocks([block])

    assert len(chunks) == 1
    assert chunks[0].content == block.content
    assert chunks[0].document_id == block.provenance.document_id
    assert chunks[0].provenance == block.provenance
    assert chunks[0].modality is Modality.TEXT


def test_chunking_splits_on_word_boundaries() -> None:
    """Verify long blocks are bounded without splitting words."""
    block = make_block("one two three four five")
    chunks = ChunkingService(max_characters=10).chunk_blocks([block])

    assert [chunk.content for chunk in chunks] == ["one two", "three four", "five"]
    assert all(len(chunk.content) <= 10 for chunk in chunks)


def test_chunking_skips_empty_blocks() -> None:
    """Verify whitespace-only parser output is not indexed."""
    assert ChunkingService().chunk_blocks([make_block("  \n\t")]) == []


def test_chunking_rejects_invalid_limit() -> None:
    """Verify invalid chunk configuration fails during construction."""
    with pytest.raises(ValueError, match="positive"):
        ChunkingService(max_characters=0)
