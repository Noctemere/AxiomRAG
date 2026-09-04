from typing import Any
from uuid import uuid4

import pytest

from apps.worker.docling_parser import DoclingParser
from apps.worker.parser import ParsedBlock, ParsedDocument, ParserRegistry, PlainTextParser
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

    assert isinstance(blocks, ParsedDocument)
    assert len(blocks.blocks) == 2
    assert all(isinstance(block, ParsedBlock) for block in blocks.blocks)
    assert [block.content for block in blocks.blocks] == ["First paragraph.", "Second paragraph."]
    assert all(block.modality is Modality.TEXT for block in blocks.blocks)
    assert all(block.provenance.document_id == document_id for block in blocks.blocks)
    assert all(block.provenance.page_number == 1 for block in blocks.blocks)
    assert all(block.tenant_id == tenant_id for block in blocks.blocks)


def test_plain_text_parser_ignores_blank_paragraphs() -> None:
    """Verify empty sections do not become searchable content."""
    blocks = PlainTextParser().parse(
        document_id=uuid4(),
        tenant_id=uuid4(),
        content=b"\n\nOnly content\n\n",
        content_type="text/plain",
    )
    assert [block.content for block in blocks.blocks] == ["Only content"]


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


class FakeDoclingDocument:
    """Test double for the narrow Docling document interface."""

    def export_to_markdown(self) -> str:
        return "# Heading\n\nExtracted PDF content"


class FakeBoundingBox:
    """Test bounding box matching Docling's coordinate attributes."""

    left = 10.0
    t = 20.0
    r = 100.0
    b = 40.0

    @property
    def l(self) -> float:  # noqa: E743
        return self.left


class FakeProvenance:
    """Test page and region provenance matching Docling's item metadata."""

    page_no = 3
    bbox = FakeBoundingBox()


class FakeTextItem:
    """Test text item returned by Docling item iteration."""

    text = "Page-aware PDF text"
    prov = [FakeProvenance()]


class PageAwareFakeDoclingDocument(FakeDoclingDocument):
    """Test document exposing Docling's page-aware item iterator."""

    def iterate_items(self) -> list[tuple[FakeTextItem, int]]:
        return [(FakeTextItem(), 0)]


class FakeDoclingResult:
    """Test double for a Docling conversion result."""

    document = FakeDoclingDocument()


class PageAwareFakeDoclingResult:
    """Test conversion result containing page-aware document items."""

    document = PageAwareFakeDoclingDocument()


class FakeDoclingConverter:
    """Test converter that records the source passed to the adapter."""

    def __init__(self) -> None:
        self.source = None

    def convert(self, source: object) -> Any:
        self.source = source
        return FakeDoclingResult()


class PageAwareFakeDoclingConverter(FakeDoclingConverter):
    """Test converter returning page-aware items."""

    def convert(self, source: object) -> Any:
        self.source = source
        return PageAwareFakeDoclingResult()


def test_docling_parser_normalizes_markdown() -> None:
    """Verify Docling output becomes tenant-scoped parsed blocks."""
    converter = FakeDoclingConverter()
    document_id = uuid4()
    tenant_id = uuid4()
    blocks = DoclingParser(converter).parse(
        document_id=document_id,
        tenant_id=tenant_id,
        content=b"%PDF-fake",
        content_type="application/pdf",
    )

    assert [block.content for block in blocks.blocks] == ["# Heading", "Extracted PDF content"]
    assert all(block.provenance.document_id == document_id for block in blocks.blocks)
    assert all(block.tenant_id == tenant_id for block in blocks.blocks)
    assert converter.source is not None


def test_docling_parser_rejects_empty_pdf() -> None:
    """Verify empty PDFs fail before invoking the converter."""
    with pytest.raises(ValueError, match="empty"):
        DoclingParser(FakeDoclingConverter()).parse(
            document_id=uuid4(),
            tenant_id=uuid4(),
            content=b"",
            content_type="application/pdf",
        )


def test_docling_parser_preserves_page_and_region_provenance() -> None:
    """Verify real Docling item provenance is converted to citation metadata."""
    blocks = DoclingParser(PageAwareFakeDoclingConverter()).parse(
        document_id=uuid4(),
        tenant_id=uuid4(),
        content=b"%PDF-fake",
        content_type="application/pdf",
    )

    assert len(blocks.blocks) == 1
    assert blocks.blocks[0].content == "Page-aware PDF text"
    assert blocks.blocks[0].provenance.page_number == 3
    assert blocks.blocks[0].provenance.region_id == "bbox:10.00,20.00,100.00,40.00"
