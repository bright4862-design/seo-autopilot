from app.stage3_delivery import build_handoff_v2, select_evidence_led_preview


def test_b22_preview_does_not_promote_out_of_range_impact_as_high_impact():
    result = select_evidence_led_preview(
        [
            {
                "rule_id": "invalid-impact",
                "title": "Malformed factor",
                "impact": 99,
                "priority_score": 99.0,
                "preview_allowed": True,
                "evidence_state": "verified",
            },
            {
                "rule_id": "valid-impact",
                "title": "Valid factor",
                "impact": 3,
                "priority_score": 1.0,
                "preview_allowed": True,
                "evidence_state": "verified",
            },
        ],
        max_items=2,
    )

    assert result["state"] == "findings"
    assert [item["rule_id"] for item in result["findings"]] == ["valid-impact"]
    assert result["findings"][0]["impact"] == 3


def test_b24_handoff_projects_out_of_range_b19_factors_as_unknown():
    payload = build_handoff_v2(
        scan_identity={"scan_id": "scan-1", "scan_run_id": "scan-1"},
        fixes=[
            {
                "rule_id": "broken-page",
                "title": "Broken page",
                "priority_factors": {
                    "version": "repair_priority_v3_four_factor_v1",
                    "impact": 99,
                    "reach": 1.5,
                    "page_value": -0.1,
                    "confidence": 2.0,
                    "priority_factor_score": 42.0,
                },
            }
        ],
        user_agent="FixListBot/1.0",
    )

    factors = payload["fixes"][0]["priority_factors"]
    assert factors["impact"] is None
    assert factors["reach"] is None
    assert factors["page_value"] is None
    assert factors["confidence"] is None
    assert factors["priority_factor_score"] is None


def test_b24_handoff_preserves_valid_b19_factor_boundaries():
    payload = build_handoff_v2(
        scan_identity={"scan_id": "scan-1", "scan_run_id": "scan-1"},
        fixes=[
            {
                "rule_id": "broken-page",
                "title": "Broken page",
                "priority_factors": {
                    "version": "repair_priority_v3_four_factor_v1",
                    "impact": 5,
                    "reach": 1.0,
                    "page_value": 1.0,
                    "confidence": 1.0,
                    "priority_factor_score": 5.0,
                },
            }
        ],
        user_agent="FixListBot/1.0",
    )

    factors = payload["fixes"][0]["priority_factors"]
    assert factors["impact"] == 5
    assert factors["reach"] == 1.0
    assert factors["page_value"] == 1.0
    assert factors["confidence"] == 1.0
    assert factors["priority_factor_score"] == 5.0
