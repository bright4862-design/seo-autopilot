"""Canonical scoring-gate regression tests for app.review.run_review."""

from app.review import run_review


def _healthy_pages(n):
    return [
        {
            "final_url": f"https://x.com/p{i}",
            "status_code": 200,
            "title": f"Page {i}",
            "h1": f"Page {i}",
            "meta_description": "desc",
        }
        for i in range(n)
    ]


def test_complete_evidence_allows_normal_score():
    result = run_review({
        "website_url": "https://x.com",
        "pages": _healthy_pages(150),
        "scan_coverage": {"pages_found": 200, "pages_crawled": 150, "sampled_pages_sent_to_ai": 150},
    })

    assert result["scan_status"] == "complete"
    assert result["website_health_report"]["health_grade"] not in {"Scan incomplete", "Blocked / incomplete"}
    assert result["evidence_complete"] is True


def test_metadata_without_pages_is_scan_incomplete():
    result = run_review({
        "website_url": "https://www.funbooker.com",
        "pages": [],
        "crawled_pages": [],
        "findings": [],
        "scan_coverage": {"pages_found": 983, "pages_crawled": 150, "sampled_pages_sent_to_ai": 0},
    })

    assert result["scan_status"] == "incomplete_evidence"
    assert result["website_health_report"]["health_grade"] == "Scan incomplete"
    assert result["health_score"] <= 55
    assert result["evidence_complete"] is False
    assert len(result["cleaned_fixes"]) >= 1
    assert result["cleaned_fixes"][0]["who_can_do_this"] == "your_web_person"


def test_blocked_crawl_from_page_evidence_is_capped():
    result = run_review({
        "website_url": "https://www.meilleurtaux.com",
        "pages": [{"final_url": "https://www.meilleurtaux.com/", "status_code": 429}],
        "scan_coverage": {"pages_found": 50, "pages_crawled": 1, "sampled_pages_sent_to_ai": 1},
    })

    assert result["scan_status"] == "blocked_or_incomplete"
    assert result["website_health_report"]["health_grade"] == "Blocked / incomplete"
    assert result["health_score"] <= 45
    assert result["site_fingerprint"]["blocked_or_429_pages"] == 1


def test_metadata_only_block_is_flagged():
    result = run_review({
        "website_url": "https://x.com",
        "pages": [],
        "scan_coverage": {
            "pages_found": 40,
            "pages_crawled": 1,
            "sampled_pages_sent_to_ai": 1,
            "blocked_pages": 1,
        },
    })

    assert result["scan_status"] == "blocked_or_incomplete"
    assert result["website_health_report"]["health_grade"] == "Blocked / incomplete"
    assert result["site_fingerprint"]["blocked_or_429_pages"] == 1
    assert result["health_score"] <= 45


def test_healthy_crawl_with_incidental_blocks_is_not_capped():
    pages = _healthy_pages(150)
    pages[0]["status_code"] = 429
    pages[1]["status_code"] = 429

    result = run_review({
        "website_url": "https://x.com",
        "pages": pages,
        "scan_coverage": {"pages_found": 983, "pages_crawled": 150, "sampled_pages_sent_to_ai": 150},
    })

    assert result["scan_status"] == "complete"
    assert result["website_health_report"]["health_grade"] != "Blocked / incomplete"
    assert result["site_fingerprint"]["blocked_or_429_pages"] == 2
