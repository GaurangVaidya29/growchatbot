"""Load, validate, and summarize the extracted source documents."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.config import PROJECT_ROOT
from app.models import LoadedDocument, SourceDefinition
from app.scraper import canonicalize_url, load_source_registry


class DocumentLoadError(RuntimeError):
    """Extracted documents are missing, malformed, or untrusted."""


@dataclass(frozen=True)
class DocumentLoadResult:
    documents: tuple[LoadedDocument, ...]
    loaded_count: int
    expected_count: int
    warnings: tuple[str, ...] = ()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        raise DocumentLoadError(f"Extracted document is not valid UTF-8: {path.name}") from exc
    except json.JSONDecodeError as exc:
        raise DocumentLoadError(f"Malformed JSON in extracted document: {path.name}") from exc
    if not isinstance(payload, dict):
        raise DocumentLoadError(f"Extracted document root must be an object: {path.name}")
    return payload


def load_documents(
    extracted_directory: Path | str | None = None,
    *,
    registry_path: Path | str | None = None,
) -> DocumentLoadResult:
    """Load exactly one validated document for every approved source."""

    directory = (
        Path(extracted_directory)
        if extracted_directory is not None
        else PROJECT_ROOT / "data/extracted"
    )
    if not directory.is_absolute():
        directory = PROJECT_ROOT / directory
    if not directory.is_dir():
        raise DocumentLoadError(
            f"Extracted directory does not exist: {directory}. Run the scrape stage first."
        )

    sources = load_source_registry(registry_path)
    source_by_id: dict[str, SourceDefinition] = {source.source_id: source for source in sources}
    expected_ids = set(source_by_id)
    files = sorted(directory.glob("SRC-*.json"))
    if not files:
        raise DocumentLoadError("No extracted documents found. Run the scrape stage first.")

    documents: list[LoadedDocument] = []
    seen_ids: set[str] = set()
    warnings: list[str] = []
    for path in files:
        payload = _read_json(path)
        try:
            document = LoadedDocument.model_validate(payload)
        except ValidationError as exc:
            raise DocumentLoadError(f"Invalid extracted document {path.name}: {exc}") from exc

        if document.source_id in seen_ids:
            raise DocumentLoadError(f"Duplicate extracted source: {document.source_id}")
        if document.source_id not in source_by_id:
            raise DocumentLoadError(f"Unregistered extracted source: {document.source_id}")
        if path.stem != document.source_id:
            raise DocumentLoadError(
                f"Filename/source mismatch: {path.name} contains {document.source_id}"
            )

        trusted_source = source_by_id[document.source_id]
        if canonicalize_url(str(document.url)) != canonicalize_url(str(trusted_source.url)):
            raise DocumentLoadError(f"Untrusted URL in {path.name}")
        if document.title != trusted_source.title:
            raise DocumentLoadError(f"Title mismatch in {path.name}")
        if document.scheme_id != trusted_source.scheme_id:
            raise DocumentLoadError(f"Scheme ID mismatch in {path.name}")
        if document.retrieved_at.tzinfo is None:
            raise DocumentLoadError(f"retrieved_at must include a timezone in {path.name}")

        seen_ids.add(document.source_id)
        documents.append(document)

    missing_ids = expected_ids - seen_ids
    extra_ids = seen_ids - expected_ids
    if missing_ids or extra_ids:
        raise DocumentLoadError(
            f"Document set mismatch; missing={sorted(missing_ids)}, extra={sorted(extra_ids)}"
        )

    return DocumentLoadResult(
        documents=tuple(sorted(documents, key=lambda item: item.source_id)),
        loaded_count=len(documents),
        expected_count=len(expected_ids),
        warnings=tuple(warnings),
    )


def write_load_manifest(
    result: DocumentLoadResult,
    path: Path | str | None = None,
) -> Path:
    """Write a human-readable validation summary for the loading phase."""

    manifest_path = (
        Path(path) if path is not None else PROJECT_ROOT / "data/extracted/load_manifest.json"
    )
    if not manifest_path.is_absolute():
        manifest_path = PROJECT_ROOT / manifest_path
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "expected_count": result.expected_count,
        "loaded_count": result.loaded_count,
        "source_ids": [document.source_id for document in result.documents],
        "warnings": list(result.warnings),
        "status": "READY" if result.loaded_count == result.expected_count else "FAILED",
    }
    temporary_path = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    temporary_path.replace(manifest_path)
    return manifest_path

