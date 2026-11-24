"""Deterministic, structure-aware chunking for validated documents."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.config import ChunkingSettings, PROJECT_ROOT
from app.models import ChunkRecord, LoadedDocument


EXCLUDED_HEADINGS = {
    "return calculator",
    "returns and rankings",
    "compare similar funds",
    "annualised returns",
    "absolute returns",
}


class ChunkingError(RuntimeError):
    """Documents cannot be converted to valid chunks."""


@dataclass(frozen=True)
class ChunkingResult:
    chunks: tuple[ChunkRecord, ...]
    source_count: int
    skipped_sections: int
    duplicate_chunks: int


def _normalize(value: str) -> str:
    return " ".join(value.split())


def classify_fact_type(heading: str, text: str) -> str:
    """Classify only direct evidence; explanatory definitions remain general."""

    combined = f"{heading} {text}".lower()
    if "expense ratio" in combined and re.search(r"\b\d+(?:\.\d+)?%", text):
        return "expense_ratio"
    if "exit load" in combined and ("exit load of" in text.lower() or re.search(r"\bnil\b", text, re.I)):
        return "exit_load"
    if "minimum sip" in combined and re.search(r"\d", text):
        return "minimum_sip"
    if "lock-in" in combined or "lock in" in combined:
        return "lock_in"
    if ("risk level" in combined or "riskometer" in combined) and "risk" in text.lower():
        return "riskometer"
    if "benchmark" in combined and ":" in text:
        return "benchmark"
    return "general"


def _estimated_tokens(value: str) -> int:
    return len(re.findall(r"\w+|[^\w\s]", value, re.UNICODE))


def _split_long_text(text: str, target_tokens: int, overlap_tokens: int) -> list[str]:
    """Split narrative content near sentence boundaries with bounded overlap."""

    text = _normalize(text)
    if _estimated_tokens(text) <= target_tokens:
        return [text]

    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
    if len(sentences) == 1:
        words = text.split()
        step = max(1, target_tokens - overlap_tokens)
        return [" ".join(words[start : start + target_tokens]) for start in range(0, len(words), step)]

    chunks: list[str] = []
    current: list[str] = []
    for sentence in sentences:
        candidate = " ".join([*current, sentence])
        if current and _estimated_tokens(candidate) > target_tokens:
            completed = " ".join(current)
            chunks.append(completed)
            overlap_words = completed.split()[-overlap_tokens:] if overlap_tokens else []
            current = [" ".join(overlap_words), sentence] if overlap_words else [sentence]
        else:
            current.append(sentence)
    if current:
        chunks.append(" ".join(current))
    return [_normalize(chunk) for chunk in chunks if _normalize(chunk)]


def _chunk_id(source_id: str, section: str, fact_type: str, text: str) -> str:
    canonical = "\n".join((source_id, section, fact_type, _normalize(text)))
    return f"chk_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:24]}"


def build_chunks(
    documents: tuple[LoadedDocument, ...] | list[LoadedDocument],
    settings: ChunkingSettings,
) -> ChunkingResult:
    """Build atomic fact chunks and bounded narrative chunks."""

    if not documents:
        raise ChunkingError("No validated documents supplied")

    chunks: list[ChunkRecord] = []
    seen_ids: set[str] = set()
    skipped_sections = 0
    duplicate_chunks = 0

    for document in sorted(documents, key=lambda item: item.source_id):
        for section in document.sections:
            heading = _normalize(section.heading)
            text = _normalize(section.text)
            lowered_heading = heading.lower()
            if (
                lowered_heading in EXCLUDED_HEADINGS
                or lowered_heading.startswith("holdings")
                or lowered_heading.startswith("list of hdfc mutual fund")
            ):
                skipped_sections += 1
                continue

            fact_type = classify_fact_type(heading, text)
            parts = (
                [text]
                if fact_type != "general"
                else _split_long_text(
                    text,
                    target_tokens=settings.target_tokens,
                    overlap_tokens=settings.overlap_tokens,
                )
            )
            for part in parts:
                contextual_text = (
                    f"Scheme: {document.title}\n"
                    f"Section: {heading}\n"
                    f"{part}"
                )
                identifier = _chunk_id(
                    document.source_id,
                    heading,
                    fact_type,
                    contextual_text,
                )
                if identifier in seen_ids:
                    duplicate_chunks += 1
                    continue
                seen_ids.add(identifier)
                chunks.append(
                    ChunkRecord(
                        chunk_id=identifier,
                        source_id=document.source_id,
                        scheme_id=document.scheme_id,
                        section=heading,
                        fact_type=fact_type,
                        text=contextual_text,
                        source_url=document.url,
                        retrieved_at=document.retrieved_at,
                    )
                )

    if not chunks:
        raise ChunkingError("Chunking produced no records")
    return ChunkingResult(
        chunks=tuple(chunks),
        source_count=len({chunk.source_id for chunk in chunks}),
        skipped_sections=skipped_sections,
        duplicate_chunks=duplicate_chunks,
    )


def write_chunk_artifacts(
    result: ChunkingResult,
    *,
    output_path: Path | str | None = None,
    manifest_path: Path | str | None = None,
) -> tuple[Path, Path]:
    """Write JSONL chunks and a small build manifest atomically."""

    chunks_path = Path(output_path) if output_path is not None else PROJECT_ROOT / "data/chunks/chunks.jsonl"
    summary_path = (
        Path(manifest_path)
        if manifest_path is not None
        else PROJECT_ROOT / "data/chunks/chunk_manifest.json"
    )
    if not chunks_path.is_absolute():
        chunks_path = PROJECT_ROOT / chunks_path
    if not summary_path.is_absolute():
        summary_path = PROJECT_ROOT / summary_path
    chunks_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    chunks_temp = chunks_path.with_suffix(chunks_path.suffix + ".tmp")
    with chunks_temp.open("w", encoding="utf-8", newline="\n") as handle:
        for chunk in result.chunks:
            handle.write(json.dumps(chunk.model_dump(mode="json"), ensure_ascii=False, sort_keys=True))
            handle.write("\n")
    chunks_temp.replace(chunks_path)

    payload = {
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "chunk_count": len(result.chunks),
        "source_count": result.source_count,
        "source_ids": sorted({chunk.source_id for chunk in result.chunks}),
        "fact_type_counts": {
            fact_type: sum(chunk.fact_type == fact_type for chunk in result.chunks)
            for fact_type in sorted({chunk.fact_type for chunk in result.chunks})
        },
        "skipped_sections": result.skipped_sections,
        "duplicate_chunks": result.duplicate_chunks,
        "status": "READY",
    }
    summary_temp = summary_path.with_suffix(summary_path.suffix + ".tmp")
    summary_temp.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    summary_temp.replace(summary_path)
    return chunks_path, summary_path


def load_chunks(path: Path | str | None = None) -> tuple[ChunkRecord, ...]:
    """Load and validate persisted JSONL chunks for embedding."""

    chunks_path = Path(path) if path is not None else PROJECT_ROOT / "data/chunks/chunks.jsonl"
    if not chunks_path.is_absolute():
        chunks_path = PROJECT_ROOT / chunks_path
    if not chunks_path.is_file():
        raise ChunkingError("Chunk file is missing. Run the chunk stage first.")

    chunks: list[ChunkRecord] = []
    seen_ids: set[str] = set()
    with chunks_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                chunk = ChunkRecord.model_validate_json(line)
            except ValidationError as exc:
                raise ChunkingError(f"Invalid chunk on line {line_number}: {exc}") from exc
            if chunk.chunk_id in seen_ids:
                raise ChunkingError(f"Duplicate chunk ID: {chunk.chunk_id}")
            seen_ids.add(chunk.chunk_id)
            chunks.append(chunk)
    if not chunks:
        raise ChunkingError("Chunk file contains no records")
    return tuple(chunks)

