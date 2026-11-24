from datetime import UTC, datetime

from app.config import EnvironmentSettings, load_config
from app.guardrails import ResponseCategory
from app.llm import QueryService
from app.models import GeneratedAnswer
from app.retrieval import RetrievalResult, RetrievalService, resolve_fact_type, resolve_scheme
from app.scraper import load_source_registry
from app.vector_store import VectorSearchHit


class FakeEmbeddingService:
    def __init__(self):
        self.questions = []

    def embed_query(self, question):
        self.questions.append(question)
        return (1.0, 0.0, 0.0)


class FakeVectorStore:
    def __init__(self, hits=()):
        self.hits = tuple(hits)
        self.calls = []

    def search(self, embedding, *, top_k, filters, embedding_model):
        self.calls.append((embedding, top_k, filters, embedding_model))
        return self.hits


class FakeRetriever:
    def __init__(self, result):
        self.result = result

    def retrieve(self, question):
        return self.result


class InvalidUrlGenerator:
    def generate(self, question, result):
        return GeneratedAnswer(
            category="FACTUAL_SUPPORTED",
            answer_text="Expense ratio: 0.99%. See https://untrusted.example.",
            selected_source_id="SRC-02",
            evidence_chunk_ids=["chunk-1"],
        )


def hit(*, score=0.91, fact_type="expense_ratio", source_id="SRC-02"):
    return VectorSearchHit(
        chunk_id="chunk-1",
        text="Scheme: HDFC Large Cap Fund Direct Growth\nExpense ratio: 0.99%",
        score=score,
        metadata={
            "source_id": source_id,
            "scheme_id": "hdfc_large_cap_direct_growth",
            "fact_type": fact_type,
        },
    )


def build_retriever(hits=()):
    embeddings = FakeEmbeddingService()
    store = FakeVectorStore(hits)
    service = RetrievalService(
        load_config(),
        embedding_service=embeddings,
        vector_store=store,
        sources=load_source_registry(),
    )
    return service, embeddings, store


def test_scheme_and_fact_resolution():
    scheme = resolve_scheme("Expense ratio for HDFC Large Cap Fund Direct Growth")
    assert scheme.scheme_id == "hdfc_large_cap_direct_growth"
    assert resolve_fact_type("What is its expense ratio?") == "expense_ratio"
    assert resolve_fact_type("Tell me about the scheme") == "general"


def test_supported_fact_is_filtered_by_scheme_and_fact_type():
    service, embeddings, store = build_retriever((hit(),))
    result = service.retrieve("What is the expense ratio of HDFC Large Cap?")
    assert result.category == ResponseCategory.FACTUAL_SUPPORTED
    assert result.hits[0].chunk_id == "chunk-1"
    assert embeddings.questions
    assert store.calls[0][2] == {"scheme_id": "hdfc_large_cap_direct_growth"}


def test_wrong_fact_or_low_score_is_not_answered():
    wrong_fact, _, _ = build_retriever((hit(fact_type="benchmark"),))
    low_score, _, _ = build_retriever((hit(score=0.49),))
    assert (
        wrong_fact.retrieve("Expense ratio for HDFC Large Cap").category
        == ResponseCategory.UNSUPPORTED_BY_SOURCES
    )
    assert (
        low_score.retrieve("Expense ratio for HDFC Large Cap").category
        == ResponseCategory.UNSUPPORTED_BY_SOURCES
    )


def test_unknown_source_is_never_trusted():
    service, _, _ = build_retriever((hit(source_id="SRC-999"),))
    assert (
        service.retrieve("Expense ratio for HDFC Large Cap").category
        == ResponseCategory.UNSUPPORTED_BY_SOURCES
    )


def test_sensitive_and_advice_queries_do_not_reach_vector_search():
    service, embeddings, store = build_retriever((hit(),))
    sensitive = service.retrieve("My PAN is ABCDE1234F")
    advice = service.retrieve("Should I buy HDFC Large Cap?")
    assert sensitive.category == ResponseCategory.SENSITIVE_DATA
    assert advice.category == ResponseCategory.ADVICE_OR_OPINION
    assert not embeddings.questions
    assert not store.calls


def test_missing_or_multiple_scheme_requires_clarification():
    service, embeddings, _ = build_retriever((hit(),))
    missing = service.retrieve("What is the expense ratio?")
    multiple = service.retrieve("Benchmark of HDFC Large Cap and HDFC Mid Cap")
    assert missing.category == ResponseCategory.CLARIFICATION_REQUIRED
    assert multiple.category == ResponseCategory.CLARIFICATION_REQUIRED
    assert not embeddings.questions


def test_missing_groq_key_fails_closed_for_supported_fact():
    result = RetrievalResult(
        category=ResponseCategory.FACTUAL_SUPPORTED,
        scheme_id="hdfc_large_cap_direct_growth",
        fact_type="expense_ratio",
        hits=(hit(),),
    )
    service = QueryService(
        retrieval_service=FakeRetriever(result),
        sources=load_source_registry(),
        source_dates={"SRC-02": datetime(2026, 11, 24, tzinfo=UTC)},
        environment=EnvironmentSettings(groq_api_key=None),
    )
    response = service.answer("Expense ratio for HDFC Large Cap")
    assert response.category == ResponseCategory.SERVICE_ERROR.value
    assert response.evidence_chunk_ids == []


def test_query_service_rejects_generated_url_and_uses_safe_fallback():
    result = RetrievalResult(
        category=ResponseCategory.FACTUAL_SUPPORTED,
        scheme_id="hdfc_large_cap_direct_growth",
        fact_type="expense_ratio",
        hits=(hit(),),
    )
    service = QueryService(
        retrieval_service=FakeRetriever(result),
        generator=InvalidUrlGenerator(),
        sources=load_source_registry(),
        source_dates={"SRC-02": datetime(2026, 11, 24, tzinfo=UTC)},
    )
    response = service.answer("Expense ratio for HDFC Large Cap")
    assert response.category == ResponseCategory.SERVICE_ERROR.value
    assert str(response.citation.url).startswith("https://groww.in/")
    assert "untrusted" not in response.answer


def test_deterministic_refusal_has_exactly_one_approved_citation():
    result = RetrievalResult(
        category=ResponseCategory.ADVICE_OR_OPINION,
        scheme_id=None,
        fact_type="general",
    )
    service = QueryService(
        retrieval_service=FakeRetriever(result),
        sources=load_source_registry(),
        source_dates={"SRC-01": datetime(2026, 11, 24, tzinfo=UTC)},
    )
    response = service.answer("Should I buy this fund?")
    assert response.category == ResponseCategory.ADVICE_OR_OPINION.value
    assert response.citation.source_id == "SRC-01"
    assert response.evidence_chunk_ids == []

