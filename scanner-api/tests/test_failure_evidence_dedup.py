from app.review import (
    FAILURE_EVIDENCE_DEDUP_VERSION,
    run_review,
    suppress_duplicate_group_cards,
)


def page(path: str, status: int, **extra):
    return {
        "url": f"https://example.com{path}",
        "final_url": f"https://example.com{path}",
        "status_code": status,
        "fetch_error": f"HTTP {status}",
        "source_pages": ["https://example.com/"],
        "url_confidence": "linked_but_failed",
        **extra,
    }


def test_verified_404_group_suppresses_overlapping_failed_page_cards():
    failed = [page("/missing-a?utm_source=a", 404), page("/missing-b", 404)]
    result = run_review({
        "website_url": "https://example.com",
        "pages_found": 20,
        "pages_crawled": 2,
        "pages": failed,
        "verified_failed_pages": failed,
        "findings": [
            {"rule": "failed_page", "page_url": "/missing-a?utm_source=b", "affected_pages": ["/missing-a?utm_source=b"], "status_code": 404},
            {"rule": "failed_page", "page_url": "/missing-b", "affected_pages": ["/missing-b"], "status_code": 404},
        ],
    })

    cards = [
        fix for fix in result["cleaned_fixes"]
        if fix.get("rule") in {"broken_page", "failed_page", "404_error"}
    ]
    assert len(cards) == 1
    assert cards[0]["rule"] == "broken_page"
    assert len(cards[0]["affected_pages"]) == 2


def test_single_503_is_verification_evidence_not_a_scoring_defect():
    failed = page("/temporarily-unavailable", 503)
    result = run_review({
        "website_url": "https://example.com",
        "pages_found": 20,
        "pages_crawled": 1,
        "pages": [failed],
        "verified_failed_pages": [failed],
    })
    card = next(fix for fix in result["cleaned_fixes"] if fix.get("rule") == "server_error")

    assert card["verification_state"] == "needs_verification"
    assert card["evidence_status"] == "needs_verification"
    assert card["non_scoring"] is True
    assert card["failure_evidence_dedup_version"] == FAILURE_EVIDENCE_DEDUP_VERSION


def test_explicitly_repeated_503_remains_confirmed():
    failed = page("/repeated-server-error", 503, failure_observation_count=2)
    result = run_review({
        "website_url": "https://example.com",
        "pages_found": 20,
        "pages_crawled": 1,
        "pages": [failed],
        "verified_failed_pages": [failed],
    })
    card = next(fix for fix in result["cleaned_fixes"] if fix.get("rule") == "server_error")

    assert card.get("verification_state") != "needs_verification"
    assert card.get("non_scoring") is not True
    assert card["failure_evidence_dedup_version"] == FAILURE_EVIDENCE_DEDUP_VERSION


def test_redirect_destination_503_and_server_error_are_one_remediation_group():
    urls = ["/draft-one?utm_source=redirect", "/draft-two"]
    fixes = [
        {
            "rule": "server_error",
            "source": "scanner_verified_failed_pages:5xx",
            "affected_pages": urls,
            "status_codes": [503],
            "confidence_score": 68,
        },
        {
            "rule": "redirect_destination_failed",
            "source": "redirect_validation",
            "affected_pages": ["/draft-one?utm_source=sitemap", "/draft-two"],
            "status_codes": [503],
            "confidence_score": 90,
        },
    ]

    assert len(suppress_duplicate_group_cards(fixes)) == 1
