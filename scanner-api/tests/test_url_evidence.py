from app.url_evidence import URL_EVIDENCE_VERSION, apply_verified_url_contract


def test_contract_marks_only_successful_final_urls_as_live():
    result = {
        "pages": [
            {
                "url": "https://example.com/old",
                "final_url": "https://example.com/live",
                "status_code": 200,
            },
            {
                "url": "https://example.com/missing",
                "final_url": "https://example.com/missing",
                "status_code": 404,
            },
            {
                "url": "https://example.com/error",
                "final_url": "https://example.com/error",
                "status_code": 500,
            },
        ]
    }

    contracted = apply_verified_url_contract(result)

    assert contracted["url_evidence_version"] == URL_EVIDENCE_VERSION
    assert contracted["verified_live_url_count"] == 1
    assert contracted["confirmed_error_url_count"] == 2
    assert contracted["pages"][0]["verified_final_url"] == "https://example.com/live"
    assert contracted["pages"][0]["url_verification"] == "live_200"
    assert "verified_final_url" not in contracted["pages"][1]
    assert contracted["pages"][1]["url_verification"] == "confirmed_http_error"
    assert contracted["technical_audit_summary"]["redirecting_url_count"] == 1


def test_contract_rejects_fetch_errors_and_non_http_final_values():
    result = {
        "crawled_pages": [
            {
                "url": "https://example.com/timeout",
                "final_url": "https://example.com/timeout",
                "status_code": 200,
                "fetch_error": "timeout",
            },
            {
                "url": "https://example.com/javascript",
                "final_url": "javascript:alert(1)",
                "status_code": 200,
            },
        ]
    }

    contracted = apply_verified_url_contract(result)

    assert contracted["verified_live_url_count"] == 0
    assert all(
        "verified_final_url" not in page for page in contracted["crawled_pages"]
    )
