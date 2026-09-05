from __future__ import annotations

import re
from collections import Counter


class SparseVectorizer:
    """Create deterministic token-id/value sparse vectors for Qdrant."""

    model_name = "local-bm25-token-hash"

    def __init__(self, vocabulary_size: int = 2**20) -> None:
        if vocabulary_size < 1_024:
            raise ValueError("vocabulary size must be at least 1024")
        self.vocabulary_size = vocabulary_size

    def transform(self, texts: list[str]) -> list[tuple[list[int], list[float]]]:
        """Return sorted token IDs and term-frequency values per input text."""
        return [self._transform_one(text) for text in texts]

    def _transform_one(self, text: str) -> tuple[list[int], list[float]]:
        counts = Counter(re.findall(r"\w+", text.lower()))
        pairs = sorted(
            ((self._token_id(token), float(count)) for token, count in counts.items()),
            key=lambda pair: pair[0],
        )
        return [pair[0] for pair in pairs], [pair[1] for pair in pairs]

    def _token_id(self, token: str) -> int:
        value = 2166136261
        for byte in token.encode("utf-8"):
            value = (value ^ byte) * 16777619 & 0xFFFFFFFF
        return value % self.vocabulary_size
