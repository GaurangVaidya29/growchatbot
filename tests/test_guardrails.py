import pytest

from app.guardrails import ResponseCategory, SensitiveCategory, route_question


@pytest.mark.parametrize(
    ("question", "category"),
    [
        ("My PAN is ABCDE1234F", SensitiveCategory.PAN),
        ("My email is person@example.com", SensitiveCategory.EMAIL),
        ("My OTP is 482911", SensitiveCategory.OTP),
        ("My account number is 123456789012", SensitiveCategory.ACCOUNT_NUMBER),
    ],
)
def test_sensitive_data_is_blocked_before_retrieval(question, category):
    decision = route_question(question)
    assert decision.category == ResponseCategory.SENSITIVE_DATA
    assert category in decision.sensitive_categories
    assert decision.normalized_question == ""


@pytest.mark.parametrize(
    "question",
    [
        "Should I buy HDFC Large Cap?",
        "Which fund is best for my portfolio?",
        "Recommend an HDFC mutual fund.",
    ],
)
def test_advice_requests_are_deterministic(question):
    assert route_question(question).category == ResponseCategory.ADVICE_OR_OPINION


@pytest.mark.parametrize(
    "question",
    [
        "Compare returns of HDFC Large Cap and HDFC Mid Cap.",
        "What is the projected performance?",
    ],
)
def test_performance_requests_are_blocked(question):
    assert route_question(question).category == ResponseCategory.PERFORMANCE_REQUEST


def test_fact_question_continues_to_retrieval():
    assert (
        route_question("What is the expense ratio of HDFC Large Cap?").category
        == ResponseCategory.FACTUAL_CANDIDATE
    )


@pytest.mark.parametrize("question", ["", "   ", "a" * 1_001])
def test_invalid_question_is_rejected(question):
    with pytest.raises(ValueError):
        route_question(question)

