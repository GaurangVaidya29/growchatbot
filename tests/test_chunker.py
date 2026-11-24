"""Tests for deterministic structure-aware chunks."""

from datetime import UTC, datetime

from app.chunker import build_chunks
from app.config import ChunkingSettings
from app.models import DocumentSection, LoadedDocument


def _document() -> LoadedDocument:
    return LoadedDocument(
        source_id="SRC-02",
        title="HDFC Large Cap Fund Direct Growth",
        scheme_id="hdfc_large_cap_direct_growth",
        url="https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
        retrieved_at=datetime.now(UTC),
        content_hash="b" * 64,
        sections=[
            DocumentSection(heading="Expense ratio", text="Expense ratio: 0.99%"),
            DocumentSection(
                heading="Exit load",
                text="Exit load: Exit load of 1% if redeemed within 1 year",
            ),
            DocumentSection(
                heading="Returns and rankings",
                text="Performance content that must not be indexed.",
            ),
            DocumentSection(
                heading="Overview",
                text="A factual scheme overview. " * 40,
            ),
        ],
    )


def test_preserves_atomic_facts_and_excludes_performance() -> None:
    result = build_chunks([_document()], ChunkingSettings(target_tokens=40, overlap_tokens=5))

    expense_chunks = [chunk for chunk in result.chunks if chunk.fact_type == "expense_ratio"]
    exit_chunks = [chunk for chunk in result.chunks if chunk.fact_type == "exit_load"]
    assert len(expense_chunks) == 1
    assert "0.99%" in expense_chunks[0].text
    assert len(exit_chunks) == 1
    assert "within 1 year" in exit_chunks[0].text
    assert not any("Performance content" in chunk.text for chunk in result.chunks)


def test_chunk_ids_are_deterministic() -> None:
    settings = ChunkingSettings(target_tokens=40, overlap_tokens=5)

    first = build_chunks([_document()], settings)
    second = build_chunks([_document()], settings)

    assert [chunk.chunk_id for chunk in first.chunks] == [
        chunk.chunk_id for chunk in second.chunks
    ]


def test_long_narrative_is_split() -> None:
    result = build_chunks([_document()], ChunkingSettings(target_tokens=20, overlap_tokens=3))

    overview_chunks = [chunk for chunk in result.chunks if chunk.section == "Overview"]
    assert len(overview_chunks) > 1

