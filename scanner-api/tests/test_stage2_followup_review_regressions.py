from datetime import date
import json

from app.scan_job import (
    build_authority_review_payload,
    build_completion_envelope,
    build_limited_envelope,
)
from app.stage2_connected_provider_evidence import (
    build_crux_scan_evidence,
    build_gsc_scan_evidence,
)


PRIVATE_SENTINEL = "PRIVATE-STAGE2-BOUNDARY-SENTINEL-20260920"


def _raw_result() -> dict:
    page = {
        "url": "https://privacy.example/location",
        "final_url": "https://privacy.example/location",
        "status_code": 200,
        "page_evidence_class": "usable_html",
        "title": "Public title",
        "main_text": [PRIVATE_SENTINEL],
        "main_text_signature": PRIVATE_SENTINEL,
        "local_entity_observations": {
            "version": "local_entity_producer_v1_jsonld_explicit_identity",
            "observations": [{"entity_key": PRIVATE_SENTINEL, "phone": PRIVATE_SENTINEL}],
        },
        "contextual_freshness_evidence": {
            "version": "contextual_freshness_v1",
            "intent_evidence": [PRIVATE_SENTINEL],
        },
        "_reachability_links": [{"href": PRIVATE_SENTINEL}],
    }
    aggregate = {
        "producer_version": "local_entity_producer_v1_jsonld_explicit_identity",
        "local_entity_version": "local_entity_completeness_v1",
        "nap_consistency_version": "local_entity_nap_consistency_v1",
        "eligible_observations": 1,
        "selected_observations": 1,
        "selection_truncated": False,
        "future_debug_observation": PRIVATE_SENTINEL,
        "completeness": [
            {
                "version": "local_entity_completeness_v1",
                "state": "pass",
                "reason": "required_local_details_observed",
                "page_url": PRIVATE_SENTINEL,
                "entity_key": PRIVATE_SENTINEL,
            }
        ],
        "nap_consistency": {
            "version": "local_entity_nap_consistency_v1",
            "state": "pass",
            "verified_observations": 1,
            "ambiguous_observations": 0,
            "comparable_entity_groups": 1,
            "unverified_entity_groups": 0,
            "scope": "cross_page_explicit_entity_identity",
            "sitewide_consistency_claim": False,
            "future_debug_observation": PRIVATE_SENTINEL,
            "inconsistencies": [],
        },
    }
    return {
        "success": True,
        "request_id": "request-privacy-followup",
        "idempotency_key": "request-privacy-followup",
        "scan_id": "scan-privacy-followup",
        "scan_run_id": "scan-privacy-followup",
        "normalized_domain": "privacy.example",
        "respect_robots_txt": True,
        "owner_attested_robots_override": False,
        "pages_crawled": 1,
        "pages_found": 1,
        "pages": [page],
        "crawled_pages": [page],
        "grouped_findings": [],
        "local_entity_scan_evidence": aggregate,
        "technical_audit_summary": {
            "pages_crawled": 1,
            "local_entity_scan_evidence": aggregate,
        },
        "scan_summary": {"pages_scanned": 1},
    }


def _scan() -> dict:
    return {
        "id": "scan-privacy-followup",
        "project_id": "project-privacy-followup",
        "owner_user_id": "owner-privacy-followup",
        "request_id": "request-privacy-followup",
        "idempotency_key": "request-privacy-followup",
        "attempt_count": 1,
    }


def _review() -> dict:
    return {
        "release_gate_eligible": True,
        "scan_status": "complete",
        "recommendations": [],
    }


def _assert_private_stage2_evidence_absent(value) -> None:
    serialized = json.dumps(value, sort_keys=True)
    assert PRIVATE_SENTINEL not in serialized
    for field in (
        "main_text",
        "main_text_signature",
        "local_entity_observations",
        "contextual_freshness_evidence",
        "_reachability_links",
        "future_debug_observation",
    ):
        assert f'"{field}"' not in serialized


def test_authority_helper_defensively_projects_raw_stage2_result():
    payload = build_authority_review_payload(_raw_result())
    _assert_private_stage2_evidence_absent(payload)
    assert payload["crawled_pages"][0]["title"] == "Public title"


def test_signed_envelope_helpers_defensively_project_raw_stage2_result():
    raw = _raw_result()
    completion = build_completion_envelope(_scan(), raw, _review(), "followup-test-key")
    limited = build_limited_envelope(_scan(), raw, _review(), "followup-test-key")

    for envelope in (completion, limited):
        _assert_private_stage2_evidence_absent(envelope)
        assert envelope["scan"]["crawled_pages"][0]["title"] == "Public title"
        assert len(envelope["proof"]) == 64


def test_future_dated_crux_and_gsc_evidence_fail_closed():
    as_of = date(2026, 9, 20)
    future = "2026-10-20"

    crux = build_crux_scan_evidence(
        expected_scan_id="scan-provider-followup",
        payload={
            "scan_id": "scan-provider-followup",
            "connection_state": "connected",
            "authorized": True,
            "observed_at": future,
            "scope": "origin",
            "metrics": {"lcp_ms": 1200, "inp_ms": 100, "cls": 0.03},
        },
        as_of=as_of,
    )
    assert crux["state"] == "unavailable"
    assert crux["reason"] == "provider_observation_time_invalid"
    assert crux["metrics"] is None

    assessed = ["https://example.com/pricing"]
    gsc = build_gsc_scan_evidence(
        expected_scan_id="scan-provider-followup",
        assessed_urls=assessed,
        payload={
            "scan_id": "scan-provider-followup",
            "connection_state": "connected",
            "authorized": True,
            "observed_at": future,
            "pages": [
                {
                    "url": assessed[0],
                    "metrics": {
                        "clicks": 12,
                        "impressions": 100,
                        "position": 2.5,
                        "index_state": "indexed",
                    },
                }
            ],
        },
        as_of=as_of,
    )
    assert gsc["state"] == "unavailable"
    assert gsc["reason"] == "provider_observation_time_invalid"
    assert gsc["pages"] == [
        {
            "url": assessed[0],
            "state": "unavailable",
            "reason": "provider_observation_time_invalid",
            "metrics": None,
        }
    ]
