"""Typed application configuration loaded from YAML and the environment."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"


class ScrapingSettings(BaseModel):
    timeout_seconds: int = Field(default=20, gt=0)
    max_retries: int = Field(default=2, ge=0)
    follow_links: bool = False
    max_response_bytes: int = Field(default=5_000_000, gt=0)
    min_extracted_characters: int = Field(default=100, gt=0)
    user_agent: str = "GrowwMFFAQDemo/0.1 (facts-only educational prototype)"

    @model_validator(mode="after")
    def prevent_recursive_crawling(self) -> "ScrapingSettings":
        if self.follow_links:
            raise ValueError("follow_links must remain false for the approved-source demo")
        return self

    @field_validator("user_agent")
    @classmethod
    def require_user_agent(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("user_agent cannot be empty")
        return value


class ChunkingSettings(BaseModel):
    target_tokens: int = Field(default=400, gt=0)
    overlap_tokens: int = Field(default=50, ge=0)

    @model_validator(mode="after")
    def validate_overlap(self) -> "ChunkingSettings":
        if self.overlap_tokens >= self.target_tokens:
            raise ValueError("overlap_tokens must be smaller than target_tokens")
        return self


class EmbeddingSettings(BaseModel):
    provider: Literal["sentence_transformers"] = "sentence_transformers"
    model: str = "sentence-transformers/all-MiniLM-L6-v2"
    batch_size: int = Field(default=32, gt=0)
    normalize: bool = True

    @field_validator("model")
    @classmethod
    def require_model_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("embedding model cannot be empty")
        return value


class VectorDatabaseSettings(BaseModel):
    provider: Literal["chroma"] = "chroma"
    collection: str = "groww_hdfc_mf_faq"
    persist_directory: Path = Path("data/chroma")

    @field_validator("collection")
    @classmethod
    def require_collection_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("vector database collection cannot be empty")
        return value

    @field_validator("persist_directory")
    @classmethod
    def require_safe_relative_path(cls, value: Path) -> Path:
        if value.is_absolute() or ".." in value.parts:
            raise ValueError("persist_directory must be a safe project-relative path")
        return value


class RetrievalSettings(BaseModel):
    top_k: int = Field(default=5, gt=0)
    score_threshold: float = Field(default=0.50, ge=0.0, le=1.0)


class ResponseSettings(BaseModel):
    max_sentences: Literal[3] = 3
    citation_count: Literal[1] = 1


class AppConfig(BaseModel):
    scraping: ScrapingSettings = Field(default_factory=ScrapingSettings)
    chunking: ChunkingSettings = Field(default_factory=ChunkingSettings)
    embeddings: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    vector_db: VectorDatabaseSettings = Field(default_factory=VectorDatabaseSettings)
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)
    response: ResponseSettings = Field(default_factory=ResponseSettings)


class EnvironmentSettings(BaseSettings):
    """Secret-bearing runtime settings.

    Values are read from the process environment. A future application bootstrap can
    use pydantic-settings to load a local .env file after dependencies are installed.
    """

    llm_provider: Literal["groq"] = "groq"
    llm_model: str = "qwen/qwen3.8-27b"
    groq_api_key: SecretStr | None = None
    ui_debug: bool = False

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def from_environment(cls) -> "EnvironmentSettings":
        return cls()


def load_config(path: Path | str | None = None) -> AppConfig:
    """Load and validate the non-secret YAML configuration."""

    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path
    if not config_path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as handle:
        raw_config = yaml.safe_load(handle) or {}

    if not isinstance(raw_config, dict):
        raise ValueError("Configuration root must be a YAML mapping")
    return AppConfig.model_validate(raw_config)


def ensure_data_directories(config: AppConfig) -> tuple[Path, ...]:
    """Create the project-local data directories used by later phases."""

    relative_paths = (
        Path("data/raw"),
        Path("data/extracted"),
        Path("data/chunks"),
        config.vector_db.persist_directory,
        Path("data/evaluations"),
    )
    resolved_paths: list[Path] = []
    for relative_path in relative_paths:
        resolved = (PROJECT_ROOT / relative_path).resolve()
        if PROJECT_ROOT.resolve() not in resolved.parents:
            raise ValueError(f"Data directory escapes the project root: {relative_path}")
        resolved.mkdir(parents=True, exist_ok=True)
        resolved_paths.append(resolved)
    return tuple(resolved_paths)

