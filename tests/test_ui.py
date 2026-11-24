from datetime import UTC, datetime

import pytest

from app.guardrails import ResponseCategory
from app.ui import (
    EXAMPLE_QUESTIONS,
    UIState,
    format_source_date,
    state_for_category,
    validate_question_input,
)


@pytest.mark.parametrize(
    ("category", "expected"),
    [
        (ResponseCategory.FACTUAL_SUPPORTED.value, UIState.ANSWER),
        (ResponseCategory.CLARIFICATION_REQUIRED.value, UIState.CLARIFICATION),
        (ResponseCategory.ADVICE_OR_OPINION.value, UIState.REFUSAL),
        (ResponseCategory.PERFORMANCE_REQUEST.value, UIState.REFUSAL),
        (ResponseCategory.OUT_OF_SCOPE.value, UIState.REFUSAL),
        (ResponseCategory.UNSUPPORTED_BY_SOURCES.value, UIState.UNSUPPORTED),
        (ResponseCategory.SENSITIVE_DATA.value, UIState.SENSITIVE_WARNING),
        (ResponseCategory.SERVICE_ERROR.value, UIState.ERROR),
        ("UNKNOWN", UIState.ERROR),
    ],
)
def test_query_categories_map_to_ui_states(category, expected):
    assert state_for_category(category) == expected


def test_ui_input_validation_handles_empty_and_long_questions():
    assert validate_question_input("   ") == "Enter a question before submitting."
    assert "1000" in validate_question_input("x" * 1_001)
    assert validate_question_input("What is the expense ratio?") is None


def test_ui_has_exactly_three_examples():
    assert len(EXAMPLE_QUESTIONS) == 3


def test_source_date_is_human_readable():
    value = datetime(2026, 11, 24, 8, 30, tzinfo=UTC)
    assert format_source_date(value) == "24 Nov 2026"
