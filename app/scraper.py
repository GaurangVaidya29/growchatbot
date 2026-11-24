"""Exact-allowlist page scraping and readable-content extraction."""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
import yaml
from bs4 import BeautifulSoup, Tag
from pydantic import TypeAdapter, ValidationError

from app.config import PROJECT_ROOT, ScrapingSettings
from app.models import DocumentSection, LoadedDocument, SourceDefinition


APPROVED_SOURCES: dict[str, str] = {
    "SRC-01": "https://groww.in/mutual-funds/amc/hdfc-mutual-funds",
    "SRC-02": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
    "SRC-03": "https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth",
    "SRC-04": "https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth",
    "SRC-05": "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
}

REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}
RETRYABLE_STATUS_CODES = {429, 502, 503, 504}
REMOVED_TAGS = (
    "script",
    "style",
    "noscript",
    "svg",
    "nav",
    "header",
    "footer",
    "aside",
    "form",
    "button",
)
CONTENT_TAGS = {"p", "li", "tr", "dt", "dd"}


class ScrapingError(RuntimeError):
    """Base error for a source that cannot be safely scraped."""


class SourceRegistryError(ScrapingError):
    """The source registry does not match the fixed project allowlist."""


class SourceFetchError(ScrapingError):
    """A page could not be fetched under the configured network policy."""


class ExtractionError(ScrapingError):
    """A fetched page did not contain enough readable content."""


@dataclass(frozen=True)
class ScrapeResult:
    source_id: str
    status: str
    raw_path: Path | None = None
    extracted_path: Path | None = None
    content_hash: str | None = None
    error: str | None = None


def canonicalize_url(value: str) -> str:
    """Return the exact-comparison form used by the allowlist."""

    parsed = urlsplit(value)
    if parsed.scheme.lower() != "https":
        raise SourceRegistryError("Only HTTPS source URLs are allowed")
    if parsed.username or parsed.password:
        raise SourceRegistryError("Source URLs cannot contain credentials")
    if parsed.query or parsed.fragment:
        raise SourceRegistryError("Source URLs cannot contain query strings or fragments")

    hostname = (parsed.hostname or "").lower()
    if hostname != "groww.in":
        raise SourceRegistryError("Only the approved groww.in pages are allowed")

    port = parsed.port
    if port not in (None, 443):
        raise SourceRegistryError("Non-default source URL ports are not allowed")

    path = parsed.path.rstrip("/") or "/"
    return urlunsplit(("https", hostname, path, "", ""))


def load_source_registry(path: Path | str | None = None) -> tuple[SourceDefinition, ...]:
    """Load and validate exactly the five user-approved source definitions."""

    registry_path = Path(path) if path is not None else PROJECT_ROOT / "config/sources.yaml"
    if not registry_path.is_absolute():
        registry_path = PROJECT_ROOT / registry_path
    if not registry_path.is_file():
        raise SourceRegistryError(f"Source registry not found: {registry_path}")

    with registry_path.open("r", encoding="utf-8") as handle:
        raw_registry = yaml.safe_load(handle) or {}
    if not isinstance(raw_registry, dict) or not isinstance(raw_registry.get("sources"), list):
        raise SourceRegistryError("Source registry must contain a 'sources' list")

    try:
        sources = tuple(TypeAdapter(list[SourceDefinition]).validate_python(raw_registry["sources"]))
    except ValidationError as exc:
        raise SourceRegistryError(f"Invalid source registry: {exc}") from exc

    expected_ids = set(APPROVED_SOURCES)
    actual_ids = {source.source_id for source in sources}
    if len(sources) != len(expected_ids) or actual_ids != expected_ids:
        raise SourceRegistryError("Source registry must contain exactly SRC-01 through SRC-05")

    seen_urls: set[str] = set()
    for source in sources:
        if not source.enabled:
            raise SourceRegistryError(f"Approved source is disabled: {source.source_id}")
        actual_url = canonicalize_url(str(source.url))
        expected_url = canonicalize_url(APPROVED_SOURCES[source.source_id])
        if actual_url != expected_url:
            raise SourceRegistryError(f"Unapproved URL for {source.source_id}: {actual_url}")
        if actual_url in seen_urls:
            raise SourceRegistryError(f"Duplicate source URL: {actual_url}")
        seen_urls.add(actual_url)

    return sources


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _extract_scheme_fact_sections(
    soup: BeautifulSoup,
    fallback_title: str,
) -> tuple[DocumentSection, ...]:
    """Extract high-value scheme facts that are rendered as label/value divs."""

    facts: list[DocumentSection] = []
    seen_headings: set[str] = set()

    def add(heading: str, text: str) -> None:
        clean_text = _clean_text(text)
        if clean_text and heading not in seen_headings:
            facts.append(DocumentSection(heading=heading, text=clean_text))
            seen_headings.add(heading)

    for node in soup.find_all(string=lambda value: value and value.strip().lower() == "expense ratio"):
        parent_text = _clean_text(node.parent.parent.get_text(" | ", strip=True))
        match = re.fullmatch(r"Expense ratio\s*\|\s*([0-9.]+%)", parent_text, re.IGNORECASE)
        if match:
            add("Expense ratio", f"Expense ratio: {match.group(1)}")
            break

    for node in soup.find_all(string=lambda value: value and value.strip().lower() == "exit load"):
        parent_text = _clean_text(node.parent.parent.get_text(" | ", strip=True))
        if re.search(r"\b(exit load of|nil\b)", parent_text, re.IGNORECASE):
            value = parent_text.split("|", maxsplit=1)[-1].strip()
            add("Exit load", f"Exit load: {value}")
            break

    for node in soup.find_all(string=lambda value: value and value.strip().lower() == "fund benchmark"):
        parent_text = _clean_text(node.parent.parent.get_text(" | ", strip=True))
        value = parent_text.split("|", maxsplit=1)[-1].strip()
        if value and value.lower() != "fund benchmark":
            add("Benchmark", f"Fund benchmark: {value}")
            break

    visible_text = _clean_text(soup.get_text(" ", strip=True))
    risk_match = re.search(r"\bis rated\s+(.+?)\s+risk\.", visible_text, re.IGNORECASE)
    if risk_match:
        add("Risk level", f"Risk level: {risk_match.group(1).strip()} risk")

    sip_match = re.search(
        r"Minimum SIP Investment is set to\s*([^.]*)\.",
        visible_text,
        re.IGNORECASE,
    )
    if sip_match:
        add("Minimum SIP", f"Minimum SIP investment: {sip_match.group(1).strip()}")

    lock_in_match = re.search(
        r"ELSS\s*[•·-]\s*(\d+)Y\s*Lock-in",
        visible_text,
        re.IGNORECASE,
    )
    if lock_in_match:
        add("Lock-in period", f"ELSS lock-in period: {lock_in_match.group(1)} years")

    return tuple(facts)


def extract_sections(html: bytes, fallback_title: str) -> tuple[DocumentSection, ...]:
    """Extract visible, structured text without treating links as crawl targets."""

    soup = BeautifulSoup(html.decode("utf-8", errors="replace"), "html.parser")
    fact_sections = _extract_scheme_fact_sections(soup, fallback_title)
    for element in soup.find_all(REMOVED_TAGS):
        element.decompose()

    root = soup.find("main") or soup.find("article") or soup.body
    if root is None:
        raise ExtractionError("Page does not contain a readable body")

    sections: list[DocumentSection] = list(fact_sections)
    current_heading = fallback_title
    current_lines: list[str] = []
    seen_blocks: set[tuple[str, str]] = set()

    def flush() -> None:
        nonlocal current_lines
        if current_lines:
            sections.append(
                DocumentSection(heading=current_heading, text="\n".join(current_lines))
            )
            current_lines = []

    for element in root.find_all(["h1", "h2", "h3", "h4", "h5", "h6", *CONTENT_TAGS]):
        if not isinstance(element, Tag):
            continue
        if element.name in CONTENT_TAGS and element.find_parent(CONTENT_TAGS):
            continue

        separator = " | " if element.name == "tr" else " "
        text = _clean_text(element.get_text(separator=separator, strip=True))
        if not text:
            continue

        if element.name and element.name.startswith("h"):
            flush()
            current_heading = text
            continue

        key = (current_heading, text)
        if key in seen_blocks:
            continue
        seen_blocks.add(key)
        current_lines.append(text)

    flush()

    if not sections:
        fallback_text = _clean_text(root.get_text(separator=" ", strip=True))
        if fallback_text:
            sections.append(DocumentSection(heading=fallback_title, text=fallback_text))

    return tuple(sections)


class ApprovedPageScraper:
    """Fetch and store only the five exact URLs in the project allowlist."""

    def __init__(
        self,
        settings: ScrapingSettings,
        *,
        client: httpx.Client | None = None,
        project_root: Path = PROJECT_ROOT,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings
        self.project_root = project_root.resolve()
        self._owns_client = client is None
        self.client = client or httpx.Client(
            timeout=settings.timeout_seconds,
            headers={"User-Agent": settings.user_agent},
            follow_redirects=False,
        )
        self.sleep = sleep
        self.allowed_urls = {
            canonicalize_url(value) for value in APPROVED_SOURCES.values()
        }

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> "ApprovedPageScraper":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _request_once(self, url: str) -> httpx.Response:
        current_url = canonicalize_url(url)
        for _ in range(5):
            if current_url not in self.allowed_urls:
                raise SourceFetchError(f"URL is outside the approved allowlist: {current_url}")

            response = self.client.get(current_url, follow_redirects=False)
            if response.status_code not in REDIRECT_STATUS_CODES:
                return response

            location = response.headers.get("location")
            if not location:
                raise SourceFetchError("Redirect response did not include a Location header")
            redirected_url = canonicalize_url(urljoin(current_url, location))
            if redirected_url not in self.allowed_urls:
                raise SourceFetchError("Redirect target is outside the approved allowlist")
            current_url = redirected_url

        raise SourceFetchError("Too many redirects")

    def fetch(self, source: SourceDefinition) -> bytes:
        approved_url = canonicalize_url(str(source.url))
        if approved_url != canonicalize_url(APPROVED_SOURCES.get(source.source_id, "")):
            raise SourceFetchError(f"Source is not approved: {source.source_id}")

        response: httpx.Response | None = None
        for attempt in range(self.settings.max_retries + 1):
            try:
                response = self._request_once(approved_url)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt >= self.settings.max_retries:
                    raise SourceFetchError(f"Network error for {source.source_id}: {exc}") from exc
                self.sleep(min(2**attempt, 5))
                continue

            if response.status_code in RETRYABLE_STATUS_CODES and attempt < self.settings.max_retries:
                self.sleep(min(2**attempt, 5))
                continue
            break

        if response is None:
            raise SourceFetchError(f"No response received for {source.source_id}")
        if response.status_code >= 400:
            raise SourceFetchError(
                f"HTTP {response.status_code} while fetching {source.source_id}"
            )

        content_type = response.headers.get("content-type", "").lower()
        if "text/html" not in content_type:
            raise SourceFetchError(
                f"Expected HTML for {source.source_id}, received {content_type or 'unknown'}"
            )

        declared_size = response.headers.get("content-length")
        if declared_size and int(declared_size) > self.settings.max_response_bytes:
            raise SourceFetchError(f"Response is too large for {source.source_id}")
        content = response.content
        if len(content) > self.settings.max_response_bytes:
            raise SourceFetchError(f"Response is too large for {source.source_id}")
        return content

    def _safe_artifact_path(self, directory: str, filename: str) -> Path:
        path = (self.project_root / "data" / directory / filename).resolve()
        if self.project_root not in path.parents:
            raise ScrapingError("Artifact path escapes the project root")
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        temporary_path = path.with_suffix(path.suffix + ".tmp")
        temporary_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        temporary_path.replace(path)

    @staticmethod
    def _write_bytes(path: Path, payload: bytes) -> None:
        temporary_path = path.with_suffix(path.suffix + ".tmp")
        temporary_path.write_bytes(payload)
        temporary_path.replace(path)

    def scrape_source(self, source: SourceDefinition) -> ScrapeResult:
        try:
            html = self.fetch(source)
            content_hash = hashlib.sha256(html).hexdigest()
            retrieved_at = datetime.now(UTC)
            sections = extract_sections(html, source.title)
            extracted_characters = sum(len(section.text) for section in sections)
            if extracted_characters < self.settings.min_extracted_characters:
                raise ExtractionError(
                    f"Extracted content for {source.source_id} is below the minimum length"
                )

            document = LoadedDocument(
                source_id=source.source_id,
                title=source.title,
                scheme_id=source.scheme_id,
                url=source.url,
                retrieved_at=retrieved_at,
                content_hash=content_hash,
                sections=list(sections),
            )

            raw_path = self._safe_artifact_path("raw", f"{source.source_id}.html")
            raw_manifest_path = self._safe_artifact_path(
                "raw", f"{source.source_id}.manifest.json"
            )
            extracted_path = self._safe_artifact_path(
                "extracted", f"{source.source_id}.json"
            )

            self._write_bytes(raw_path, html)
            self._write_json(
                raw_manifest_path,
                {
                    "source_id": source.source_id,
                    "url": canonicalize_url(str(source.url)),
                    "retrieved_at": retrieved_at.isoformat().replace("+00:00", "Z"),
                    "content_hash": content_hash,
                    "byte_count": len(html),
                    "status": "SUCCESS",
                },
            )
            self._write_json(extracted_path, document.model_dump(mode="json"))
            return ScrapeResult(
                source_id=source.source_id,
                status="SUCCESS",
                raw_path=raw_path,
                extracted_path=extracted_path,
                content_hash=content_hash,
            )
        except (ScrapingError, ValidationError, OSError, ValueError) as exc:
            return ScrapeResult(
                source_id=source.source_id,
                status="FAILED",
                error=str(exc),
            )

    def scrape_all(self, sources: Iterable[SourceDefinition]) -> tuple[ScrapeResult, ...]:
        results = tuple(self.scrape_source(source) for source in sources)
        manifest_path = self._safe_artifact_path("raw", "scrape_manifest.json")
        self._write_json(
            manifest_path,
            {
                "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "expected_sources": sorted(APPROVED_SOURCES),
                "results": [
                    {
                        "source_id": result.source_id,
                        "status": result.status,
                        "content_hash": result.content_hash,
                        "error": result.error,
                    }
                    for result in results
                ],
            },
        )
        return results

