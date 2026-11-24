"""Tests for trusted extracted-document loading."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.document_loader import DocumentLoadError, load_documents
from app.scraper import load_source_registry


def _write_valid_documents(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for source in load_source_registry():
        payload = {
            "source_id": source.source_id,
            "title": source.title,
            "scheme_id": source.scheme_id,
            "url": str(source.url),
            "retrieved_at": datetime.now(UTC).isoformat(),
            "content_hash": "a" * 64,
            "sections": [{"heading": "Overview", "text": "Validated public source text."}],
        }
        (directory / f"{source.source_id}.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )


def test_loads_exactly_five_validated_documents(tmp_path: Path) -> None:
    extracted = tmp_path / "extracted"
    _write_valid_documents(extracted)

    result = load_documents(extracted)

    assert result.loaded_count == 5
    assert result.expected_count == 5
    assert [document.source_id for document in result.documents] == [
        "SRC-01",
        "SRC-02",
        "SRC-03",
        "SRC-04",
        "SRC-05",
    ]


def test_rejects_untrusted_document_url(tmp_path: Path) -> None:
    extracted = tmp_path / "extracted"
    _write_valid_documents(extracted)
    path = extracted / "SRC-01.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["url"] = "https://groww.in/unapproved-page"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(DocumentLoadError, match="Untrusted URL"):
        load_documents(extracted)


def test_rejects_missing_document(tmp_path: Path) -> None:
    extracted = tmp_path / "extracted"
    _write_valid_documents(extracted)
    (extracted / "SRC-05.json").unlink()

    with pytest.raises(DocumentLoadError, match="Document set mismatch"):
        load_documents(extracted)


def test_rejects_malformed_json(tmp_path: Path) -> None:
    extracted = tmp_path / "extracted"
    _write_valid_documents(extracted)
    (extracted / "SRC-01.json").write_text("{bad json", encoding="utf-8")

    with pytest.raises(DocumentLoadError, match="Malformed JSON"):
        load_documents(extracted)

