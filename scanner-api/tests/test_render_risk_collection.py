import httpx
import pytest

from app.render_risk_collection import (
    build_study_record,
    fetch_study_record,
    normalize_manifest_record,
)


MANIFEST = {
    "site": "example-saas",
    "url": "https://example.com/app",
    "stratum": "saas_js",
}


def scan_result(state="material_client_rendering_risk"):
    return {
        "success": True,
        "scanner_version": "python_scanner_v2_contract_parity",
        "pages_crawled": 20,
        "pages_found": 24,
        "render_evidence": {
            "version": "render_evidence_v1",
            "pages_evaluated": 18,
            "client_rendering_suspected_pages": 5,
            "suspected_ratio": 0.2778,
            "evidence_state": state,
            "representative_pages": ["/app"],
        },
    }


def test_manifest_requires_an_absolute_url_and_valid_stratum():
    normalized = normalize_manifest_record(MANIFEST)
    assert normalized["scan_mode"] == "advanced"
    assert normalized["manual_js_disabled_verdict"] == "not_reviewed"

    with pytest.raises(ValueError, match="absolute http"):
        normalize_manifest_record({**MANIFEST, "url": "/relative"})
    with pytest.raises(ValueError, match="stratum"):
        normalize_manifest_record({**MANIFEST, "stratum": "other"})


def test_study_record_preserves_scanner_render_evidence_without_recalculating_it():
    result = scan_result()
    record = build_study_record(MANIFEST, result)

    assert record["render_evidence"] == result["render_evidence"]
    assert record["render_evidence"] is not result["render_evidence"]
    assert record["manual_js_disabled_verdict"] == "not_reviewed"
    assert record["scan_status"] == "complete"
    assert record["pages_crawled"] == 20


@pytest.mark.asyncio
async def test_transient_503_is_retried_and_not_recorded_as_raw_html_sufficient():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.headers["x-scanner-key"] == "secret"
        if calls == 1:
            return httpx.Response(503, json={"detail": "instance unavailable"})
        return httpx.Response(200, json=scan_result("raw_html_sufficient"))

    async def no_sleep(_seconds):
        return None

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        record, failure = await fetch_study_record(
            client,
            "https://scanner.example.run.app",
            "secret",
            MANIFEST,
            attempts=2,
            sleep=no_sleep,
        )

    assert calls == 2
    assert failure is None
    assert record["render_evidence"]["evidence_state"] == "raw_html_sufficient"


@pytest.mark.asyncio
async def test_non_retryable_auth_failure_is_written_only_as_a_failure():
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401, json={"detail": "Unauthorized"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        record, failure = await fetch_study_record(
            client,
            "https://scanner.example.run.app",
            "wrong-secret",
            MANIFEST,
            attempts=3,
        )

    assert calls == 1
    assert record is None
    assert failure["scan_status"] == "failed"
    assert failure["status_code"] == 401
    assert "Unauthorized" in failure["error"]
    assert "render_evidence" not in failure


@pytest.mark.asyncio
async def test_invalid_success_payload_is_not_mislabeled_as_a_completed_measurement():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "pages_crawled": 12})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        record, failure = await fetch_study_record(
            client,
            "https://scanner.example.run.app",
            "secret",
            MANIFEST,
        )

    assert record is None
    assert failure["scan_status"] == "failed"
    assert "render_evidence" in failure["error"]
