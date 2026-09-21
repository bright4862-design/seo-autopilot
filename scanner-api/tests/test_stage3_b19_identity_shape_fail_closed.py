from app.stage3_priority_factors import build_four_factor_priority


def _page(url):
    return {
        "url": url,
        "status_code": 200,
        "content_type": "text/html",
        "page_template_family": "product_page",
        "indexable": True,
    }


def _verified_fix(affected):
    return {
        "rule": "missing_meta_description",
        "category": "meta_description",
        "base_severity": "medium",
        "verification_state": "verified",
        "evidence_status": "confirmed",
        "affected_pages": [affected],
        "page_template_family": "product_page",
    }


def test_structured_page_identity_cannot_establish_b19_reach():
    malformed_identity = {"private_debug": "https://internal.invalid/secret"}

    factors = build_four_factor_priority(
        _verified_fix(malformed_identity),
        [_page(malformed_identity)],
    )

    assert factors["reach"] is None
    assert factors["reach_state"] == "unknown"
    assert factors["priority_factor_score"] is None


def test_sequence_page_identity_cannot_establish_b19_reach():
    malformed_identity = ["https://internal.invalid/secret"]

    factors = build_four_factor_priority(
        _verified_fix(malformed_identity),
        [_page(malformed_identity)],
    )

    assert factors["reach"] is None
    assert factors["reach_state"] == "unknown"
    assert factors["priority_factor_score"] is None


def test_literal_string_page_identity_still_establishes_known_reach():
    factors = build_four_factor_priority(
        _verified_fix("/products/a"),
        [_page("/products/a")],
    )

    assert factors["reach"] == 1.0
    assert factors["reach_state"] == "known"
    assert factors["priority_factor_score"] == 2.0
