"""Noindex remediation must describe the observed search-intent source."""

import pytest

from app.extract import extract_page
from app.scan_job import build_local_review
from app.scanner import build_findings, group_findings


ORIGIN = "https://example.com"


def _conflict_page(index, intent):
    url = f"{ORIGIN}/products/item-{index}"
    page = extract_page(
        '<html><head><title>A useful product</title>'
        '<meta name="robots" content="noindex"></head>'
        '<body><main><h1>A useful product</h1><p>Product details.</p></main></body></html>',
        url,
        url,
        200,
        "text/html",
        {"discovered_from": ["sitemap"] if "sitemap" in intent else ["internal_link"]},
    )
    if "declared" in intent:
        page["geo_search_intent"] = True
    return page


def _through_real_review(intents):
    pages = [_conflict_page(index, intent) for index, intent in enumerate(intents)]
    raw = build_findings(pages)
    grouped = group_findings(raw)
    result = {
        "success": True,
        "website_url": ORIGIN,
        "crawl_scope": {"requested_origin": ORIGIN},
        "pages": pages,
        "pages_found": len(pages),
        "pages_crawled": len(pages),
        "raw_findings": raw,
        "findings": grouped,
    }
    repairs = build_local_review(result)["canonical_repairs"]
    conflicts = lambda rows: [row for row in rows if row["rule"] == "sitemap_indexability_conflict"]
    return conflicts(raw), conflicts(grouped), conflicts(repairs)


def _customer_text(row):
    return " ".join(str(row.get(key) or "") for key in (
        "title", "issue_title", "plain_english_explanation", "plain_english_summary",
        "why_it_matters", "recommended_value", "recommendation", "ai_recommendation",
    )).lower()


def test_declared_intent_noindex_group_never_invents_sitemap_or_redirect_evidence():
    raw, grouped, canonical = _through_real_review([{"declared"}] * 3)

    assert len(raw) == 3
    for rows in (raw, grouped, canonical):
        assert rows
        for row in rows:
            text = _customer_text(row)
            assert "declared search intent" in text
            assert "noindex" in text
            assert "sitemap" not in text
            assert "redirect" not in text
            assert "remove the declared search intent" in text
    assert len(grouped) == len(canonical) == 1
    assert grouped[0]["page_count"] == canonical[0]["page_count"] == 3


def test_sitemap_noindex_group_retains_sitemap_action_without_claiming_redirects():
    raw, grouped, canonical = _through_real_review([{"sitemap"}] * 3)

    for rows in (raw, grouped, canonical):
        for row in rows:
            text = _customer_text(row)
            assert "sitemap" in text
            assert "noindex" in text
            assert "redirect" not in text
            assert "remove" in row["recommended_value"].lower()
    assert grouped[0]["title"] == "Remove non-indexable URLs from the sitemap"


@pytest.mark.parametrize("intents", [
    [{"sitemap"}, {"declared"}, {"declared"}],
    [{"declared"}, {"declared"}, {"sitemap"}],
    [{"sitemap", "declared"}] * 3,
])
def test_mixed_intent_group_qualifies_each_source_and_retains_both_actions(intents):
    _, grouped, canonical = _through_real_review(intents)

    for rows in (grouped, canonical):
        assert len(rows) == 1
        [row] = rows
        text = _customer_text(row)
        assert "redirect" not in text
        assert "declared search intent" in text
        assert "noindex" in text
        assert "for urls listed in the sitemap" in row["recommended_value"].lower()
        assert "for urls with declared search intent" in row["recommended_value"].lower()
        assert row["page_count"] == 3
        assert len(row["affected_pages"]) == 3
