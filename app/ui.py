"""Streamlit interface for the facts-only mutual fund FAQ assistant.

This module deliberately contains no retrieval or safety policy. It maps the category
returned by :class:`QueryService` to a presentation state and renders the one citation
already selected by the trusted application layer.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from app.config import EnvironmentSettings
from app.guardrails import MAX_QUESTION_CHARACTERS, ResponseCategory
from app.llm import QueryService, UnavailableAnswerGenerator
from app.models import QueryResponse


PRODUCT_TITLE = "Groww Mutual Fund Facts Assistant"
WELCOME_MESSAGE = (
    "Ask a factual question about the supported HDFC mutual fund pages. "
    "Answers are grounded in the approved source index."
)
SAFETY_NOTE = "Facts-only. No investment advice."
EXAMPLE_QUESTIONS = (
    "What is the expense ratio of HDFC Large Cap Fund Direct Growth?",
    "What is the lock-in period of HDFC ELSS Tax Saver Fund?",
    "What are the exit load and minimum SIP for HDFC Mid Cap Fund?",
)


class UIState(StrEnum):
    IDLE = "IDLE"
    LOADING = "LOADING"
    ANSWER = "ANSWER"
    CLARIFICATION = "CLARIFICATION"
    REFUSAL = "REFUSAL"
    UNSUPPORTED = "UNSUPPORTED"
    SENSITIVE_WARNING = "SENSITIVE_WARNING"
    ERROR = "ERROR"


CATEGORY_STATES: dict[str, UIState] = {
    ResponseCategory.FACTUAL_SUPPORTED.value: UIState.ANSWER,
    ResponseCategory.CLARIFICATION_REQUIRED.value: UIState.CLARIFICATION,
    ResponseCategory.ADVICE_OR_OPINION.value: UIState.REFUSAL,
    ResponseCategory.PERFORMANCE_REQUEST.value: UIState.REFUSAL,
    ResponseCategory.OUT_OF_SCOPE.value: UIState.REFUSAL,
    ResponseCategory.UNSUPPORTED_BY_SOURCES.value: UIState.UNSUPPORTED,
    ResponseCategory.SENSITIVE_DATA.value: UIState.SENSITIVE_WARNING,
    ResponseCategory.SERVICE_ERROR.value: UIState.ERROR,
}


def state_for_category(category: str) -> UIState:
    """Map the service category to presentation only; do not reclassify content."""

    return CATEGORY_STATES.get(category, UIState.ERROR)


def validate_question_input(question: str) -> str | None:
    """Return a UI validation message, without applying any safety policy."""

    if not question.strip():
        return "Enter a question before submitting."
    if len(question) > MAX_QUESTION_CHARACTERS:
        return f"Keep the question within {MAX_QUESTION_CHARACTERS} characters."
    return None


def format_source_date(value: datetime) -> str:
    return value.strftime("%d %b %Y")


def create_ready_query_service() -> QueryService:
    """Create the service and enforce index compatibility before accepting queries."""

    service = QueryService()
    if isinstance(service.generator, UnavailableAnswerGenerator):
        raise RuntimeError(
            "Groq is not ready. Configure GROQ_API_KEY and install the Groq SDK."
        )
    service.retrieval.vector_store.validate_compatibility(
        embedding_model=service.config.embeddings.model,
        normalized_embeddings=service.config.embeddings.normalize,
    )
    return service


def _render_response(st: Any, response: QueryResponse, *, debug_enabled: bool) -> None:
    state = state_for_category(response.category)
    with st.container(border=True):
        if state == UIState.ANSWER:
            st.success(response.answer, icon="✅")
        elif state == UIState.CLARIFICATION:
            st.info(response.answer, icon="❓")
        elif state == UIState.REFUSAL:
            st.warning(response.answer, icon="🛡️")
        elif state == UIState.UNSUPPORTED:
            st.info(response.answer, icon="ℹ️")
        elif state == UIState.SENSITIVE_WARNING:
            st.warning(response.answer, icon="🔒")
        else:
            st.error(response.answer, icon="⚠️")

        st.link_button(
            f"Source: {response.citation.label}",
            str(response.citation.url),
            use_container_width=True,
        )
        st.caption(
            f"Last updated from sources: {format_source_date(response.source_updated_at)}"
        )

    if debug_enabled:
        with st.expander("Safe debug details", expanded=False):
            st.json(
                {
                    "response_category": response.category,
                    "source_id": response.citation.source_id,
                    "evidence_chunk_ids": response.evidence_chunk_ids,
                }
            )


def main() -> None:
    try:
        import streamlit as st
    except ImportError as exc:  # Gives a useful error when invoked with plain Python.
        raise RuntimeError(
            "Streamlit is not installed. Run: python -m pip install -r requirements.txt"
        ) from exc

    st.set_page_config(
        page_title=PRODUCT_TITLE,
        page_icon="📚",
        layout="centered",
        initial_sidebar_state="collapsed",
    )

    @st.cache_resource(show_spinner=False)
    def get_query_service() -> QueryService:
        return create_ready_query_service()

    def select_example(question: str) -> None:
        st.session_state.question_input = question

    st.title(PRODUCT_TITLE)
    st.write(WELCOME_MESSAGE)
    st.info(SAFETY_NOTE, icon="🛡️")

    st.subheader("Try an example")
    for index, example in enumerate(EXAMPLE_QUESTIONS, start=1):
        st.button(
            example,
            key=f"example_{index}",
            on_click=select_example,
            args=(example,),
            use_container_width=True,
        )

    if "busy" not in st.session_state:
        st.session_state.busy = False

    service: QueryService | None = None
    try:
        service = get_query_service()
    except Exception:
        setup_message = (
            "The assistant backend is not ready. Add a valid GROQ_API_KEY to .env and "
            "ensure the loading, chunking, and indexing stages have completed."
        )
        st.error(setup_message, icon="⚠️")

    question = st.text_input(
        "Your question",
        key="question_input",
        placeholder="Ask about an expense ratio, exit load, SIP, lock-in, risk, or benchmark",
        help=(
            f"Maximum {MAX_QUESTION_CHARACTERS} characters. Do not enter PAN, Aadhaar, "
            "account numbers, OTPs, email addresses, or phone numbers."
        ),
    )
    submitted = st.button(
        "Ask question",
        type="primary",
        disabled=st.session_state.busy or service is None,
        use_container_width=True,
    )

    if submitted and service is not None:
        validation_message = validate_question_input(question)
        if validation_message:
            st.warning(validation_message, icon="ℹ️")
            return

        st.session_state.busy = True
        try:
            with st.spinner("Checking approved sources…"):
                response = service.answer(question)
            environment = EnvironmentSettings.from_environment()
            _render_response(st, response, debug_enabled=environment.ui_debug)
        except Exception:
            st.error(
                "The assistant could not complete the request. Please try again later.",
                icon="⚠️",
            )
        finally:
            st.session_state.busy = False


if __name__ == "__main__":
    main()

