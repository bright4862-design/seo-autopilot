"""Presentation-contract regressions for Python Review and frontend handoff."""

from app.review import run_review


def _run(pages):
    return run_review({
        "website_url": "https://example.com",
        "pages": pages,
        "scan_coverage": {
            "pages_found": max(10, len(pages)),
            "pages_crawled": len(pages),
            "sampled_pages_sent_to_ai": len(pages),
        },
    })


def _page(path, family="standard", **extra):
    return {
        "final_url": f"https://example.com{path}",
        "status_code": 200,
        "h1_count": 1,
        "meta_description": "Useful description",
        "canonical": f"https://example.com{path}",
        "page_template_family": family,
        **extra,
    }


def _fix(result, rule):
    return next(fix for fix in result["cleaned_fixes"] if fix.get("rule") == rule)


def test_activity_image_alt_card_has_specific_title_and_steps():
    pages = [
        _page(f"/fr/annonce/activity-{index}/voir", "activity_detail", image_missing_alt_count=2)
        for index in range(3)
    ]
    card = _fix(_run(pages), "image_alt_text")
    steps = " ".join(card["what_to_do_steps"]).lower()

    assert card["title"] == "Add missing image descriptions to activity/detail pages"
    assert "alt text" in steps
    assert "shared image component" in steps
    assert "routing" not in steps
    assert "canonical, schema" not in steps


def test_legal_canonical_card_has_specific_title_and_steps():
    pages = [
        _page("/fr/page/cgu", "legal_info", canonical=""),
        _page("/fr/page/mentions-legales", "legal_info", canonical=""),
    ]
    card = _fix(_run(pages), "canonical_missing")
    steps = " ".join(card["what_to_do_steps"]).lower()

    assert card["title"] == "Add canonical URLs to legal info pages"
    assert "self-referencing canonical" in steps
    assert "rendered page source" in steps
    assert "schema, indexability" not in steps


def test_single_missing_meta_description_has_singular_copy():
    card = _fix(
        _run([_page("/fr/annonce/activity/voir", "activity_detail", meta_description="")]),
        "missing_meta_description",
    )
    steps = " ".join(card["what_to_do_steps"]).lower()

    assert card["title"] == "Add a meta description to the affected page"
    assert "meta description" in steps
    assert "unique to the page" in steps


def test_single_missing_h1_has_singular_copy():
    card = _fix(_run([_page("/fr/review/page", h1_count=0)]), "missing_h1")
    steps = " ".join(card["what_to_do_steps"]).lower()

    assert card["title"] == "Add an H1 to the affected page"
    assert "one clear h1" in steps
    assert "h2 or h3" in steps


def test_cross_cutting_429_card_is_family_neutral():
    families = {
        "collection_page": ["/fr/category/escape-game", "/fr/category/karting"],
        "activity_detail": ["/fr/annonce/a1/voir", "/fr/annonce/a2/voir"],
        "location_landing": ["/fr/lieu/lyon"],
        "standard": ["/fr/theme/cadeau"],
    }
    pages = [
        _page(url, family, status_code=429)
        for family, urls in families.items()
        for url in urls
    ]
    card = _fix(_run(pages), "rate_limited_page")

    assert card["page_template_family"] == "mixed"
    assert card["page_scope"] == "cross_cutting"
    assert card["title"] == "Check pages blocked by rate limiting"
    assert len(card["affected_pages"]) == 6

def test_clean_review_does_not_emit_rate_limit_caveat():
    result = _run([_page("/clean")])
    limitations = result["website_health_report"]["limitations"]

    assert not any("HTTP 429" in limitation for limitation in limitations)


def test_rate_limit_card_and_caveat_are_emitted_together():
    result = _run([_page("/blocked", status_code=429)])
    limitations = result["website_health_report"]["limitations"]

    assert _fix(result, "rate_limited_page")
    assert any("HTTP 429" in limitation for limitation in limitations)


def test_server_error_card_does_not_trigger_rate_limit_caveat():
    result = _run([_page("/server-error", status_code=503)])
    limitations = result["website_health_report"]["limitations"]

    assert _fix(result, "server_error")
    assert not any("HTTP 429" in limitation for limitation in limitations)


def _run_with_coverage(pages, *, pages_found, pages_crawled=None):
    crawled = len(pages) if pages_crawled is None else pages_crawled
    return run_review({
        "website_url": "https://example.com",
        "pages": pages,
        "scan_coverage": {
            "pages_found": pages_found,
            "pages_crawled": crawled,
            "sampled_pages_sent_to_ai": len(pages),
        },
    })


def _sitewide_fixture(*, canonical="", image_missing_alt_count=0):
    families = {
        "homepage": 1,
        "conversion": 4,
        "loan_program": 5,
        "location_landing": 8,
        "guide_article": 6,
        "legal_info": 2,
        "contact": 1,
        "standard": 3,
    }
    pages = []
    for family, count in families.items():
        for index in range(count):
            path = "/" if family == "homepage" else f"/{family}/{index}"
            pages.append(_page(
                path,
                family,
                canonical=canonical or "",
                image_missing_alt_count=image_missing_alt_count,
            ))
    return families, pages


def test_sitewide_canonical_collapse_preserves_family_evidence():
    families, pages = _sitewide_fixture(canonical="")
    result = _run_with_coverage(pages, pages_found=36)
    canonical_cards = [fix for fix in result["cleaned_fixes"] if fix.get("rule") == "canonical_missing"]

    assert len(canonical_cards) == 1
    card = canonical_cards[0]
    assert card["title"] == "Add canonical URLs across the site"
    assert card["page_scope"] == "sitewide"
    assert card["page_template_family"] == ""
    assert card["page_count"] == len(pages)
    assert card["family_breakdown"] == families
    assert set(card["representative_pages_by_family"]) == set(families)
    assert len(card["source_pages"]) == len(families)
    assert card["sitewide_evidence"]["coverage_ratio"] == 1.0
    assert "global document-head" in card["plain_english_explanation"].lower()


def test_sitewide_collapse_does_not_overclaim_on_shallow_discovery_coverage():
    _, pages = _sitewide_fixture(canonical="")
    result = _run_with_coverage(pages, pages_found=200, pages_crawled=len(pages))
    canonical_cards = [fix for fix in result["cleaned_fixes"] if fix.get("rule") == "canonical_missing"]

    assert len(canonical_cards) >= 3
    assert not any(fix.get("page_scope") == "sitewide" for fix in canonical_cards)


def test_content_specific_image_findings_do_not_collapse_sitewide():
    _, pages = _sitewide_fixture(
        canonical="https://example.com/canonical",
        image_missing_alt_count=2,
    )
    result = _run_with_coverage(pages, pages_found=36)
    image_cards = [fix for fix in result["cleaned_fixes"] if fix.get("rule") == "image_alt_text"]

    assert len(image_cards) >= 3
    assert not any(fix.get("page_scope") == "sitewide" for fix in image_cards)

