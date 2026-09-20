import json

from app.main import enforce_scan_response_page_budget
from app.render_evidence_quality import apply_render_evidence_quality
from app.scan_job import (
    build_authority_review_payload,
    build_completion_envelope,
    build_limited_envelope,
)


PRIVATE_FIELDS = {
    "main_text",
    "main_text_evidence_version",
    "main_text_signature",
    "main_text_representation",
    "main_text_token_count",
    "main_text_char_count",
    "main_text_source",
    "main_text_verified",
    "main_text_reason",
    "main_text_truncated",
    "local_entity_observations",
    "location_context",
    "contextual_freshness_evidence",
    "_reachability_links",
}

SENTINELS = {
    "shingle": "b10-shingle-deadbeef00112233",
    "signature": "b10-signature-private-445566",
    "source_text": "PRIVATE MAIN CONTENT SENTINEL 99117",
    "entity_id": "https://privacy.example/#branch-99117",
    "entity_name": "Privacy Sentinel Branch 99117",
    "address": "99117 Private Evidence Avenue",
    "phone": "+1-555-99117",
    "hours": "Mo-Fr 09:00-17:00 SENTINEL99117",
    "freshness": "PRIVATE CURRENT INTENT SENTINEL 99117",
}


def _private_page() -> dict:
    return {
        "url": "https://privacy.example/location",
        "final_url": "https://privacy.example/location",
        "status_code": 200,
        "page_evidence_class": "usable_html",
        "title": "Safe public title",
        "transfer_bytes": 4096,
        "main_text": [SENTINELS["shingle"]],
        "main_text_evidence_version": "main_text_signature_v1",
        "main_text_signature": SENTINELS["signature"],
        "main_text_representation": "sha256_five_token_shingles",
        "main_text_token_count": 99,
        "main_text_char_count": 99117,
        "main_text_source": "main",
        "main_text_verified": True,
        "main_text_reason": "accepted_main_landmark",
        "main_text_truncated": False,
        "local_entity_observations": {
            "version": "local_entity_producer_v1_jsonld_explicit_identity",
            "state": "observed",
            "observations": [{
                "entity_key": SENTINELS["entity_id"],
                "name": SENTINELS["entity_name"],
                "address": SENTINELS["address"],
                "phone": SENTINELS["phone"],
                "regular_hours": SENTINELS["hours"],
            }],
        },
        "location_context": {
            "visible_text": SENTINELS["source_text"],
            "title": SENTINELS["entity_name"],
        },
        "contextual_freshness_evidence": {
            "version": "contextual_freshness_v1",
            "intent_evidence": [SENTINELS["freshness"]],
        },
        "_reachability_links": [{"href": "https://privacy.example/private-target"}],
    }


def _local_entity_aggregate() -> dict:
    return {
        "producer_version": "local_entity_producer_v1_jsonld_explicit_identity",
        "local_entity_version": "local_entity_completeness_v1",
        "nap_consistency_version": "local_entity_nap_consistency_v1",
        "eligible_observations": 1,
        "selected_observations": 1,
        "selection_truncated": False,
        "completeness": [{
            "page_url": "https://privacy.example/location",
            "entity_key": SENTINELS["entity_id"],
            "entity_match": "verified",
            "entity_identity_reason": "absolute_http_jsonld_id",
            "source": "structured_data",
            "surface_provenance": ["structured_data", "sitemap_reference"],
            "context_provenance_version": "local_entity_context_provenance_v1",
            "contextual_status_state": "observed_explicit",
            "contextual_status_provenance": [{
                "source": "accepted_heading",
                "value": SENTINELS["entity_name"],
            }],
            "version": "local_entity_completeness_v1",
            "state": "pass",
            "reason": "required_local_details_observed",
            "missing_required": [],
            "unverified_fields": [],
            "contextual_status": "open",
            "optional_available": {"photos": False},
        }],
        "nap_consistency": {
            "version": "local_entity_nap_consistency_v1",
            "state": "fail",
            "verified_observations": 2,
            "ambiguous_observations": 0,
            "comparable_entity_groups": 1,
            "unverified_entity_groups": 0,
            "scope": "cross_page_explicit_entity_identity",
            "sitewide_consistency_claim": False,
            "inconsistencies": [{
                "entity_key": SENTINELS["entity_id"],
                "fields": ["phone"],
                "source_count": 2,
                "provenance": ["structured_data"],
            }],
        },
    }


def _raw_result() -> dict:
    page = _private_page()
    aggregate = _local_entity_aggregate()
    return {
        "success": True,
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
        "local_entity_scan_evidence": aggregate,
        "technical_audit_summary": {
            "pages_crawled": 1,
            "local_entity_scan_evidence": aggregate,
        },
        "scan_summary": {"pages_scanned": 1},
        "normalized_domain": "privacy.example",
        "respect_robots_txt": True,
        "owner_attested_robots_override": False,
    }


def _post_crawl_result() -> dict:
    # This is the common transform immediately before both the synchronous
    # response budget boundary and durable authority handling.
    return apply_render_evidence_quality(_raw_result())


def _serialized(value) -> str:
    return json.dumps(value, sort_keys=True)


def _assert_private_values_absent(value) -> None:
    serialized = _serialized(value)
    for sentinel in SENTINELS.values():
        assert sentinel not in serialized


def _assert_page_is_projected(page: dict) -> None:
    assert page["title"] == "Safe public title"
    assert page["transfer_bytes"] == 4096
    assert PRIVATE_FIELDS.isdisjoint(page)


def _assert_local_aggregate_is_non_content_summary(value: dict) -> None:
    aggregate = value["local_entity_scan_evidence"]
    assert aggregate["eligible_observations"] == 1
    assert aggregate["selected_observations"] == 1
    assert aggregate["completeness"][0]["state"] == "pass"
    assert aggregate["completeness"][0]["entity_match"] == "verified"
    assert "page_url" not in aggregate["completeness"][0]
    assert "entity_key" not in aggregate["completeness"][0]
    assert "contextual_status_provenance" not in aggregate["completeness"][0]
    assert "entity_key" not in aggregate["nap_consistency"]["inconsistencies"][0]


def test_common_post_crawl_projection_removes_private_stage2_page_evidence():
    raw = _raw_result()
    projected = apply_render_evidence_quality(raw)

    # The projection must not mutate the producer evidence object itself; this
    # keeps source/review diagnostics available to the producing phase while the
    # result crossing the boundary is clean.
    assert raw["crawled_pages"][0]["main_text_signature"] == SENTINELS["signature"]
    assert raw["crawled_pages"][0]["local_entity_observations"]["observations"][0]["phone"] == SENTINELS["phone"]

    _assert_page_is_projected(projected["pages"][0])
    _assert_page_is_projected(projected["crawled_pages"][0])
    _assert_local_aggregate_is_non_content_summary(projected)
    _assert_local_aggregate_is_non_content_summary(projected["technical_audit_summary"])
    _assert_private_values_absent(projected)


def test_scan_response_page_budget_cannot_republish_private_stage2_evidence():
    response = enforce_scan_response_page_budget(_post_crawl_result(), "advanced")

    _assert_page_is_projected(response["pages"][0])
    _assert_page_is_projected(response["crawled_pages"][0])
    assert response["pages_crawled"] == 1
    _assert_private_values_absent(response)


def test_authority_review_payload_cannot_republish_private_stage2_evidence():
    payload = build_authority_review_payload(_post_crawl_result())

    _assert_page_is_projected(payload["crawled_pages"][0])
    assert payload["sampled_pages_sent_to_review"] == 1
    _assert_private_values_absent(payload)


def test_signed_completion_and_limited_scan_envelopes_carry_only_projected_pages():
    result = _post_crawl_result()
    scan = {
        "id": "scan-privacy-1",
        "project_id": "project-privacy-1",
        "owner_user_id": "owner-privacy-1",
        "request_id": "request-privacy-1",
        "idempotency_key": "request-privacy-1",
        "attempt_count": 1,
    }
    review = {
        "release_gate_eligible": True,
        "scan_status": "complete",
        "recommendations": [],
    }

    completion = build_completion_envelope(scan, result, review, "privacy-test-key")
    limited = build_limited_envelope(scan, result, review, "privacy-test-key")

    # The common pre-authority projection already removed producer-only evidence
    # before either envelope can be signed or persisted.
    for envelope in (completion, limited):
        _assert_page_is_projected(envelope["scan"]["crawled_pages"][0])
        _assert_private_values_absent(envelope)
        assert len(envelope["proof"]) == 64
