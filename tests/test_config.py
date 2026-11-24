"""Phase 1 configuration and import smoke tests."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import AppConfig, EnvironmentSettings, load_config


def test_default_config_loads() -> None:
    config = load_config()

    assert config.scraping.follow_links is False
    assert config.embeddings.provider == "sentence_transformers"
    assert config.embeddings.model == "sentence-transformers/all-MiniLM-L6-v2"
    assert config.vector_db.collection == "groww_hdfc_mf_faq"
    assert config.response.max_sentences == 3
    assert config.response.citation_count == 1


def test_recursive_crawling_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AppConfig.model_validate({"scraping": {"follow_links": True}})


def test_invalid_chunk_overlap_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AppConfig.model_validate(
            {"chunking": {"target_tokens": 100, "overlap_tokens": 100}}
        )


def test_secret_is_redacted_in_model_representation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "synthetic-test-secret")
    settings = EnvironmentSettings.from_environment()

    assert "synthetic-test-secret" not in repr(settings)
    assert settings.groq_api_key is not None


def test_runtime_rejects_non_groq_llm_provider() -> None:
    with pytest.raises(ValidationError):
        EnvironmentSettings(llm_provider="openai")


def test_missing_configuration_has_clear_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "missing.yaml")

