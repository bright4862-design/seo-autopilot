import json

from fastapi.testclient import TestClient


def _private_scan_result() -> dict:
    page = {
        "url": "https://privacy-http.example/location",
        "final_url": "https://privacy-http.example/location",
        "status_code": 200,
        "page_evidence_class": "usable_html",
        "title": "Safe public title",
        "main_text": ["PRIVATE-B10-SHINGLE-HTTP-99117"],
        "main_text_evidence_version": "main_text_signature_v1",
        "main_text_signature": "PRIVATE-B10-SIGNATURE-HTTP-99117",
        "main_text_representation": "sha256_five_token_shingles",
        "main_text_token_count": 17,
        "main_text_char_count": 99117,
        "main_text_source": "main",
        "main_text_verified": True,
        "main_text_reason": "accepted_main_landmark",
        "main_text_truncated": False,
        "local_entity_observations": {
            "version": "local_entity_producer_v1_jsonld_explicit_identity",
            "state": "observed",
            "observations": [
                {
                    "entity_key": "https://privacy-http.example/#private-entity-99117",
                    "name": "PRIVATE ENTITY HTTP 99117",
                    "address": "99117 Private HTTP Avenue",
                    "phone": "+1-555-99117",
                }
            ],
        },
        "contextual_freshness_evidence": {
            "version": "contextual_freshness_v1",
            "intent_evidence": ["PRIVATE FRESHNESS HTTP 99117"],
        },
        "_reachability_links": [
            {"href": "https://privacy-http.example/private-target-99117"}
        ],
    }
    return {
        "success": True,
        "scanner_version": "python_scanner_v3_bounded_request",
        "scan_mode": "advanced",
        "pages_crawled": 1,
        "pages_found": 1,
        "pages": [page],
        "crawled_pages": [page],
        "grouped_findings": [],
        "render_evidence": {
            "version": "render_evidence_v1",
            "pages_evaluated": 1,
            "evidence_state": "raw_html_sufficient",
            "rendering_mode": "raw_html_first",
        },
        "technical_audit_summary": {"pages_crawled": 1},
        "scan_summary": {"pages_scanned": 1},
        "normalized_domain": "privacy-http.example",
        "respect_robots_txt": True,
        "owner_attested_robots_override": False,
    }


def test_synchronous_scan_http_response_cannot_publish_private_stage2_evidence(monkeypatch):
    from app import main

    async def private_scan(**_kwargs):
        return _private_scan_result()

    async def unchanged_trust(result):
        return result

    monkeypatch.setattr(main, "run_scan", private_scan)
    monkeypatch.setattr(main, "enrich_scan_with_trust_pages", unchanged_trust)
    monkeypatch.setattr(
        main,
        "apply_indexability_quality_to_result",
        lambda result, **_kwargs: result,
    )
    monkeypatch.setattr(main, "SCANNER_API_KEY", "stage2-privacy-test-key")

    response = TestClient(main.app).post(
        "/scan",
        json={
            "website_url": "https://privacy-http.example/location",
            "request_id": "privacy-http-request-1",
            "idempotency_key": "privacy-http-request-1",
            "scan_id": "privacy-http-scan-1",
            "scan_run_id": "privacy-http-scan-1",
            "respect_robots_txt": True,
        },
        headers={"X-Scanner-Key": "stage2-privacy-test-key"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["pages"][0]["title"] == "Safe public title"
    assert body["crawled_pages"][0]["title"] == "Safe public title"
    assert "main_text" not in body["pages"][0]
    assert "main_text_signature" not in body["pages"][0]
    assert "local_entity_observations" not in body["pages"][0]
    assert "contextual_freshness_evidence" not in body["pages"][0]
    assert "_reachability_links" not in body["pages"][0]

    serialized = json.dumps(body, sort_keys=True)
    for sentinel in (
        "PRIVATE-B10-SHINGLE-HTTP-99117",
        "PRIVATE-B10-SIGNATURE-HTTP-99117",
        "PRIVATE ENTITY HTTP 99117",
        "99117 Private HTTP Avenue",
        "+1-555-99117",
        "PRIVATE FRESHNESS HTTP 99117",
        "private-target-99117",
    ):
        assert sentinel not in serialized
