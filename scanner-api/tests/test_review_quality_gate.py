from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.review import run_review


def test_metadata_only_review_is_scan_incomplete_not_excellent() -> None:
    payload = {
        "scan": {
            "success": True,
            "version": "runAdvancedScan_v21_python_first",
            "scanner_version": "python_scanner_v2_contract_parity",
            "website_url": "https://www.funbooker.com/fr/",
            "normalized_url": "https://www.funbooker.com/fr/",
            "scan_mode": "advanced",
            "scan_coverage": {
                "pages_crawled": 150,
                "pages_found": 983,
                "sampled_pages_sent_to_ai": 0,
            },
            "pages_crawled": 150,
            "pages_found": 983,
            "advanced_scan_backend": "python_scanner_api",
            "deno_fallback_used": False,
            "pages": [],
            "crawled_pages": [],
            "verified_failed_pages": [],
            "suspicious_url_artifacts": [],
            "grouped_findings": [],
            "findings": [],
            "recommendations": [],
        }
    }

    result = run_review(payload)

    assert result["ai_provider"] == "python_review_api"
    assert result["review_version"] == "python_review_v1_archetype_templates"
    assert result["site_fingerprint"]["primary_archetype"] == "booking_experiences_marketplace"

    quality = result["review_input_quality"]
    assert quality["pages_crawled_reported"] == 150
    assert quality["pages_received"] == 0
    assert quality["sampled_pages_sent_to_ai"] == 0
    assert quality["evidence_complete"] is False
    assert quality["metadata_without_pages"] is True

    assert result["health_score"] <= 55
    assert result["website_health_report"]["health_score"] <= 55
    assert result["website_health_report"]["health_grade"] == "Scan incomplete"
    assert "page evidence" in result["ai_review_warning"]

    fixes = result["cleaned_fixes"]
    assert fixes
    assert fixes[0]["rule"] == "review_evidence_missing"
    assert fixes[0]["who_can_do_this"] == "your_web_person"
    assert fixes[0]["requires_developer"] is True


def test_blocked_crawl_is_capped_and_flagged() -> None:
    result = run_review({
        "website_url": "https://www.meilleurtaux.com",
        "pages": [{"final_url": "https://www.meilleurtaux.com/", "status_code": 429}],
        "scan_coverage": {"pages_found": 50, "pages_crawled": 1, "sampled_pages_sent_to_ai": 1},
    })

    assert result["health_score"] <= 45
    assert result["website_health_report"]["health_score"] <= 45
    assert result["website_health_report"]["health_grade"] == "Blocked / incomplete"
    assert result["scan_status"] == "blocked_or_incomplete"
    assert result["review_input_quality"]["blocked_or_429_pages"] == 1


def test_healthy_crawl_with_few_blocks_is_not_capped() -> None:
    pages = [{"final_url": f"https://x.com/p{i}", "status_code": 200} for i in range(150)]
    pages[0]["status_code"] = 429
    pages[1]["status_code"] = 429

    result = run_review({
        "website_url": "https://x.com",
        "pages": pages,
        "scan_coverage": {"pages_found": 983, "pages_crawled": 150, "sampled_pages_sent_to_ai": 150},
    })

    assert result["scan_status"] == "complete"
    assert result["website_health_report"]["health_grade"] != "Blocked / incomplete"
    assert result["review_input_quality"]["blocked_or_429_pages"] == 2
