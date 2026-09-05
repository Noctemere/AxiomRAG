import pytest

from apps.worker.sparse_vector import SparseVectorizer


def test_sparse_vectorizer_is_deterministic_and_sorted() -> None:
    """Verify token IDs are stable, unique, and ordered for Qdrant."""
    vectorizer = SparseVectorizer(vocabulary_size=2_048)
    first = vectorizer.transform(["Alpha beta alpha"])[0]
    second = vectorizer.transform(["Alpha beta alpha"])[0]

    assert first == second
    indices, values = first
    assert indices == sorted(indices)
    assert len(indices) == len(values) == 2
    assert 2.0 in values
    assert 1.0 in values


def test_sparse_vectorizer_rejects_tiny_vocabulary() -> None:
    """Verify sparse IDs have a sufficiently large collision space."""
    with pytest.raises(ValueError, match="at least 1024"):
        SparseVectorizer(vocabulary_size=32)