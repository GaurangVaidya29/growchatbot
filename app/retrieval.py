"""Privacy-first, scheme-aware retrieval from the active ChromaDB index."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.config import AppConfig, load_config
from app.embeddings import EmbeddingError, EmbeddingService
from app.guardrails import GuardrailDecision, ResponseCategory, route_question
from app.models import SourceDefinition
from app.scraper import load_source_registry
from app.vector_store import ChromaVectorStore, VectorSearchHit, VectorStoreError


SCHEME_ALIASES: dict[str, tuple[str, ...]] = {
    "hdfc_mutual_fund": (
        "hdfc mutual fund",
        "hdfc amc",
    ),
    "hdfc_large_cap_direct_growth": (
        "hdfc large cap fund direct growth",
        "hdfc large cap direct growth",
        "hdfc large cap fund",
        "hdfc large cap",
    ),
    "hdfc_flexi_cap_direct_growth": (
        "hdfc flexi cap direct plan growth",
        "hdfc flexi cap direct growth",
        "hdfc flexi cap fund",
        "hdfc flexi cap",
        "hdfc equity fund direct growth",
    ),
    "hdfc_elss_direct_growth": (
        "hdfc elss tax saver fund direct plan growth",
        "hdfc elss tax saver fund",
        "hdfc elss fund",
        "hdfc elss",
        "hdfc tax saver fund",
    ),
    "hdfc_mid_cap_direct_growth": (
        "hdfc mid cap fund direct growth",
        "hdfc mid cap direct growth",
        "hdfc mid cap fund",
        "hdfc mid cap",
    ),
}

FACT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("expense_ratio", re.compile(r"\b(?:expense ratio|ter)\b", re.I)),
    ("exit_load", re.compile(r"\b(?:exit load|redemption (?:fee|charge))\b", re.I)),
    ("minimum_sip", re.compile(r"\b(?:minimum|min)\s+sip\b|\bsip\s+(?:minimum|amount)\b", re.I)),
    ("lock_in", re.compile(r"\b(?:lock[ -]?in|tax saver lock)\b", re.I)),
    ("riskometer", re.compile(r"\b(?:riskometer|risk level|how risky|risk rating)\b", re.I)),
    ("benchmark", re.compile(r"\b(?:benchmark|benchmarked|index tracked)\b", re.I)),
    (
        "statement_process",
        re.compile(r"\b(?:capital gains? statement|download statement|account statement)\b", re.I),
    ),
)

SCHEME_REQUIRED_FACTS = {
    "expense_ratio",
    "exit_load",
    "minimum_sip",
    "lock_in",
    "riskometer",
    "benchmark",
}


@dataclass(frozen=True)
class SchemeResolution:
    scheme_id: str | None
    candidates: tuple[str, ...]
    clarification_required: bool


@dataclass(frozen=True)
class RetrievalResult:
    category: ResponseCategory
    scheme_id: str | None
    fact_type: str
    hits: tuple[VectorSearchHit, ...] = ()
    reason: str | None = None
    guardrail: GuardrailDecision | None = None


def resolve_scheme(question: str) -> SchemeResolution:
    normalized = " ".join(question.lower().split())
    matches: set[str] = set()
    for scheme_id, aliases in SCHEME_ALIASES.items():
        if any(re.search(rf"\b{re.escape(alias)}\b", normalized) for alias in aliases):
            matches.add(scheme_id)
    candidates = tuple(sorted(matches))
    return SchemeResolution(
        scheme_id=candidates[0] if len(candidates) == 1 else None,
        candidates=candidates,
        clarification_required=len(candidates) > 1,
    )


def resolve_fact_type(question: str) -> str:
    for fact_type, pattern in FACT_PATTERNS:
        if pattern.search(question):
            return fact_type
    return "general"


class RetrievalService:
    def __init__(
        self,
        config: AppConfig | None = None,
        *,
        embedding_service: EmbeddingService | Any | None = None,
        vector_store: ChromaVectorStore | Any | None = None,
        sources: tuple[SourceDefinition, ...] | None = None,
    ) -> None:
        self.config = config or load_config()
        self.embedding_service = embedding_service or EmbeddingService(self.config.embeddings)
        self.vector_store = vector_store or ChromaVectorStore(self.config.vector_db)
        self.sources = sources or load_source_registry()
        self.source_by_id = {
            source.source_id: source for source in self.sources if source.enabled
        }
        self.source_by_scheme = {
            source.scheme_id: source
            for source in self.sources
            if source.enabled and source.scheme_id
        }

    def retrieve(self, question: str) -> RetrievalResult:
        try:
            guardrail = route_question(question)
        except ValueError as exc:
            return RetrievalResult(
                category=ResponseCategory.CLARIFICATION_REQUIRED,
                scheme_id=None,
                fact_type="general",
                reason=str(exc),
            )

        if guardrail.category != ResponseCategory.FACTUAL_CANDIDATE:
            return RetrievalResult(
                category=guardrail.category,
                scheme_id=None,
                fact_type="general",
                reason=guardrail.reason,
                guardrail=guardrail,
            )

        scheme = resolve_scheme(guardrail.normalized_question)
        fact_type = resolve_fact_type(guardrail.normalized_question)
        if scheme.clarification_required:
            return RetrievalResult(
                category=ResponseCategory.CLARIFICATION_REQUIRED,
                scheme_id=None,
                fact_type=fact_type,
                reason="Multiple approved schemes were mentioned; specify one scheme.",
                guardrail=guardrail,
            )
        if fact_type in SCHEME_REQUIRED_FACTS and scheme.scheme_id is None:
            return RetrievalResult(
                category=ResponseCategory.CLARIFICATION_REQUIRED,
                scheme_id=None,
                fact_type=fact_type,
                reason="Specify one approved HDFC scheme for this fact.",
                guardrail=guardrail,
            )
        if fact_type == "statement_process":
            return RetrievalResult(
                category=ResponseCategory.UNSUPPORTED_BY_SOURCES,
                scheme_id=scheme.scheme_id,
                fact_type=fact_type,
                reason="Statement-download instructions are not present in the five-page corpus.",
                guardrail=guardrail,
            )

        filters = {"scheme_id": scheme.scheme_id} if scheme.scheme_id else None
        try:
            query_embedding = self.embedding_service.embed_query(
                guardrail.normalized_question
            )
            candidates = self.vector_store.search(
                query_embedding,
                top_k=max(self.config.retrieval.top_k * 2, self.config.retrieval.top_k),
                filters=filters,
                embedding_model=self.config.embeddings.model,
            )
        except (EmbeddingError, VectorStoreError, OSError, RuntimeError) as exc:
            return RetrievalResult(
                category=ResponseCategory.SERVICE_ERROR,
                scheme_id=scheme.scheme_id,
                fact_type=fact_type,
                reason=f"Retrieval service error: {type(exc).__name__}",
                guardrail=guardrail,
            )

        trusted_candidates = tuple(
            hit
            for hit in candidates
            if hit.score >= self.config.retrieval.score_threshold
            and hit.metadata.get("source_id") in self.source_by_id
            and (
                scheme.scheme_id is None
                or hit.metadata.get("scheme_id") == scheme.scheme_id
            )
        )
        if fact_type != "general":
            exact_fact_hits = tuple(
                hit
                for hit in trusted_candidates
                if hit.metadata.get("fact_type") == fact_type
            )
            trusted_candidates = exact_fact_hits

        ranked_hits = tuple(
            sorted(trusted_candidates, key=lambda hit: hit.score, reverse=True)[
                : self.config.retrieval.top_k
            ]
        )
        if not ranked_hits:
            return RetrievalResult(
                category=ResponseCategory.UNSUPPORTED_BY_SOURCES,
                scheme_id=scheme.scheme_id,
                fact_type=fact_type,
                reason="No trusted source chunk met the relevance and fact-type requirements.",
                guardrail=guardrail,
            )

        return RetrievalResult(
            category=ResponseCategory.FACTUAL_SUPPORTED,
            scheme_id=scheme.scheme_id,
            fact_type=fact_type,
            hits=ranked_hits,
            guardrail=guardrail,
        )

