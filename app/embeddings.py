"""Sentence-transformer document and query embeddings."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import EmbeddingSettings, PROJECT_ROOT
from app.models import ChunkRecord


class EmbeddingError(RuntimeError):
    """The configured embedding model could not produce compatible vectors."""


@dataclass(frozen=True)
class EmbeddingBatch:
    vectors: tuple[tuple[float, ...], ...]
    model_name: str
    dimension: int
    normalized: bool


class EmbeddingService:
    """Lazy wrapper around Sentence Transformers.

    A compatible model object can be injected by tests so unit tests do not need to
    download or initialize the real model.
    """

    def __init__(self, settings: EmbeddingSettings, *, model: Any | None = None) -> None:
        self.settings = settings
        self._model = model

    @property
    def model_name(self) -> str:
        return self.settings.model

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbeddingError(
                "sentence-transformers is not installed; install requirements before indexing"
            ) from exc
        try:
            self._model = SentenceTransformer(self.settings.model)
        except Exception as exc:
            raise EmbeddingError(
                f"Unable to load embedding model '{self.settings.model}': {exc}"
            ) from exc
        return self._model

    @staticmethod
    def _to_vectors(raw_vectors: Any) -> tuple[tuple[float, ...], ...]:
        rows = raw_vectors.tolist() if hasattr(raw_vectors, "tolist") else raw_vectors
        try:
            vectors = tuple(tuple(float(value) for value in row) for row in rows)
        except (TypeError, ValueError) as exc:
            raise EmbeddingError("Embedding model returned an invalid vector structure") from exc
        if not vectors or not vectors[0]:
            raise EmbeddingError("Embedding model returned no vectors")
        dimension = len(vectors[0])
        if any(len(vector) != dimension for vector in vectors):
            raise EmbeddingError("Embedding vectors have inconsistent dimensions")
        if any(not math.isfinite(value) for vector in vectors for value in vector):
            raise EmbeddingError("Embedding vectors contain non-finite values")
        return vectors

    def _encode(self, texts: list[str], *, batch_size: int) -> tuple[tuple[float, ...], ...]:
        if not texts or any(not text.strip() for text in texts):
            raise EmbeddingError("Embedding input cannot be empty")
        model = self._load_model()
        try:
            raw_vectors = model.encode(
                texts,
                batch_size=batch_size,
                show_progress_bar=False,
                normalize_embeddings=self.settings.normalize,
                convert_to_numpy=True,
            )
        except Exception as exc:
            raise EmbeddingError(f"Embedding generation failed: {exc}") from exc
        vectors = self._to_vectors(raw_vectors)
        if len(vectors) != len(texts):
            raise EmbeddingError("Embedding count does not match input count")
        return vectors

    def embed_documents(self, texts: list[str]) -> EmbeddingBatch:
        vectors = self._encode(texts, batch_size=self.settings.batch_size)
        return EmbeddingBatch(
            vectors=vectors,
            model_name=self.model_name,
            dimension=len(vectors[0]),
            normalized=self.settings.normalize,
        )

    def embed_query(self, text: str) -> tuple[float, ...]:
        return self._encode([text], batch_size=1)[0]


def embed_chunks(
    chunks: tuple[ChunkRecord, ...] | list[ChunkRecord],
    service: EmbeddingService,
) -> EmbeddingBatch:
    if not chunks:
        raise EmbeddingError("No chunks supplied for embedding")
    return service.embed_documents([chunk.text for chunk in chunks])


def write_embedding_manifest(
    chunks: tuple[ChunkRecord, ...] | list[ChunkRecord],
    batch: EmbeddingBatch,
    path: Path | str | None = None,
) -> Path:
    manifest_path = (
        Path(path)
        if path is not None
        else PROJECT_ROOT / "data/chunks/embedding_manifest.json"
    )
    if not manifest_path.is_absolute():
        manifest_path = PROJECT_ROOT / manifest_path
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "model": batch.model_name,
        "dimension": batch.dimension,
        "normalized": batch.normalized,
        "chunk_count": len(chunks),
        "chunk_ids_hash": __import__("hashlib").sha256(
            "\n".join(chunk.chunk_id for chunk in chunks).encode("utf-8")
        ).hexdigest(),
        "status": "READY",
    }
    temporary_path = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    temporary_path.replace(manifest_path)
    return manifest_path

