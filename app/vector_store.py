"""Persistent ChromaDB indexing with an active-index manifest."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import PROJECT_ROOT, VectorDatabaseSettings
from app.embeddings import EmbeddingBatch
from app.models import ChunkRecord, IndexManifest


class VectorStoreError(RuntimeError):
    """ChromaDB is missing, incompatible, or failed an index operation."""


@dataclass(frozen=True)
class VectorSearchHit:
    chunk_id: str
    text: str
    score: float
    metadata: dict[str, Any]


def _load_chromadb() -> Any:
    try:
        import chromadb
    except ImportError as exc:
        raise VectorStoreError(
            "chromadb is not installed; install requirements before indexing"
        ) from exc
    return chromadb


def _index_version(chunks: tuple[ChunkRecord, ...], batch: EmbeddingBatch) -> str:
    payload = "\n".join(
        [
            batch.model_name,
            str(batch.dimension),
            str(batch.normalized),
            *(chunk.chunk_id for chunk in chunks),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ChromaVectorStore:
    def __init__(
        self,
        settings: VectorDatabaseSettings,
        *,
        project_root: Path = PROJECT_ROOT,
        client: Any | None = None,
    ) -> None:
        self.settings = settings
        self.project_root = project_root.resolve()
        self.persist_directory = (self.project_root / settings.persist_directory).resolve()
        if self.project_root not in self.persist_directory.parents:
            raise VectorStoreError("Chroma persistence directory escapes the project root")
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.persist_directory / "index_manifest.json"
        if client is None:
            chromadb = _load_chromadb()
            client = chromadb.PersistentClient(path=str(self.persist_directory))
        self.client = client

    def _read_manifest(self) -> IndexManifest | None:
        if not self.manifest_path.is_file():
            return None
        try:
            return IndexManifest.model_validate_json(
                self.manifest_path.read_text(encoding="utf-8")
            )
        except Exception as exc:
            raise VectorStoreError(f"Invalid index manifest: {exc}") from exc

    def _write_manifest(self, manifest: IndexManifest) -> None:
        temporary_path = self.manifest_path.with_suffix(".json.tmp")
        temporary_path.write_text(
            json.dumps(
                manifest.model_dump(mode="json"),
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        temporary_path.replace(self.manifest_path)

    def _collection_exists(self, name: str) -> bool:
        try:
            self.client.get_collection(name=name)
            return True
        except Exception:
            return False

    def build_index(
        self,
        chunks: tuple[ChunkRecord, ...] | list[ChunkRecord],
        batch: EmbeddingBatch,
    ) -> IndexManifest:
        chunks_tuple = tuple(chunks)
        if not chunks_tuple:
            raise VectorStoreError("No chunks supplied for indexing")
        if len(chunks_tuple) != len(batch.vectors):
            raise VectorStoreError("Chunk and embedding counts do not match")
        if len({chunk.chunk_id for chunk in chunks_tuple}) != len(chunks_tuple):
            raise VectorStoreError("Duplicate chunk IDs cannot be indexed")
        if any(len(vector) != batch.dimension for vector in batch.vectors):
            raise VectorStoreError("Embedding dimensions are inconsistent")

        version = _index_version(chunks_tuple, batch)
        collection_name = f"{self.settings.collection}_{version[:12]}"
        current_manifest = self._read_manifest()
        if (
            current_manifest is not None
            and current_manifest.index_version == version
            and current_manifest.status == "READY"
            and self._collection_exists(current_manifest.active_collection)
        ):
            collection = self.client.get_collection(name=current_manifest.active_collection)
            if collection.count() == len(chunks_tuple):
                return current_manifest

        if self._collection_exists(collection_name):
            self.client.delete_collection(name=collection_name)
        try:
            collection = self.client.create_collection(
                name=collection_name,
                metadata={
                    "hnsw:space": "cosine",
                    "embedding_model": batch.model_name,
                    "normalized_embeddings": str(batch.normalized).lower(),
                },
            )
            batch_size = 100
            for start in range(0, len(chunks_tuple), batch_size):
                chunk_batch = chunks_tuple[start : start + batch_size]
                vector_batch = batch.vectors[start : start + batch_size]
                collection.upsert(
                    ids=[chunk.chunk_id for chunk in chunk_batch],
                    documents=[chunk.text for chunk in chunk_batch],
                    embeddings=[list(vector) for vector in vector_batch],
                    metadatas=[
                        {
                            "source_id": chunk.source_id,
                            "scheme_id": chunk.scheme_id or "",
                            "section": chunk.section,
                            "fact_type": chunk.fact_type,
                            "source_url": str(chunk.source_url),
                            "retrieved_at": chunk.retrieved_at.isoformat(),
                        }
                        for chunk in chunk_batch
                    ],
                )
            if collection.count() != len(chunks_tuple):
                raise VectorStoreError(
                    f"Indexed count mismatch: expected {len(chunks_tuple)}, got {collection.count()}"
                )
            sample = collection.get(ids=[chunks_tuple[0].chunk_id], include=["metadatas"])
            if not sample.get("ids") or sample["ids"][0] != chunks_tuple[0].chunk_id:
                raise VectorStoreError("Unable to verify an indexed sample record")
        except Exception as exc:
            if self._collection_exists(collection_name):
                self.client.delete_collection(name=collection_name)
            if isinstance(exc, VectorStoreError):
                raise
            raise VectorStoreError(f"ChromaDB index build failed: {exc}") from exc

        manifest = IndexManifest(
            base_collection=self.settings.collection,
            active_collection=collection_name,
            index_version=version,
            embedding_model=batch.model_name,
            embedding_dimension=batch.dimension,
            normalized_embeddings=batch.normalized,
            chunk_count=len(chunks_tuple),
            source_ids=sorted({chunk.source_id for chunk in chunks_tuple}),
            created_at=datetime.now(UTC),
            status="READY",
        )
        self._write_manifest(manifest)
        return manifest

    def validate_compatibility(
        self,
        *,
        embedding_model: str,
        embedding_dimension: int | None = None,
        normalized_embeddings: bool | None = None,
    ) -> IndexManifest:
        manifest = self._read_manifest()
        if manifest is None or manifest.status != "READY":
            raise VectorStoreError("No READY ChromaDB index manifest found")
        if manifest.base_collection != self.settings.collection:
            raise VectorStoreError("Configured collection does not match the active index")
        if manifest.embedding_model != embedding_model:
            raise VectorStoreError("Embedding model does not match the active index")
        if embedding_dimension is not None and manifest.embedding_dimension != embedding_dimension:
            raise VectorStoreError("Embedding dimension does not match the active index")
        if (
            normalized_embeddings is not None
            and manifest.normalized_embeddings != normalized_embeddings
        ):
            raise VectorStoreError("Embedding normalization does not match the active index")
        if not self._collection_exists(manifest.active_collection):
            raise VectorStoreError("Active ChromaDB collection is missing")
        collection = self.client.get_collection(name=manifest.active_collection)
        if collection.count() != manifest.chunk_count:
            raise VectorStoreError("Active ChromaDB collection count does not match its manifest")
        return manifest

    def search(
        self,
        query_embedding: tuple[float, ...] | list[float],
        *,
        top_k: int,
        filters: dict[str, Any] | None = None,
        embedding_model: str,
    ) -> tuple[VectorSearchHit, ...]:
        if top_k <= 0:
            raise VectorStoreError("top_k must be positive")
        manifest = self.validate_compatibility(
            embedding_model=embedding_model,
            embedding_dimension=len(query_embedding),
        )
        collection = self.client.get_collection(name=manifest.active_collection)
        query_arguments: dict[str, Any] = {
            "query_embeddings": [list(query_embedding)],
            "n_results": min(top_k, manifest.chunk_count),
            "include": ["documents", "metadatas", "distances"],
        }
        if filters:
            query_arguments["where"] = filters
        result = collection.query(**query_arguments)
        ids = result.get("ids", [[]])[0]
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        return tuple(
            VectorSearchHit(
                chunk_id=identifier,
                text=document or "",
                score=max(-1.0, min(1.0, 1.0 - float(distance))),
                metadata=dict(metadata or {}),
            )
            for identifier, document, metadata, distance in zip(
                ids, documents, metadatas, distances, strict=True
            )
        )

    def health_check(self) -> bool:
        try:
            manifest = self._read_manifest()
            if manifest is None:
                return False
            self.validate_compatibility(embedding_model=manifest.embedding_model)
            return True
        except VectorStoreError:
            return False

