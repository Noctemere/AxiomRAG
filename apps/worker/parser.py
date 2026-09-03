from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid4

from packages.contracts.models import Modality, Provenance


@dataclass(frozen=True)
class ParsedBlock:
    """Normalized parser output that can later become a retrievable chunk."""

    block_id: UUID
    content: str
    modality: Modality
    provenance: Provenance
    tenant_id: UUID


class DocumentParser(Protocol):
    """Adapter boundary for Docling, OCR, or another layout-aware parser."""

    @property
    def supported_content_types(self) -> frozenset[str]:
        """MIME types accepted by the parser."""
        ...

    def parse(
        self,
        *,
        document_id: UUID,
        tenant_id: UUID,
        content: bytes,
        content_type: str,
    ) -> list[ParsedBlock]:
        """Extract normalized blocks from a document."""
        ...


class PlainTextParser:
    """Deterministic parser for plain text and Markdown development fixtures."""

    supported_content_types = frozenset({"text/plain", "text/markdown"})

    def parse(
        self,
        *,
        document_id: UUID,
        tenant_id: UUID,
        content: bytes,
        content_type: str,
    ) -> list[ParsedBlock]:
        """Decode UTF-8 text and emit one provenance-preserving block per paragraph."""
        if content_type not in self.supported_content_types:
            raise ValueError(f"unsupported content type: {content_type}")

        text = content.decode("utf-8")
        blocks: list[ParsedBlock] = []
        for paragraph in (part.strip() for part in text.split("\n\n")):
            if not paragraph:
                continue
            blocks.append(
                ParsedBlock(
                    block_id=uuid4(),
                    content=paragraph,
                    modality=Modality.TEXT,
                    provenance=Provenance(document_id=document_id, page_number=1),
                    tenant_id=tenant_id,
                )
            )
        return blocks


class ParserRegistry:
    """Selects a parser by MIME type and keeps parser choice out of task code."""

    def __init__(self, parsers: list[DocumentParser]) -> None:
        self._parsers = parsers

    def get(self, content_type: str) -> DocumentParser:
        """Return the first parser that supports the requested MIME type."""
        for parser in self._parsers:
            if content_type in parser.supported_content_types:
                return parser
        raise ValueError(f"no parser registered for content type: {content_type}")
