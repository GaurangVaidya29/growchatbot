"""Deterministic privacy, advice, performance, and scope guardrails."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


MAX_QUESTION_CHARACTERS = 1_000


class ResponseCategory(StrEnum):
    FACTUAL_CANDIDATE = "FACTUAL_CANDIDATE"
    FACTUAL_SUPPORTED = "FACTUAL_SUPPORTED"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    ADVICE_OR_OPINION = "ADVICE_OR_OPINION"
    PERFORMANCE_REQUEST = "PERFORMANCE_REQUEST"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    SENSITIVE_DATA = "SENSITIVE_DATA"
    UNSUPPORTED_BY_SOURCES = "UNSUPPORTED_BY_SOURCES"
    SERVICE_ERROR = "SERVICE_ERROR"


class SensitiveCategory(StrEnum):
    PAN = "PAN"
    AADHAAR = "AADHAAR"
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    OTP = "OTP"
    ACCOUNT_NUMBER = "ACCOUNT_NUMBER"


@dataclass(frozen=True)
class GuardrailDecision:
    category: ResponseCategory
    normalized_question: str
    sensitive_categories: tuple[SensitiveCategory, ...] = ()
    reason: str | None = None


PAN_PATTERN = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", re.IGNORECASE)
AADHAAR_PATTERN = re.compile(r"(?<!\d)(?:\d[ -]?){11}\d(?!\d)")
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?91[ -]?)?[6-9]\d{9}(?!\d)")
OTP_PATTERN = re.compile(r"\b(?:otp|one[ -]?time password|passcode)\b.{0,30}\b\d{4,8}\b", re.I)
ACCOUNT_PATTERN = re.compile(
    r"\b(?:account|a/c|folio)\s*(?:number|no\.?|#)?\s*(?:is\s*)?[:=-]?\s*\d{8,18}\b",
    re.I,
)

ADVICE_PATTERNS = (
    re.compile(r"\bshould\s+i\b", re.I),
    re.compile(r"\b(?:buy|sell|hold|switch)\b", re.I),
    re.compile(r"\b(?:best|recommend|recommendation|suitable|suitability)\b", re.I),
    re.compile(r"\bportfolio\b", re.I),
    re.compile(r"\bhow\s+much\s+should\s+i\s+invest\b", re.I),
    re.compile(r"\bwhere\s+should\s+i\s+invest\b", re.I),
)
PERFORMANCE_PATTERNS = (
    re.compile(r"\b(?:returns?|cagr|performance|alpha)\b", re.I),
    re.compile(r"\b(?:compare|comparison|rank|ranking)\b.{0,40}\b(?:fund|scheme|return)", re.I),
    re.compile(r"\b(?:project|projection|forecast|future value)\b", re.I),
)
OUT_OF_SCOPE_PATTERNS = (
    re.compile(r"\b(?:weather|recipe|movie|sports?|cricket)\b", re.I),
    re.compile(r"\b(?:stock|share|crypto|bitcoin|loan|insurance)\b", re.I),
)


def normalize_question(question: str) -> str:
    normalized = " ".join(question.split())
    if not normalized:
        raise ValueError("Question cannot be empty")
    if len(normalized) > MAX_QUESTION_CHARACTERS:
        raise ValueError(
            f"Question exceeds the {MAX_QUESTION_CHARACTERS}-character limit"
        )
    return normalized


def detect_sensitive_categories(question: str) -> tuple[SensitiveCategory, ...]:
    """Return categories only; never return or persist the matched values."""

    patterns = (
        (SensitiveCategory.PAN, PAN_PATTERN),
        (SensitiveCategory.AADHAAR, AADHAAR_PATTERN),
        (SensitiveCategory.EMAIL, EMAIL_PATTERN),
        (SensitiveCategory.PHONE, PHONE_PATTERN),
        (SensitiveCategory.OTP, OTP_PATTERN),
        (SensitiveCategory.ACCOUNT_NUMBER, ACCOUNT_PATTERN),
    )
    return tuple(category for category, pattern in patterns if pattern.search(question))


def route_question(question: str) -> GuardrailDecision:
    normalized = normalize_question(question)
    sensitive_categories = detect_sensitive_categories(normalized)
    if sensitive_categories:
        return GuardrailDecision(
            category=ResponseCategory.SENSITIVE_DATA,
            normalized_question="",
            sensitive_categories=sensitive_categories,
            reason="Sensitive data detected before retrieval",
        )
    if any(pattern.search(normalized) for pattern in ADVICE_PATTERNS):
        return GuardrailDecision(
            category=ResponseCategory.ADVICE_OR_OPINION,
            normalized_question=normalized,
            reason="Advice or portfolio action requested",
        )
    if any(pattern.search(normalized) for pattern in PERFORMANCE_PATTERNS):
        return GuardrailDecision(
            category=ResponseCategory.PERFORMANCE_REQUEST,
            normalized_question=normalized,
            reason="Performance calculation, comparison, or projection requested",
        )
    if any(pattern.search(normalized) for pattern in OUT_OF_SCOPE_PATTERNS):
        return GuardrailDecision(
            category=ResponseCategory.OUT_OF_SCOPE,
            normalized_question=normalized,
            reason="Question is outside mutual fund FAQ scope",
        )
    return GuardrailDecision(
        category=ResponseCategory.FACTUAL_CANDIDATE,
        normalized_question=normalized,
    )


def contains_prohibited_advice(text: str) -> bool:
    return any(pattern.search(text) for pattern in ADVICE_PATTERNS)


def contains_prohibited_performance(text: str) -> bool:
    return any(pattern.search(text) for pattern in PERFORMANCE_PATTERNS)

