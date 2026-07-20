from app.evidence_quality import apply_evidence_quality_gate, evaluate_evidence_quality


def page(path: str, *, words: int = 180, family: str = "standard", intent: str = "standard") -> dict:
    return {
        "url": f"https://example.com{path}",
        "final_url": f"https://example.com{path}",
        "path": path,
        "status_code": 200,
        "content_type": "text/html",
        "fetch_error": "",
        "title": "Useful page title",
        "h1": "Useful heading",
        "word_count": words,
        "page_template_family": family,
        "estimated_page_intent": intent,
    }


def payload(pages: list[dict]) -> dict:
    return {
        "website_url": "https://example.com/",
        "pages_found": len(pages),
        "pages_crawled": len(pages),
        "crawled_pages": pages,
    }


def complete_result() -> dict:
    return {
        "scan_status": "complete",
        "review_confidence_state": "complete",
        "score_is_provisional": False,
        "release_gate_eligible": True,
        "health_score": 72,
        "seo_score": 72,
        "health_grade": "Needs work",
        "customer_summary": "FixList reviewed the discovered pages.",
        "website_health_report": {},
        "scan_summary": {},
        "site_summary": {},
        "technical_audit_summary": {},
    }


def test_lamanna_style_default_route_crawl_becomes_provisional():
    pages = [
        page("/", words=328, family="homepage", intent="money_or_conversion"),
        page("/merch", family="standard"),
        page("/hello-world", family="standard"),
        page("/author/admin", family="route_boundary", intent="internal_or_auth"),
        page("/category/uncategorized", family="collection_page"),
    ]

    quality = evaluate_evidence_quality(payload(pages))
    assert quality["usable_html_page_count"] == 5
    assert quality["representative_html_page_count"] == 2
    assert quality["default_route_page_count"] == 3
    assert quality["discovery_quality_state"] == "default_route_dominated"
    assert quality["evidence_quality_blocking"] is True

    result = apply_evidence_quality_gate(complete_result(), payload(pages))
    assert result["scan_status"] == "inconclusive_insufficient_evidence"
    assert result["score_is_provisional"] is True
    assert result["release_gate_eligible"] is False
    assert result["health_score"] <= 55
    assert result["review_confidence_state"] == "insufficient_discovery_quality"
    assert result["next_best_step"] == "Verify sitemap and internal navigation coverage"
    assert result["website_health_report"]["evidence_quality_state"] == "insufficient_discovery"


def test_meaningful_one_page_site_remains_supported():
    pages = [page("/", words=420, family="homepage", intent="money_or_conversion")]
    result = apply_evidence_quality_gate(complete_result(), payload(pages))
    assert result["evidence_quality_state"] == "small_site_supported"
    assert result["discovery_quality_state"] == "small_site_supported"
    assert result["evidence_quality_blocking"] is False
    assert result["scan_status"] == "complete"
    assert result["score_is_provisional"] is False


def test_small_brochure_site_without_default_route_dominance_remains_complete():
    pages = [
        page("/", family="homepage"),
        page("/about", family="standard", intent="trust_or_legal"),
        page("/services", family="service_page", intent="money_or_conversion"),
        page("/contact", family="contact", intent="money_or_conversion"),
    ]
    result = apply_evidence_quality_gate(complete_result(), payload(pages))
    assert result["evidence_quality_state"] == "representative"
    assert result["representative_html_page_count"] == 4
    assert result["evidence_quality_blocking"] is False
    assert result["scan_status"] == "complete"


def test_hartzler_like_eighteen_page_site_remains_complete():
    pages = [page("/", family="homepage")] + [page(f"/product-{index}") for index in range(17)]
    result = apply_evidence_quality_gate(complete_result(), payload(pages))
    assert result["usable_html_page_count"] == 18
    assert result["representative_html_page_count"] == 18
    assert result["evidence_quality_blocking"] is False
    assert result["scan_status"] == "complete"


def test_funbooker_like_large_site_remains_complete():
    pages = [page("/", family="homepage")] + [
        page(f"/fr/annonce/activity-{index}/voir", family="activity_detail", intent="money_or_conversion")
        for index in range(149)
    ]
    result = apply_evidence_quality_gate(complete_result(), payload(pages))
    assert result["usable_html_page_count"] == 150
    assert result["representative_html_page_count"] == 150
    assert result["evidence_quality_blocking"] is False
    assert result["scan_status"] == "complete"


def test_access_limited_result_keeps_existing_status_and_limitation():
    pages = [
        page("/"),
        page("/hello-world"),
        page("/author/admin", family="route_boundary", intent="internal_or_auth"),
    ]
    result = complete_result()
    result.update({
        "scan_status": "complete_with_access_limitations",
        "review_confidence_state": "partial_access_needs_verification",
        "score_is_provisional": True,
        "release_gate_eligible": False,
        "limitation": "HTTP 429 results require access-log confirmation.",
    })
    calibrated = apply_evidence_quality_gate(result, payload(pages))
    assert calibrated["scan_status"] == "complete_with_access_limitations"
    assert calibrated["review_confidence_state"] == "partial_access_needs_verification"
    assert calibrated["score_is_provisional"] is True
    assert calibrated["limitation"] == "HTTP 429 results require access-log confirmation."
