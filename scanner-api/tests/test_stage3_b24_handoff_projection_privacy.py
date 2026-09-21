import json

from app.stage3_delivery import build_handoff_v2


def test_b24_customer_handoff_projects_public_fields_and_drops_private_structures():
    sentinel = "https://private.example/operator-debug?token=sentinel"
    handoff = build_handoff_v2(
        scan_identity={
            "scan_id": "scan-a",
            "scan_run_id": "scan-a",
            "normalized_domain": "example.com",
            "scan_origin": "https://example.com",
            "evidence_url_identity_version": "published_url_identity_v1",
            "operator_debug": {"url": sentinel},
        },
        fixes=[
            {
                "rule_id": {"private": sentinel},
                "title": ["private", sentinel],
                "root_cause_id": {"private": sentinel},
                "family_ids": ["family:product", {"private": sentinel}],
                "published_url": {"private": sentinel},
                "request_url": [sentinel],
                "final_url": "https://example.com/product",
                "affected_pages": ["https://example.com/product"],
                "observation_count": 1,
                "known_population_count": 4,
                "priority_factors": {
                    "version": "repair_priority_v3_four_factor_v1",
                    "impact": 5,
                    "impact_reason": "access/correctness",
                    "reach": 0.25,
                    "reach_state": "known",
                    "reach_affected_indexable": 1,
                    "reach_observed_indexable_family": 4,
                    "page_value": 1.0,
                    "page_value_state": "known",
                    "page_value_role": "money",
                    "page_value_source": "base_role",
                    "confidence": 1.0,
                    "confidence_state": "verified",
                    "priority_factor_score": 1.25,
                    "score_state": "known",
                    "technical_base_severity": "critical",
                    "technical_severity_source": "rule",
                    "explanation": ["Public explanation.", {"private": sentinel}],
                    "operator_debug": {"url": sentinel},
                },
                "evidence_refs": ["evidence:1", {"private": sentinel}],
                "verification_steps": ["Confirm the fix.", {"private": sentinel}],
                "dependency": {"private": sentinel},
                "vendor_owner": [sentinel],
            }
        ],
        user_agent="FixListBot/1.0",
        suppressed_findings=[{"private": sentinel}],
        operator_authorized=False,
    )

    assert handoff["scan"] == {
        "scan_id": "scan-a",
        "scan_run_id": "scan-a",
        "normalized_domain": "example.com",
        "scan_origin": "https://example.com",
        "evidence_url_identity_version": "published_url_identity_v1",
    }
    fix = handoff["fixes"][0]
    assert fix["rule_id"] is None
    assert fix["title"] is None
    assert fix["root_cause_id"] is None
    assert fix["url_provenance"] == {
        "published_url": None,
        "request_url": None,
        "final_url": "https://example.com/product",
    }
    assert fix["dependency"] is None
    assert fix["vendor_owner"] is None
    assert fix["family_ids"] == ["family:product"]
    assert fix["evidence_refs"] == ["evidence:1"]
    assert fix["verification_steps"] == ["Confirm the fix."]
    assert fix["priority_factors"]["impact"] == 5
    assert fix["priority_factors"]["reach"] == 0.25
    assert fix["priority_factors"]["explanation"] == ["Public explanation."]
    assert "operator_debug" not in fix["priority_factors"]
    assert "suppressed_findings" not in handoff

    serialized = json.dumps(handoff, sort_keys=True)
    assert sentinel not in serialized
    assert "operator_debug" not in serialized


def test_b24_customer_handoff_rejects_malformed_priority_factor_values_without_coercion():
    handoff = build_handoff_v2(
        scan_identity={"scan_id": "scan-a"},
        fixes=[
            {
                "rule_id": "broken-page",
                "title": "Broken page",
                "affected_pages": ["https://example.com/broken"],
                "priority_factors": {
                    "version": "repair_priority_v3_four_factor_v1",
                    "impact": "5",
                    "reach": "0.5",
                    "page_value": float("nan"),
                    "confidence": True,
                    "priority_factor_score": float("inf"),
                    "reach_affected_indexable": 1.5,
                    "reach_observed_indexable_family": "2",
                    "explanation": "not-a-list",
                },
            }
        ],
        user_agent="FixListBot/1.0",
    )

    factors = handoff["fixes"][0]["priority_factors"]
    assert factors["version"] == "repair_priority_v3_four_factor_v1"
    assert factors["impact"] is None
    assert factors["reach"] is None
    assert factors["page_value"] is None
    assert factors["confidence"] is None
    assert factors["priority_factor_score"] is None
    assert factors["reach_affected_indexable"] is None
    assert factors["reach_observed_indexable_family"] is None
    assert factors["explanation"] == []
