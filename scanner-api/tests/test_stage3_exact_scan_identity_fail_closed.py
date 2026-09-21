import json

from app.repair_contract_v2 import _build_stage3_handoff_v2_source, _trusted_stage3_scan_id


def test_stage3_structured_scan_identity_cannot_become_trusted_text():
    sentinel = "https://private.example/operator-debug?token=structured-scan-id"
    malformed_identity = {"private": sentinel}
    scan_result = {
        "scan_id": malformed_identity,
        "scan_run_id": malformed_identity,
        "normalized_domain": "example.com",
    }

    assert _trusted_stage3_scan_id(scan_result) == ""


def test_b24_signed_source_fails_closed_for_structured_scan_identity():
    sentinel = "https://private.example/operator-debug?token=structured-scan-id"
    malformed_identity = {"private": sentinel}
    source = _build_stage3_handoff_v2_source(
        [
            {
                "fix_id": "broken-page",
                "title": "Broken page",
                "affected_pages": ["https://example.com/broken"],
                "stage3_counts": {
                    "observation_count": 1,
                    "known_population_count": 1,
                },
                "stage3_priority_factors": {
                    "version": "repair_priority_v3_four_factor_v1",
                    "impact": 5,
                    "reach": 1.0,
                    "page_value": 1.0,
                    "confidence": 1.0,
                    "priority_factor_score": 5.0,
                },
            }
        ],
        [],
        {
            "scan_id": malformed_identity,
            "scan_run_id": malformed_identity,
            "normalized_domain": "example.com",
        },
        scan_origin="https://example.com",
        identity_version="evidence_url_identity_v2_published_route",
    )

    assert source is None
    assert sentinel not in json.dumps(source, sort_keys=True)
