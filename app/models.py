"""Shared data contracts for the ingestion and query pipelines."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl, field_validator


class SourceDefinition(BaseModel):
    source_id: str
    title: str
    scheme_id: str | None = None
    url: HttpUrl
    enabled: bool = True

    @field_validator("source_id", "title")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value cannot be blank")
        return value


class DocumentSection(BaseModel):
    heading: str
    text: str

    @field_validator("heading", "text")
    @classmethod
    def reject_empty_section_fields(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("document section fields cannot be empty")
        return value


class LoadedDocument(BaseModel):
    source_id: str
    title: str
    scheme_id: str | None = None
    url: HttpUrl
    retrieved_at: datetime
    content_hash: str
    sections: list[DocumentSection] = Field(min_length=1)

    @field_validator("source_id", "title", "content_hash")
    @classmethod
    def reject_blank_document_fields(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("document metadata cannot be blank")
        return value

    @field_validator("content_hash")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value.lower()):
            raise ValueError("content_hash must be a SHA-256 hexadecimal digest")
        return value.lower()


class ChunkRecord(BaseModel):
    chunk_id: str
    source_id: str
    scheme_id: str | None = None
    section: str
    fact_type: str = "general"
    text: str
    source_url: HttpUrl
    retrieved_at: datetime

    @field_validator("chunk_id", "source_id", "section", "fact_type", "text")
    @classmethod
    def reject_blank_chunk_fields(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("chunk fields cannot be blank")
        return value


class IndexManifest(BaseModel):
    base_collection: str
    active_collection: str
    index_version: str
    embedding_model: str
    embedding_dimension: int = Field(gt=0)
    normalized_embeddings: bool
    chunk_count: int = Field(gt=0)
    source_ids: list[str] = Field(min_length=1)
    created_at: datetime
    status: str


class Citation(BaseModel):
    source_id: str
    label: str
    url: HttpUrl


class GeneratedAnswer(BaseModel):
    category: str
    answer_text: str
    selected_source_id: str
    evidence_chunk_ids: list[str] = Field(min_length=1)


class QueryResponse(BaseModel):
    category: str
    answer: str
    citation: Citation
    source_updated_at: datetime
    evidence_chunk_ids: list[str] = Field(default_factory=list)

