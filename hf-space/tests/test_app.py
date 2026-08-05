import app
import pytest
from app import (
    DEMO_SCAN,
    Settings,
    build_grounded_prompt,
    extract_output_text,
    guided_answer,
    normalize_scan_result,
    page_count_phrase,
    run_scan_from_ui,
    validate_public_website_url,
)


def _live_scan(website: str, *, pages: int = 1) -> dict:
    return {
        "source": "live",
        "website": website,
        "status": "complete",
        "score": 91,
        "pages_crawled": pages,
        "pages_retained": pages,
        "grouped_fixes": 0,
        "release_gate_eligible": True,
        "score_is_provisional": False,
        "priorities": [],
    }


def _ignore_progress(*args, **kwargs) -> None:
    del args, kwargs


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
    assert "developer-labelled fix themselves" in prompt


def test_prompt_includes_recent_follow_up_context():
    prompt = build_grounded_prompt(
        "Can I do this myself?",
        DEMO_SCAN,
        [
            {"role": "user", "content": "How do I fix redirected links?"},
            {"role": "assistant", "content": "Start with the shared navigation."},
        ],
    )

    assert "Can I do this myself?" in prompt
    assert "How do I fix redirected links?" in prompt
    assert "Start with the shared navigation." in prompt


def test_guided_answer_is_grounded():
    answer = guided_answer("What should I fix first?", DEMO_SCAN)
    assert "redirected internal links" in answer.lower()
    assert "18 pages" in answer


def test_guided_answer_still_supports_diy():
    answer = guided_answer("Can I do this myself?", DEMO_SCAN)
    assert "yes, with care" in answer.lower()
    assert "backup" in answer.lower()
    assert "exact clicks or code" in answer.lower()


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
        "pages_crawled": 4,
        "crawled_pages": [
            {
                "url": "https://example.com/a",
                "final_url": "https://example.com/a",
                "status_code": 404,
            },
            {
                "url": "https://example.com/b",
                "final_url": "https://example.com/live-b",
                "status_code": 200,
            },
            {
                "url": "https://example.com/c",
                "final_url": "https://example.com/c",
                "status_code": 200,
            },
            {
                "url": "https://example.com/error",
                "final_url": "https://example.com/error",
                "status_code": 500,
            },
        ],
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
                "affected_urls": ["/a", "/b", "/not-crawled"],
                "description": "Two pages point to the wrong canonical URL.",
            }
        ],
    }

    result = normalize_scan_result("https://example.com", scan, review)

    assert result["source"] == "live"
    assert result["score"] == 74
    assert result["release_gate_eligible"] is True
    assert result["pages_retained"] == 4
    assert result["priorities"][0]["affected_pages"] == 3
    assert result["priorities"][0]["owner"] == "Web developer"
    assert result["priorities"][0]["verified_urls"] == [
        "https://example.com/live-b"
    ]
    assert result["priorities"][0]["url_evidence"][0]["status_code"] == 200
    assert "https://example.com/a" not in result["priorities"][0]["verified_urls"]
    assert "https://example.com/not-crawled" not in result["priorities"][0]["verified_urls"]


def test_priority_without_crawl_match_never_constructs_a_url():
    scan = {
        "website_url": "https://example.com",
        "pages_crawled": 1,
        "pages": [
            {
                "url": "https://example.com/real",
                "final_url": "https://example.com/real",
                "status_code": 200,
            }
        ],
    }
    review = {
        "recommendations": [
            {
                "title": "Fix missing descriptions",
                "affected_pages": ["/guessed-from-template"],
            }
        ]
    }

    result = normalize_scan_result("https://example.com", scan, review)

    assert result["priorities"][0]["verified_urls"] == []
    assert result["priorities"][0]["url_evidence_status"] == "no_verified_example"


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


def test_page_count_phrase_uses_singular_only_for_one():
    assert page_count_phrase(0) == "0 pages"
    assert page_count_phrase(1) == "1 page"
    assert page_count_phrase(2) == "2 pages"


def test_success_then_failure_clears_previous_domain_and_grok_context(monkeypatch):
    monkeypatch.setattr(
        app,
        "SETTINGS",
        Settings(
            scanner_api_url="https://scanner.example.run.app",
            scanner_api_key="private-key",
        ),
    )

    def fake_pipeline(website_url: str, scan_mode: str) -> dict:
        assert scan_mode == "advanced"
        if website_url == "https://alpha.example":
            return _live_scan(website_url)
        raise RuntimeError("beta transport failed")

    monkeypatch.setattr(app, "run_scan_pipeline", fake_pipeline)

    success = run_scan_from_ui(
        "https://alpha.example",
        "advanced",
        {},
        [],
        _ignore_progress,
    )
    assert success[0]["website"] == "https://alpha.example"
    assert "Authoritative" in success[3]
    assert "1 page crawled" in success[3]
    assert "1 page" in success[4][0]["content"]

    failure = run_scan_from_ui(
        "https://beta.example",
        "advanced",
        success[0],
        success[4],
        _ignore_progress,
    )
    assert failure[0] == {}
    assert failure[4] == []
    assert "beta transport failed" in failure[3]
    assert "alpha.example" not in "".join(map(str, failure))
    assert "No scan selected" in failure[1]


def test_failure_then_success_loads_only_the_new_domain(monkeypatch):
    monkeypatch.setattr(
        app,
        "SETTINGS",
        Settings(
            scanner_api_url="https://scanner.example.run.app",
            scanner_api_key="private-key",
        ),
    )
    attempts = iter(
        [
            RuntimeError("alpha scan failed"),
            _live_scan("https://gamma.example", pages=2),
        ]
    )

    def fake_pipeline(website_url: str, scan_mode: str) -> dict:
        del website_url
        assert scan_mode == "advanced"
        result = next(attempts)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(app, "run_scan_pipeline", fake_pipeline)

    failure = run_scan_from_ui(
        "https://alpha.example",
        "advanced",
        _live_scan("https://stale.example"),
        [{"role": "assistant", "content": "stale answer"}],
        _ignore_progress,
    )
    assert failure[0] == {}
    assert failure[4] == []

    success = run_scan_from_ui(
        "https://gamma.example",
        "advanced",
        failure[0],
        failure[4],
        _ignore_progress,
    )
    assert success[0]["website"] == "https://gamma.example"
    assert "gamma.example" in success[1]
    assert "stale.example" not in "".join(map(str, success))
    assert "alpha.example" not in "".join(map(str, success))
    assert "Authoritative" in success[3]
