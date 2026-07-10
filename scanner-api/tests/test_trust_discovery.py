from __future__ import annotations

import pytest

from app.review import run_review
from app.trust_discovery import enrich_scan_with_trust_pages, is_trust_candidate


class FakeResponse:
    def __init__(self, url: str, status_code: int = 200, text: str = "", content_type: str = "text/html"):
        self.url = url
        self.status_code = status_code
        self.text = text
        self.headers = {"content-type": content_type}


def base_scan(pages=None):
    pages = list(pages or [])
    return {
        "success": True,
        "scanner_version": "python_scanner_v2_contract_parity",
        "version": "python_scanner_v2_contract_parity",
        "website_url": "https://example.com/pret-immobilier",
        "normalized_url": "https://example.com/pret-immobilier",
        "scan_mode": "advanced",
        "pages": pages,
        "crawled_pages": pages,
        "pages_crawled": len(pages),
        "pages_found": 750,
        "raw_findings": [],
        "grouped_findings": [],
        "findings": [],
        "recommendations": [],
        "verified_failed_pages": [],
        "suspicious_url_artifacts": [],
        "scan_coverage": {
            "pages_found": 750,
            "pages_crawled": len(pages),
            "sampled_pages_sent_to_ai": len(pages),
        },
        "technical_audit_summary": {},
    }


def page(path: str):
    return {
        "url": f"https://example.com{path}",
        "final_url": f"https://example.com{path}",
        "path": path,
        "status_code": 200,
        "title": "Page",
        "meta_description": "Description",
        "h1": "Page",
        "h1_count": 1,
        "canonical": f"https://example.com{path}",
        "canonical_url": f"https://example.com{path}",
        "image_missing_alt_count": 0,
        "missing_alt_image_count": 0,
        "indexable": True,
        "page_template_family": "legal_info" if is_trust_candidate(path) else "loan_program",
        "estimated_page_intent": "trust_or_legal" if is_trust_candidate(path) else "money_or_conversion",
    }


@pytest.mark.asyncio
async def test_existing_trust_page_is_preserved_and_reported(monkeypatch):
    async def fake_safe_get(_client, url):
        return FakeResponse(url, 404, "")

    monkeypatch.setattr("app.trust_discovery.is_public_http_url", lambda _url: True)
    monkeypatch.setattr("app.trust_discovery.safe_get", fake_safe_get)

    result = await enrich_scan_with_trust_pages(base_scan([page("/pret-immobilier"), page("/mentions-legales")]))

    assert result["trust_page_discovery"]["attempted"] is True
    assert "/mentions-legales" in result["trust_page_discovery"]["found"]
    assert any(p.get("path") == "/mentions-legales" for p in result["pages"])


@pytest.mark.asyncio
async def test_custom_homepage_trust_link_is_added_to_review_evidence(monkeypatch):
    homepage_html = '<html><body><footer><a href="/qui-sommes-nous">Qui sommes-nous</a></footer></body></html>'

    async def fake_safe_get(_client, url):
        if url.rstrip("/") == "https://example.com":
            return FakeResponse("https://example.com/", 200, homepage_html)
        if url.endswith("/qui-sommes-nous"):
            return FakeResponse(url, 200, "<html><title>Qui sommes-nous</title><h1>Qui sommes-nous</h1></html>")
        return FakeResponse(url, 404, "")

    monkeypatch.setattr("app.trust_discovery.is_public_http_url", lambda _url: True)
    monkeypatch.setattr("app.trust_discovery.safe_get", fake_safe_get)

    result = await enrich_scan_with_trust_pages(base_scan([page("/pret-immobilier")]))

    assert "/qui-sommes-nous" in result["trust_page_discovery"]["found"]
    assert any(p.get("path") == "/qui-sommes-nous" for p in result["pages"])

    review = run_review(result)
    assert all(fix.get("rule") != "missing_trust_pages" for fix in review["cleaned_fixes"])


@pytest.mark.asyncio
async def test_french_privacy_probe_prevents_sample_false_positive(monkeypatch):
    async def fake_safe_get(_client, url):
        if url.endswith("/politique-de-confidentialite"):
            return FakeResponse(url, 200, "<html><title>Confidentialité</title><h1>Politique de confidentialité</h1></html>")
        if url.rstrip("/") == "https://example.com":
            return FakeResponse("https://example.com/", 200, "<html><body></body></html>")
        return FakeResponse(url, 404, "")

    monkeypatch.setattr("app.trust_discovery.is_public_http_url", lambda _url: True)
    monkeypatch.setattr("app.trust_discovery.safe_get", fake_safe_get)

    result = await enrich_scan_with_trust_pages(base_scan([page("/pret-immobilier")]))

    assert result["trust_page_discovery"]["conclusive"] is True
    assert "/politique-de-confidentialite" in result["trust_page_discovery"]["found"]
    assert result["technical_audit_summary"]["trust_page_discovery"]["found"]

    review = run_review(result)
    assert all(fix.get("rule") != "missing_trust_pages" for fix in review["cleaned_fixes"])
