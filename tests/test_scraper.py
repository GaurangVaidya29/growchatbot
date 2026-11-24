"""Tests for the exact-five-page scraping boundary."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.config import ScrapingSettings
from app.scraper import (
    APPROVED_SOURCES,
    ApprovedPageScraper,
    SourceFetchError,
    SourceRegistryError,
    extract_sections,
    load_source_registry,
)


def _html(title: str) -> bytes:
    repeated_text = " ".join(["Official mutual fund fact"] * 20)
    return f"""
    <html>
      <head><title>{title}</title><style>.hidden {{ display:none }}</style></head>
      <body>
        <nav><a href="/internal-navigation">Internal navigation</a></nav>
        <main>
          <h1>{title}</h1>
          <h2>Fund details</h2>
          <p>Expense ratio: 1.00%</p>
          <p>{repeated_text}</p>
          <a href="/mutual-funds/should-never-be-fetched">Read another page</a>
        </main>
        <script>fetch('/private-api')</script>
      </body>
    </html>
    """.encode()


def test_registry_contains_exactly_the_five_approved_sources() -> None:
    sources = load_source_registry()

    assert {source.source_id for source in sources} == set(APPROVED_SOURCES)
    assert {str(source.url).rstrip("/") for source in sources} == set(
        APPROVED_SOURCES.values()
    )


def test_scraper_requests_only_the_five_registry_urls(tmp_path: Path) -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url).rstrip("/"))
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=_html(str(request.url)),
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    settings = ScrapingSettings(max_retries=0, min_extracted_characters=20)
    scraper = ApprovedPageScraper(settings, client=client, project_root=tmp_path)

    results = scraper.scrape_all(load_source_registry())

    assert all(result.status == "SUCCESS" for result in results)
    assert requested_urls == list(APPROVED_SOURCES.values())
    assert len(list((tmp_path / "data/raw").glob("SRC-*.html"))) == 5
    assert len(list((tmp_path / "data/extracted").glob("SRC-*.json"))) == 5
    assert not any("should-never-be-fetched" in url for url in requested_urls)
    assert not any("private-api" in url for url in requested_urls)


def test_redirect_outside_allowlist_is_rejected(tmp_path: Path) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://example.com/other"})

    scraper = ApprovedPageScraper(
        ScrapingSettings(max_retries=0),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        project_root=tmp_path,
    )
    source = load_source_registry()[0]

    with pytest.raises((SourceFetchError, SourceRegistryError)):
        scraper.fetch(source)


def test_non_html_response_is_rejected(tmp_path: Path) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"pdf")

    scraper = ApprovedPageScraper(
        ScrapingSettings(max_retries=0),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        project_root=tmp_path,
    )

    with pytest.raises(SourceFetchError):
        scraper.fetch(load_source_registry()[0])


def test_extraction_removes_navigation_and_script_content() -> None:
    sections = extract_sections(_html("Test Fund"), "Fallback")
    extracted_text = " ".join(section.text for section in sections)

    assert "Expense ratio" in extracted_text
    assert "Internal navigation" not in extracted_text
    assert "private-api" not in extracted_text

