from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any, Protocol, cast
from uuid import UUID, uuid4

from apps.worker.parser import ParsedBlock
from packages.contracts.models import Modality, Provenance


class DoclingDocument(Protocol):
    """Small portion of the Docling document API used by this adapter."""

    def export_to_markdown(self) -> str:
        """Export layout-aware document content as Markdown."""
        ...

    def iterate_items(self) -> Any:
        """Iterate document items and their hierarchy levels."""
        ...


class DoclingConversionResult(Protocol):
    """Small portion of a Docling conversion result used by this adapter."""

    document: DoclingDocument


class DoclingConverter(Protocol):
    """Converter boundary that keeps Docling replaceable and testable."""

    def convert(self, source: Any) -> DoclingConversionResult:
        """Convert a document stream into a Docling result."""
        ...


@dataclass(frozen=True)
class DoclingParser:
    """Parse PDFs with Docling and normalize the result for the ingestion pipeline."""

    converter: DoclingConverter
    supported_content_types: frozenset[str] = frozenset({"application/pdf"})

    @classmethod
    def create_default(cls) -> DoclingParser:
        """Create the production adapter using Docling's default converter."""
        from docling.document_converter import DocumentConverter

        return cls(converter=cast(DoclingConverter, DocumentConverter()))

    def parse(
        self,
        *,
        document_id: UUID,
        tenant_id: UUID,
        content: bytes,
        content_type: str,
    ) -> list[ParsedBlock]:
        """Convert PDF bytes and emit one provenance-preserving block per section."""
        if content_type not in self.supported_content_types:
            raise ValueError(f"unsupported content type: {content_type}")
        if not content:
            raise ValueError("document content is empty")

        source = self._document_stream(content)
        result = self.converter.convert(source)
        blocks = self._items_to_blocks(
            result.document,
            document_id=document_id,
            tenant_id=tenant_id,
        )
        if blocks:
            return blocks
        markdown = result.document.export_to_markdown()
        return self._markdown_to_blocks(markdown, document_id=document_id, tenant_id=tenant_id)

    @staticmethod
    def _document_stream(content: bytes) -> Any:
        """Create the Docling stream object without importing Docling during test discovery."""
        from docling.datamodel.base_models import DocumentStream

        return DocumentStream(name="document.pdf", stream=BytesIO(content))

    @staticmethod
    def _markdown_to_blocks(
        markdown: str,
        *,
        document_id: UUID,
        tenant_id: UUID,
    ) -> list[ParsedBlock]:
        """Split exported Markdown into non-empty sections with source provenance."""
        blocks: list[ParsedBlock] = []
        for section in (part.strip() for part in markdown.split("\n\n")):
            if not section:
                continue
            blocks.append(
                ParsedBlock(
                    block_id=uuid4(),
                    content=section,
                    modality=Modality.TEXT,
                    provenance=Provenance(document_id=document_id, page_number=1),
                    tenant_id=tenant_id,
                )
            )
        return blocks

    @staticmethod
    def _items_to_blocks(
        document: DoclingDocument,
        *,
        document_id: UUID,
        tenant_id: UUID,
    ) -> list[ParsedBlock]:
        """Convert Docling text items into blocks with page and bounding-box provenance."""
        iterate_items = getattr(document, "iterate_items", None)
        if iterate_items is None:
            return []

        blocks: list[ParsedBlock] = []
        for item, _level in iterate_items():
            content = getattr(item, "text", None)
            if not isinstance(content, str) or not content.strip():
                continue
            provenance_items = getattr(item, "prov", [])
            provenance = provenance_items[0] if provenance_items else None
            page_number = getattr(provenance, "page_no", None)
            bbox = getattr(provenance, "bbox", None)
            region_id = None
            if bbox is not None:
                region_id = f"bbox:{bbox.l:.2f},{bbox.t:.2f},{bbox.r:.2f},{bbox.b:.2f}"
            blocks.append(
                ParsedBlock(
                    block_id=uuid4(),
                    content=content.strip(),
                    modality=Modality.TEXT,
                    provenance=Provenance(
                        document_id=document_id,
                        page_number=page_number,
                        region_id=region_id,
                    ),
                    tenant_id=tenant_id,
                )
            )
        return blocks
