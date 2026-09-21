from app.stage3_delivery import build_handoff_v2, summarize_candidate_counts


def _candidate(**overrides):
    value = {
        "rule_id": "missing_meta_description",
        "title": "Missing meta description",
        "affected_pages": ["/a", "/b"],
        "observation_count": 2,
        "known_population_count": 2,
        "priority_factors": {
            "version": "repair_priority_v3_four_factor_v1",
            "impact": 2,
            "reach": 1.0,
            "page_value": 1.0,
            "confidence": 1.0,
            "priority_factor_score": 2.0,
        },
    }
    value.update(overrides)
    return value


def test_known_population_smaller_than_unique_affected_union_fails_closed():
    counts = summarize_candidate_counts(
        _candidate(known_population_count=1),
        sample_limit=10,
    )

    assert counts["unique_affected_page_count"] == 2
    assert counts["known_population_count"] is None


def test_impossible_population_is_not_signed_into_customer_handoff():
    payload = build_handoff_v2(
        scan_identity={"scan_id": "scan-1", "scan_run_id": "scan-1"},
        fixes=[_candidate(known_population_count=1)],
        user_agent="FixListBot/1.0",
    )

    assert payload["fixes"][0]["counts"]["unique_affected_pages"] == 2
    assert payload["fixes"][0]["counts"]["known_population"] is None


def test_equal_known_population_remains_known():
    counts = summarize_candidate_counts(_candidate(), sample_limit=10)

    assert counts["unique_affected_page_count"] == 2
    assert counts["known_population_count"] == 2
