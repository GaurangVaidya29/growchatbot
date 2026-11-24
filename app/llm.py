"""Grounded answer generation and response validation.

The LLM is allowed to select only evidence IDs and source IDs. URLs are resolved
from the local trusted-source registry after the generated response is validated.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import ValidationError

from app.config import AppConfig, EnvironmentSettings, load_config
from app.document_loader import load_documents
from app.guardrails import (
    ResponseCategory,
    contains_prohibited_advice,
    contains_prohibited_performance,
    detect_sensitive_categories,
)
from app.models import Citation, GeneratedAnswer, QueryResponse, SourceDefinition
from app.retrieval import RetrievalResult, RetrievalService
from app.scraper import load_source_registry


class LLMError(RuntimeError):
    """The configured answer generator was unavailable or returned invalid data."""


class AnswerGenerator(Protocol):
    def generate(self, question: str, result: RetrievalResult) -> GeneratedAnswer:
        """Generate a structured answer using only ``result.hits``."""


class UnavailableAnswerGenerator:
    """Defer an LLM setup error to the safe response boundary."""

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def generate(self, question: str, result: RetrievalResult) -> GeneratedAnswer:
        del question, result
        raise LLMError(self.reason)


class GroqAnswerGenerator:
    """Groq JSON generation with one strict retry and no URL authority."""

    def __init__(self, settings: EnvironmentSettings) -> None:
        if settings.groq_api_key is None or not settings.groq_api_key.get_secret_value():
            raise LLMError("GROQ_API_KEY is not configured")
        try:
            from groq import Groq
        except ImportError as exc:
            raise LLMError("groq is not installed") from exc
        self.model = settings.llm_model
        self.client = Groq(api_key=settings.groq_api_key.get_secret_value())

    @staticmethod
    def _prompt(question: str, result: RetrievalResult, *, retry: bool) -> str:
        evidence = [
            {
                "chunk_id": hit.chunk_id,
                "source_id": hit.metadata.get("source_id"),
                "text": hit.text,
            }
            for hit in result.hits
        ]
        retry_instruction = (
            "Your previous response was invalid. Return only the required JSON object. "
            if retry
            else ""
        )
        return (
            f"{retry_instruction}Answer only from the supplied evidence. "
            "Do not add advice, performance comparisons, sensitive data, or URLs. "
            "Use no more than three sentences. Select one supplied source_id and one or "
            "more supplied chunk_id values. Return JSON with exactly these keys: "
            "category, answer_text, selected_source_id, evidence_chunk_ids. "
            "category must be FACTUAL_SUPPORTED.\n"
            f"Question: {question}\nCanonical scheme: {result.scheme_id}\n"
            f"Fact type: {result.fact_type}\nEvidence: "
            f"{json.dumps(evidence, ensure_ascii=False)}"
        )

    def generate(self, question: str, result: RetrievalResult) -> GeneratedAnswer:
        last_error: Exception | None = None
        for retry in (False, True):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    temperature=0,
                    response_format={"type": "json_object"},
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a facts-only mutual fund FAQ answerer.",
                        },
                        {
                            "role": "user",
                            "content": self._prompt(question, result, retry=retry),
                        },
                    ],
                )
                content = response.choices[0].message.content
                if not content:
                    raise LLMError("Groq returned an empty response")
                return GeneratedAnswer.model_validate_json(content)
            except (ValidationError, ValueError, TypeError, KeyError, IndexError, LLMError) as exc:
                last_error = exc
            except Exception as exc:  # Provider SDK exceptions vary by version.
                last_error = exc
        raise LLMError(f"Groq generation failed: {type(last_error).__name__}")


TEMPLATES: dict[ResponseCategory, str] = {
    ResponseCategory.ADVICE_OR_OPINION: (
        "I can provide verified fund facts, but I cannot recommend whether to buy, sell, "
        "hold, or switch an investment."
    ),
    ResponseCategory.PERFORMANCE_REQUEST: (
        "I cannot calculate, compare, rank, or project investment performance. "
        "I can help with verified scheme facts instead."
    ),
    ResponseCategory.OUT_OF_SCOPE: (
        "That question is outside this facts-only HDFC mutual fund FAQ."
    ),
    ResponseCategory.SENSITIVE_DATA: (
        "Please do not share personal or financial identifiers here. "
        "Remove the sensitive information and ask a general fund question."
    ),
    ResponseCategory.UNSUPPORTED_BY_SOURCES: (
        "I could not verify that fact from the approved source pages, so I will not guess."
    ),
    ResponseCategory.CLARIFICATION_REQUIRED: (
        "Please specify one scheme: HDFC Large Cap, Flexi Cap, ELSS Tax Saver, or Mid Cap."
    ),
    ResponseCategory.SERVICE_ERROR: (
        "The verified source index is temporarily unavailable. Please try again later."
    ),
}


def _sentence_count(text: str) -> int:
    return len([part for part in re.split(r"(?<=[.!?])(?:\s+|$)", text.strip()) if part])


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"(?<!\w)\d+(?:[.,]\d+)*(?:%|\s*years?)?", text, re.I))


class QueryService:
    """Run retrieval, validate grounded output, and attach one trusted citation."""

    def __init__(
        self,
        config: AppConfig | None = None,
        *,
        retrieval_service: RetrievalService | Any | None = None,
        generator: AnswerGenerator | None = None,
        sources: tuple[SourceDefinition, ...] | None = None,
        source_dates: dict[str, datetime] | None = None,
        environment: EnvironmentSettings | None = None,
    ) -> None:
        self.config = config or load_config()
        self.sources = sources or load_source_registry()
        self.source_by_id = {
            source.source_id: source for source in self.sources if source.enabled
        }
        self.retrieval = retrieval_service or RetrievalService(
            self.config, sources=self.sources
        )
        if source_dates is None:
            loaded = load_documents()
            source_dates = {
                document.source_id: document.retrieved_at for document in loaded.documents
            }
        self.source_dates = source_dates
        if generator is not None:
            self.generator = generator
        else:
            runtime = environment or EnvironmentSettings.from_environment()
            try:
                self.generator = GroqAnswerGenerator(runtime)
            except LLMError as exc:
                self.generator = UnavailableAnswerGenerator(str(exc))

    def _citation_source(self, result: RetrievalResult) -> SourceDefinition:
        if result.hits:
            source_id = str(result.hits[0].metadata.get("source_id", ""))
            if source_id in self.source_by_id:
                return self.source_by_id[source_id]
        if result.scheme_id:
            for source in self.source_by_id.values():
                if source.scheme_id == result.scheme_id:
                    return source
        return self.source_by_id.get("SRC-01") or next(iter(self.source_by_id.values()))

    def _response(
        self,
        category: ResponseCategory,
        answer: str,
        source: SourceDefinition,
        evidence_ids: list[str] | None = None,
    ) -> QueryResponse:
        source_date = self.source_dates.get(source.source_id, datetime.now(UTC))
        return QueryResponse(
            category=category.value,
            answer=answer,
            citation=Citation(
                source_id=source.source_id,
                label=source.title,
                url=source.url,
            ),
            source_updated_at=source_date,
            evidence_chunk_ids=evidence_ids or [],
        )

    def _validate_generated(
        self, generated: GeneratedAnswer, result: RetrievalResult
    ) -> SourceDefinition:
        hit_by_id = {hit.chunk_id: hit for hit in result.hits}
        evidence_ids = set(generated.evidence_chunk_ids)
        if generated.category != ResponseCategory.FACTUAL_SUPPORTED.value:
            raise LLMError("Generated category is not factual-supported")
        if not evidence_ids or not evidence_ids.issubset(hit_by_id):
            raise LLMError("Generated evidence IDs were not retrieved")
        evidence_sources = {
            str(hit_by_id[chunk_id].metadata.get("source_id", ""))
            for chunk_id in evidence_ids
        }
        if generated.selected_source_id not in evidence_sources:
            raise LLMError("Selected source does not belong to selected evidence")
        source = self.source_by_id.get(generated.selected_source_id)
        if source is None:
            raise LLMError("Selected source is not approved")
        answer = generated.answer_text.strip()
        if not answer or _sentence_count(answer) > self.config.response.max_sentences:
            raise LLMError("Generated answer is empty or too long")
        if re.search(r"https?://|www\.", answer, re.I):
            raise LLMError("Generated answer contains a URL")
        if detect_sensitive_categories(answer):
            raise LLMError("Generated answer contains sensitive data")
        if contains_prohibited_advice(answer) or contains_prohibited_performance(answer):
            raise LLMError("Generated answer contains prohibited content")
        evidence_text = "\n".join(hit_by_id[item].text for item in evidence_ids)
        if not _numbers(answer).issubset(_numbers(evidence_text)):
            raise LLMError("Generated answer contains an unsupported numeric claim")
        return source

    def answer(self, question: str) -> QueryResponse:
        result = self.retrieval.retrieve(question)
        if result.category != ResponseCategory.FACTUAL_SUPPORTED:
            category = result.category
            template = TEMPLATES.get(category, TEMPLATES[ResponseCategory.SERVICE_ERROR])
            return self._response(
                category if category in TEMPLATES else ResponseCategory.SERVICE_ERROR,
                template,
                self._citation_source(result),
            )

        fallback_source = self._citation_source(result)
        try:
            safe_question = (
                result.guardrail.normalized_question if result.guardrail else question
            )
            generated = self.generator.generate(safe_question, result)
            source = self._validate_generated(generated, result)
            return self._response(
                ResponseCategory.FACTUAL_SUPPORTED,
                generated.answer_text.strip(),
                source,
                generated.evidence_chunk_ids,
            )
        except (LLMError, ValidationError, ValueError, TypeError):
            return self._response(
                ResponseCategory.SERVICE_ERROR,
                TEMPLATES[ResponseCategory.SERVICE_ERROR],
                fallback_source,
            )

