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
    steps = " ".join(card["what_to_do_steps"]).lower()
    assert "every affected family listed in the card" in steps
    assert "conversion, loan, location" not in steps


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


def test_authoritative_guide_group_explicitly_stamps_not_low_value():
    pages = [
        _page(f"/blog/article-{index}", "guide_article", meta_description="")
        for index in range(3)
    ]
    card = _fix(_run(pages), "missing_meta_description")

    assert card["page_template_family"] == "guide_article"
    assert card["is_low_value_page"] is False
    assert card["business_importance"] == "standard"




def _rate_limited_page(path, family="standard"):
    return _page(
        path,
        family,
        status_code=429,
        fetch_error="HTTP 429 Too Many Requests",
        title="Connection verification",
        url_confidence="linked_but_failed",
        source_pages=["/"],
    )


def test_fully_blocked_crawl_is_provisional_and_needs_verification():
    pages = [
        _rate_limited_page("/category/one", "collection_page"),
        _rate_limited_page("/category/two", "collection_page"),
        _rate_limited_page("/activity/one", "activity_detail"),
        _rate_limited_page("/activity/two", "activity_detail"),
        _rate_limited_page("/locations/paris", "location_landing"),
        _rate_limited_page("/guide/help", "guide_article"),
    ]
    result = _run_with_coverage(pages, pages_found=len(pages))
    rate_cards = [fix for fix in result["cleaned_fixes"] if fix.get("rule") == "rate_limited_page"]

    assert len(rate_cards) == 1
    card = rate_cards[0]
    assert card["page_scope"] == "cross_cutting"
    assert card["page_template_family"] == "mixed"
    assert card["evidence_status"] == "needs_verification"
    assert card["verification_state"] == "needs_verification"
    assert card["limitation_code"] == "rate_limit_requires_log_confirmation"
    assert card["status_codes"] == [429]
    assert len(card["affected_pages"]) == len(pages)
    assert result["scan_status"] == "blocked_or_incomplete"
    assert result["review_confidence_state"] == "blocked_access_needs_verification"
    assert result["score_is_provisional"] is True
    assert result["access_evidence_state"] == "blocked"
    assert result["website_health_report"]["health_grade"] == "Blocked / incomplete"
    assert result["health_score"] is None
    assert result["health_score_status"] == "insufficient_evidence"
    assert result["review_input_quality"]["access_evidence_state"] == "blocked"
    assert result["review_input_quality"]["score_is_provisional"] is True
    assert "score is provisional" in result["customer_summary"].lower()
    assert any("HTTP 429" in item for item in result["website_health_report"]["limitations"])
    assert not any(fix.get("page_scope") == "sitewide" for fix in result["cleaned_fixes"])
    assert not any(fix.get("rule") in {"canonical_missing", "missing_h1", "missing_meta_description", "image_alt_text"} for fix in result["cleaned_fixes"])


def test_partially_blocked_crawl_is_complete_with_access_limitations():
    pages = [
        _rate_limited_page("/category/one", "collection_page"),
        _rate_limited_page("/activity/one", "activity_detail"),
        _page("/", "homepage"),
        _page("/contact", "contact"),
        _page("/guide/one", "guide_article"),
        _page("/locations/paris", "location_landing"),
    ]
    result = _run_with_coverage(pages, pages_found=len(pages))
    card = _fix(result, "rate_limited_page")

    assert card["page_scope"] == "cross_cutting"
    assert card["page_template_family"] == "mixed"
    assert card["evidence_status"] == "needs_verification"
    assert result["scan_status"] == "complete_with_access_limitations"
    assert result["review_confidence_state"] == "partial_access_needs_verification"
    assert result["score_is_provisional"] is True
    assert result["access_evidence_state"] == "partial_access_limited"
    assert result["website_health_report"]["health_grade"] != "Blocked / incomplete"
    assert "score is provisional" in result["customer_summary"].lower()
    assert any("HTTP 429" in item for item in result["website_health_report"]["limitations"])


def test_two_page_clean_crawl_is_insufficient_evidence():
    result = _run_with_coverage([_page("/", "homepage"), _page("/contact", "contact")], pages_found=2)

    assert result["score_is_provisional"] is True
    assert result["access_evidence_state"] == "insufficient_evidence"
    assert result["scan_status"] == "inconclusive_insufficient_evidence"
    assert not any("HTTP 429" in item for item in result["website_health_report"]["limitations"])
