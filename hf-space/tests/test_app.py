import pytest

from app import (
    DEMO_SCAN,
    Settings,
    build_grounded_prompt,
    extract_output_text,
    guided_answer,
    normalize_scan_result,
    validate_public_website_url,
)


def test_extract_output_text_from_responses_api():
    payload = {
        "output": [
            {
                "content": [
                    {"type": "output_text", "text": "Grounded answer."}
                ]
            }
        ]
    }
    assert extract_output_text(payload) == "Grounded answer."


def test_prompt_contains_authority_rules_and_evidence():
    prompt = build_grounded_prompt("What should I fix first?", DEMO_SCAN)
    assert "Never invent URLs" in prompt
    assert '"release_gate_eligible":true' in prompt
    assert "What should I fix first?" in prompt


def test_guided_answer_is_grounded():
    answer = guided_answer("What should I fix first?", DEMO_SCAN)
    assert "redirected internal links" in answer.lower()
    assert "18 pages" in answer


def test_validate_public_website_url_normalizes_domain():
    assert validate_public_website_url("example.com") == "https://example.com"


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8000",
        "http://127.0.0.1",
        "http://10.0.0.5",
        "http://169.254.169.254",
    ],
)
def test_validate_public_website_url_blocks_private_targets(url):
    with pytest.raises(ValueError):
        validate_public_website_url(url)


def test_normalize_scan_result_preserves_authority_and_priorities():
    scan = {
        "website_url": "https://example.com",
        "pages_found": 12,
        "pages_crawled": 10,
        "crawled_pages": [{"url": f"https://example.com/{index}"} for index in range(10)],
        "beta_revision_fingerprint": "fingerprint-v1",
    }
    review = {
        "scan_status": "complete",
        "health_score": 74,
        "release_gate_eligible": True,
        "score_is_provisional": False,
        "recommendations": [
            {
                "title": "Fix canonical tags",
                "priority": "high",
                "affected_urls": ["/a", "/b"],
                "description": "Two pages point to the wrong canonical URL.",
            }
        ],
    }

    result = normalize_scan_result("https://example.com", scan, review)

    assert result["source"] == "live"
    assert result["score"] == 74
    assert result["release_gate_eligible"] is True
    assert result["pages_retained"] == 10
    assert result["priorities"][0]["affected_pages"] == 2
    assert result["priorities"][0]["owner"] == "Web developer"


def test_scanner_connection_enables_cloud_run_grok_proxy():
    settings = Settings(
        project_id="",
        service_account_json="",
        scanner_api_url="https://scanner.example.run.app",
        scanner_api_key="private-key",
    )

    assert settings.live_scan_enabled is True
    assert settings.live_grok_enabled is True
    assert settings.model_id == "xai/grok-4.20-non-reasoning"
