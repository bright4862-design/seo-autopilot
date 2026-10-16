import json

from app.page_output_privacy import project_local_entity_scan_evidence


SENTINEL_ENTITY = "https://privacy.example/#future-private-entity-7719"
SENTINEL_PAGE = "https://privacy.example/future-private-page-7719"
SENTINEL_TEXT = "FUTURE PRIVATE LOCAL EVIDENCE 7719"


def _future_shape_local_entity_evidence() -> dict:
    return {
        "producer_version": "local_entity_producer_v1_jsonld_explicit_identity",
        "context_provenance_version": "local_entity_context_provenance_v1",
        "local_entity_version": "local_entity_completeness_v1",
        "nap_consistency_version": "local_entity_nap_consistency_v1",
        "eligible_observations": 2,
        "selected_observations": 2,
        "selection_truncated": False,
        # Simulate future producer additions. The external projection must be an
        # allowlist rather than forwarding unknown fields by default.
        "raw_observations": [{
            "entity_key": SENTINEL_ENTITY,
            "page_url": SENTINEL_PAGE,
            "name": SENTINEL_TEXT,
        }],
        "debug_provenance": {
            "page_url": SENTINEL_PAGE,
            "raw_heading": SENTINEL_TEXT,
        },
        "completeness": [{
            "page_url": SENTINEL_PAGE,
            "entity_key": SENTINEL_ENTITY,
            "entity_match": "verified",
            "entity_identity_reason": "absolute_http_jsonld_id",
            "source": "structured_data",
            "surface_provenance": ["structured_data"],
            "context_provenance_version": "local_entity_context_provenance_v1",
            "contextual_status_state": "observed_explicit",
            "contextual_status_provenance": [{"value": SENTINEL_TEXT}],
            "version": "local_entity_completeness_v1",
            "state": "pass",
            "reason": "required_local_details_observed",
            "missing_required": [],
            "unverified_fields": [],
            "contextual_status": "open",
            "optional_available": {"photos": False},
            "future_private_detail": SENTINEL_TEXT,
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
            # Simulate a future producer adding raw identity/debug collections.
            "entity_keys": [SENTINEL_ENTITY],
            "debug_rows": [{"page_url": SENTINEL_PAGE, "text": SENTINEL_TEXT}],
            "inconsistencies": [{
                "entity_key": SENTINEL_ENTITY,
                "fields": ["phone"],
                "source_count": 2,
                "provenance": ["structured_data"],
                "future_private_detail": SENTINEL_TEXT,
            }],
        },
    }


def test_local_entity_projection_is_fail_closed_for_future_top_level_fields():
    projected = project_local_entity_scan_evidence(_future_shape_local_entity_evidence())

    assert set(projected) == {
        "producer_version",
        "context_provenance_version",
        "local_entity_version",
        "nap_consistency_version",
        "eligible_observations",
        "selected_observations",
        "selection_truncated",
        "completeness",
        "nap_consistency",
    }
    serialized = json.dumps(projected, sort_keys=True)
    assert SENTINEL_ENTITY not in serialized
    assert SENTINEL_PAGE not in serialized
    assert SENTINEL_TEXT not in serialized


def test_local_entity_projection_is_fail_closed_for_future_nap_fields():
    projected = project_local_entity_scan_evidence(_future_shape_local_entity_evidence())
    nap = projected["nap_consistency"]

    assert set(nap) == {
        "version",
        "state",
        "verified_observations",
        "ambiguous_observations",
        "comparable_entity_groups",
        "unverified_entity_groups",
        "scope",
        "sitewide_consistency_claim",
        "inconsistencies",
    }
    assert nap["inconsistencies"] == [{
        "fields": ["phone"],
        "source_count": 2,
        "provenance": ["structured_data"],
    }]
