from app.stage3_priority_factors import (
    GSC_PAGE_VALUE_EVIDENCE_VERSION,
    build_four_factor_priority,
)


def _page(url: str, *, family: str = "help", role: str = "utility") -> dict:
    return {
        "url": url,
        "status_code": 200,
        "content_type": "text/html",
        "page_template_family": family,
        "page_value_role": role,
        "indexable": True,
    }


def _fix(**overrides) -> dict:
    value = {
        "rule": "missing_meta_description",
        "category": "meta_description",
        "base_severity": "medium",
        "affected_pages": ["/help"],
        "page_template_family": "help",
    }
    value.update(overrides)
    return value


def test_b19_numeric_string_confidence_cannot_manufacture_verified_evidence():
    factors = build_four_factor_priority(
        _fix(confidence_score="95"),
        [_page("/help")],
    )

    assert factors["confidence_state"] == "unverified"
    assert factors["confidence"] == 0.4
    assert factors["priority_factor_score"] == 0.08


def test_b19_string_gsc_page_value_cannot_boost_page_value():
    factors = build_four_factor_priority(
        _fix(
            verification_state="verified",
            evidence_status="confirmed",
            gsc_priority_evidence={
                "version": GSC_PAGE_VALUE_EVIDENCE_VERSION,
                "provider": "gsc",
                "state": "connected_valid",
                "freshness_state": "current",
                "normalized_page_value": "0.9",
            },
        ),
        [_page("/help")],
    )

    assert factors["page_value"] == 0.1
    assert factors["page_value_source"] == "base_role"
    assert factors["priority_factor_score"] == 0.2


def test_b19_boolean_gsc_page_value_cannot_boost_page_value():
    factors = build_four_factor_priority(
        _fix(
            verification_state="verified",
            evidence_status="confirmed",
            gsc_priority_evidence={
                "version": GSC_PAGE_VALUE_EVIDENCE_VERSION,
                "provider": "gsc",
                "state": "connected_valid",
                "freshness_state": "current",
                "normalized_page_value": True,
            },
        ),
        [_page("/help")],
    )

    assert factors["page_value"] == 0.1
    assert factors["page_value_source"] == "base_role"
    assert factors["priority_factor_score"] == 0.2
