from app.repair_contract_v2 import _build_stage3_health_score_decision


def _decision(review):
    decision = _build_stage3_health_score_decision(review, [])
    assert decision is not None
    return decision


def test_b23_structured_authoritative_coverage_state_fails_closed_to_unknown():
    sentinel = "https://private.invalid/operator-debug"
    review = {
        "health_score": 88,
        "coverage_state": "sufficient",
        "site_fingerprint": {
            "coverage_assessment": {
                "state": {"operator_debug_url": sentinel},
            }
        },
    }

    decision = _decision(review)

    assert decision["coverage_state"] == "unknown"
    assert sentinel not in repr(decision)


def test_b23_list_authoritative_coverage_state_fails_closed_to_unknown():
    sentinel = "PRIVATE_COVERAGE_DEBUG_SENTINEL"
    review = {
        "health_score": 88,
        "site_fingerprint": {
            "coverage_assessment": {
                "state": ["sufficient", sentinel],
            }
        },
    }

    decision = _decision(review)

    assert decision["coverage_state"] == "unknown"
    assert sentinel not in repr(decision)


def test_b23_missing_authoritative_state_preserves_valid_review_coverage_state():
    review = {
        "health_score": 88,
        "coverage_state": "limited_coverage",
        "site_fingerprint": {"coverage_assessment": {}},
    }

    decision = _decision(review)

    assert decision["coverage_state"] == "limited_coverage"
