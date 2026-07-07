import pytest

from app.scanner import run_scan


@pytest.mark.asyncio
async def test_invalid_url_contract():
    result = await run_scan("not a url", scan_mode="advanced")
    assert result["success"] is False
    assert "error" in result


@pytest.mark.asyncio
async def test_success_contract_keys(monkeypatch):
    async def fake_load_sitemap_urls(*args, **kwargs):
        return []

    async def fake_fetch_and_extract(client, url, discovery):
        return {
            "url": url,
            "final_url": url,
            "path": "/",
            "status_code": 200,
            "fetch_error": "",
            "url_confidence": "confirmed_seed",
            "url_suspicion_reasons": [],
            "discovered_from": ["seed"],
            "source_pages": [],
            "link_text_samples": [],
            "title": "Home",
            "meta_description": "Description",
            "h1": "Home",
            "h1_count": 1,
            "canonical": url,
            "indexable": True,
            "estimated_page_intent": "standard",
            "image_missing_alt_count": 0,
            "_html": "",
        }

    monkeypatch.setattr("app.scanner.load_sitemap_urls", fake_load_sitemap_urls)
    monkeypatch.setattr("app.scanner.fetch_and_extract", fake_fetch_and_extract)

    result = await run_scan("https://example.com/", scan_mode="advanced")
    assert result["success"] is True
    assert isinstance(result["pages"], list)
    assert isinstance(result["recommendations"], list)
    assert isinstance(result["verified_failed_pages"], list)
    assert isinstance(result["suspicious_url_artifacts"], list)
    assert isinstance(result["technical_audit_summary"], dict)
