"""Tests for embedding input/output compatibility without downloading a model."""

from app.config import EmbeddingSettings
from app.embeddings import EmbeddingError, EmbeddingService


class FakeModel:
    def encode(self, texts, **_):
        return [[float(index + 1), 0.0, 1.0] for index, _text in enumerate(texts)]


def test_document_and_query_embeddings_have_same_dimension() -> None:
    service = EmbeddingService(EmbeddingSettings(), model=FakeModel())

    batch = service.embed_documents(["first", "second"])
    query = service.embed_query("question")

    assert len(batch.vectors) == 2
    assert batch.dimension == 3
    assert len(query) == batch.dimension
    assert batch.model_name == "sentence-transformers/all-MiniLM-L6-v2"


def test_empty_embedding_input_is_rejected() -> None:
    service = EmbeddingService(EmbeddingSettings(), model=FakeModel())

    try:
        service.embed_documents([])
    except EmbeddingError as exc:
        assert "empty" in str(exc).lower() or "no chunks" in str(exc).lower()
    else:
        raise AssertionError("Empty embedding input should fail")
