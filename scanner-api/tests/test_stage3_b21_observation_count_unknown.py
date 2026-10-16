from app.stage3_delivery import build_handoff_v2, summarize_candidate_counts


def test_b21_malformed_explicit_observation_count_without_observations_stays_unknown():
    counts = summarize_candidate_counts(
        {
            "affected_pages": ["https://example.com/a"],
            "observation_count": "4",
        }
    )

    assert counts["observation_count"] is None


def test_b24_handoff_does_not_turn_malformed_observation_count_into_zero():
    handoff = build_handoff_v2(
        scan_identity={"scan_id": "scan-1", "scan_run_id": "scan-1"},
        fixes=[
            {
                "rule_id": "rule-1",
                "title": "Fix one thing",
                "affected_pages": ["https://example.com/a"],
                "observation_count": {"operator_debug": "PRIVATE_SENTINEL"},
            }
        ],
        user_agent="FixList",
    )

    assert handoff["fixes"][0]["counts"]["observations"] is None
    assert "PRIVATE_SENTINEL" not in repr(handoff)


def test_b21_real_observation_list_can_supply_count_when_explicit_count_is_invalid():
    counts = summarize_candidate_counts(
        {
            "affected_pages": ["https://example.com/a"],
            "observation_count": "invalid",
            "observations": [
                {"observed_url": "https://example.com/a"},
                {"observed_url": "https://example.com/b"},
            ],
        }
    )

    assert counts["observation_count"] == 2
