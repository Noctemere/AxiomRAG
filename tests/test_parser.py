from uuid import uuid4

import pytest

from apps.worker.parser import ParsedBlock, ParserRegistry, PlainTextParser
from packages.contracts.models import Modality


def test_plain_text_parser_creates_provenance_blocks() -> None:
    """Verify paragraphs become text blocks linked to the source document."""
    document_id = uuid4()
    tenant_id = uuid4()
    parser = PlainTextParser()

    blocks = parser.parse(
        document_id=document_id,
        tenant_id=tenant_id,
        content=b"First paragraph.\n\nSecond paragraph.",
        content_type="text/plain",
    )

    assert len(blocks) == 2
    assert all(isinstance(block, ParsedBlock) for block in blocks)
    assert [block.content for block in blocks] == ["First paragraph.", "Second paragraph."]
    assert all(block.modality is Modality.TEXT for block in blocks)
    assert all(block.provenance.document_id == document_id for block in blocks)
    assert all(block.provenance.page_number == 1 for block in blocks)
    assert all(block.tenant_id == tenant_id for block in blocks)


def test_plain_text_parser_ignores_blank_paragraphs() -> None:
    """Verify empty sections do not become searchable content."""
    blocks = PlainTextParser().parse(
        document_id=uuid4(),
        tenant_id=uuid4(),
        content=b"\n\nOnly content\n\n",
        content_type="text/plain",
    )
    assert [block.content for block in blocks] == ["Only content"]


def test_plain_text_parser_rejects_invalid_utf8() -> None:
    """Verify invalid source encoding fails instead of silently corrupting text."""
    with pytest.raises(UnicodeDecodeError):
        PlainTextParser().parse(
            document_id=uuid4(), tenant_id=uuid4(), content=b"\xff", content_type="text/plain"
        )


def test_parser_registry_selects_parser_by_mime_type() -> None:
    """Verify MIME-based parser selection."""
    parser = PlainTextParser()
    registry = ParserRegistry([parser])
    assert registry.get("text/plain") is parser
    assert registry.get("text/markdown") is parser


def test_parser_registry_rejects_unknown_mime_type() -> None:
    """Verify unsupported formats fail clearly."""
    with pytest.raises(ValueError, match="no parser registered"):
        ParserRegistry([PlainTextParser()]).get("application/pdf")
