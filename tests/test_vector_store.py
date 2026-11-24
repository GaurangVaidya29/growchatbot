"""ChromaDB integration tests for idempotent indexing and search."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

chromadb = pytest.importorskip("chromadb")

from app.config import VectorDatabaseSettings
from app.embeddings import EmbeddingBatch
from app.models import ChunkRecord
from app.vector_store import ChromaVectorStore, VectorStoreError


def _chunks() -> tuple[ChunkRecord, ...]:
    return (
        ChunkRecord(
            chunk_id="chk_expense",
            source_id="SRC-02",
            scheme_id="hdfc_large_cap_direct_growth",
            section="Expense ratio",
            fact_type="expense_ratio",
            text="Scheme: HDFC Large Cap Fund Direct Growth\nExpense ratio: 0.99%",
            source_url="https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
            retrieved_at=datetime.now(UTC),
        ),
        ChunkRecord(
            chunk_id="chk_exit",
            source_id="SRC-02",
            scheme_id="hdfc_large_cap_direct_growth",
            section="Exit load",
            fact_type="exit_load",
            text="Scheme: HDFC Large Cap Fund Direct Growth\nExit load: 1% within 1 year",
            source_url="https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
            retrieved_at=datetime.now(UTC),
        ),
    )


def _batch() -> EmbeddingBatch:
    return EmbeddingBatch(
        vectors=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        model_name="test-model",
        dimension=3,
        normalized=True,
    )


def test_build_is_idempotent_and_searchable(tmp_path: Path) -> None:
    client = chromadb.EphemeralClient()
    settings = VectorDatabaseSettings(collection="test_groww_collection")
    store = ChromaVectorStore(settings, project_root=tmp_path, client=client)

    first = store.build_index(_chunks(), _batch())
    second = store.build_index(_chunks(), _batch())
    hits = store.search(
        (1.0, 0.0, 0.0),
        top_k=1,
        embedding_model="test-model",
        filters={"scheme_id": "hdfc_large_cap_direct_growth"},
    )
    unfiltered_hits = store.search(
        (0.0, 1.0, 0.0),
        top_k=1,
        embedding_model="test-model",
    )

    assert first.index_version == second.index_version
    assert first.chunk_count == 2
    assert hits[0].chunk_id == "chk_expense"
    assert unfiltered_hits[0].chunk_id == "chk_exit"
    assert store.health_check() is True


def test_model_mismatch_is_rejected(tmp_path: Path) -> None:
    store = ChromaVectorStore(
        VectorDatabaseSettings(collection="test_mismatch_collection"),
        project_root=tmp_path,
        client=chromadb.EphemeralClient(),
    )
    store.build_index(_chunks(), _batch())

    with pytest.raises(VectorStoreError, match="Embedding model"):
        store.validate_compatibility(embedding_model="different-model")

