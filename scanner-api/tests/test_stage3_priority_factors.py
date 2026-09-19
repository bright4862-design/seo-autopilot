from app.stage3_priority_factors import (
    FOUR_FACTOR_PRIORITY_VERSION,
    GSC_PAGE_VALUE_EVIDENCE_VERSION,
    annotate_four_factor_priority,
    build_four_factor_priority,
)


def page(url, *, family="product_page", indexable=True, role=None, intent=None):
    value = {
        "url": url,
        "status_code": 200,
        "content_type": "text/html",
        "page_template_family": family,
        "indexable": indexable,
    }
    if role is not None:
        value["page_value_role"] = role
    if intent is not None:
        value["page_intent"] = intent
    return value


def verified_fix(**overrides):
    value = {
        "rule": "missing_meta_description",
        "category": "meta_description",
        "base_severity": "medium",
        "verification_state": "verified",
        "evidence_status": "confirmed",
        "affected_pages": ["/products/a"],
        "page_template_family": "product_page",
        "action_priority": "important",
        "action_priority_score": 2200,
    }
    value.update(overrides)
    return value


def test_four_factor_contract_preserves_existing_review_priority_fields():
    fix = verified_fix()
    result = annotate_four_factor_priority(fix, [page("/products/a")])
    factors = result["stage3_priority_factors"]

    assert factors["version"] == FOUR_FACTOR_PRIORITY_VERSION
    assert factors["impact"] == 2
    assert factors["reach"] == 1.0
    assert factors["page_value"] == 1.0
    assert factors["confidence"] == 1.0
    assert factors["priority_factor_score"] == 2.0
    assert result["base_severity"] == "medium"
    assert result["action_priority"] == "important"
    assert result["action_priority_score"] == 2200
    assert any("does not overwrite canonical Review ranking" in line for line in factors["explanation"])


def test_unknown_family_denominator_is_unknown_not_zero():
    fix = verified_fix(
        rule="broken_page",
        category="404_error",
        base_severity="high",
        affected_pages=["/a", "/b"],
        page_template_family="mixed",
    )
    factors = build_four_factor_priority(
        fix,
        [page("/a", family="standard"), page("/b", family="product_page")],
    )

    assert factors["impact"] == 5
    assert factors["reach"] is None
    assert factors["reach_state"] == "unknown"
    assert factors["priority_factor_score"] is None
    assert factors["score_state"] == "unknown"
    assert any("Reach unknown" in line for line in factors["explanation"])


def test_observed_non_indexable_affected_page_has_known_zero_reach():
    fix = verified_fix(
        affected_pages=["/products/noindex"],
        page_template_family="product_page",
    )
    factors = build_four_factor_priority(
        fix,
        [
            page("/products/noindex", indexable=False),
            page("/products/indexable", indexable=True),
        ],
    )

    assert factors["reach"] == 0.0
    assert factors["reach_state"] == "known"
    assert factors["reach_affected_indexable"] == 0
    assert factors["reach_observed_indexable_family"] == 1
    assert factors["priority_factor_score"] == 0.0
    assert not any("Reach unknown" in line for line in factors["explanation"])


def test_high_impact_commercial_leaf_stays_ahead_of_low_impact_structural_page():
    high_leaf = verified_fix(
        rule="broken_page",
        category="404_error",
        base_severity="high",
        affected_pages=["/products/a"],
        page_template_family="product_page",
    )
    low_structural = verified_fix(
        rule="title_over_pixel_limit",
        category="title_length",
        base_severity="low",
        affected_pages=["/"],
        page_template_family="homepage",
    )
    pages = [page("/products/a"), page("/", family="homepage", role="hub")]

    high_factors = build_four_factor_priority(high_leaf, pages)
    low_factors = build_four_factor_priority(low_structural, pages)

    assert high_factors["technical_base_severity"] == "high"
    assert low_factors["technical_base_severity"] == "low"
    assert high_factors["priority_factor_score"] > low_factors["priority_factor_score"]


def test_repeated_commercial_leaves_saturate_instead_of_summing_page_value():
    single = verified_fix(affected_pages=["/products/0"])
    repeated = verified_fix(affected_pages=[f"/products/{i}" for i in range(50)])
    single_pages = [page("/products/0")]
    repeated_pages = [page(f"/products/{i}") for i in range(50)]

    one = build_four_factor_priority(single, single_pages)
    many = build_four_factor_priority(repeated, repeated_pages)

    assert one["reach"] == 1.0
    assert many["reach"] == 1.0
    assert one["page_value"] == 1.0
    assert many["page_value"] == 1.0
    assert one["priority_factor_score"] == many["priority_factor_score"]


def test_canonical_gap_rises_only_with_verified_live_duplicate_evidence():
    base = verified_fix(
        rule="canonical_missing",
        category="canonical",
        affected_pages=["/products/a"],
    )
    without_duplicate = build_four_factor_priority(base, [page("/products/a")])
    with_duplicate = build_four_factor_priority(
        {**base, "verified_live_duplicate_routes": ["/products/a?variant=1"]},
        [page("/products/a")],
    )
    heuristic_duplicate = build_four_factor_priority(
        {
            **base,
            "verification_state": "heuristic",
            "evidence_status": "provisional",
            "verified_live_duplicate_routes": ["/products/a?variant=1"],
        },
        [page("/products/a")],
    )

    assert without_duplicate["impact"] == 2
    assert with_duplicate["impact"] == 3
    assert heuristic_duplicate["impact"] == 2


def test_verified_noindex_money_page_has_blueprint_impact_five():
    fix = verified_fix(
        rule="noindex_money_page",
        category="indexability",
        affected_pages=["/apply"],
        page_template_family="conversion",
    )
    factors = build_four_factor_priority(
        fix,
        [page("/apply", family="conversion", role="money")],
    )
    assert factors["impact"] == 5
    assert "money page" in factors["impact_reason"]


def test_gsc_can_affect_page_value_only_with_current_verified_envelope():
    fix = verified_fix(
        affected_pages=["/help"],
        page_template_family="help",
        gsc_priority_evidence={
            "version": GSC_PAGE_VALUE_EVIDENCE_VERSION,
            "provider": "gsc",
            "state": "disconnected",
            "freshness_state": "current",
            "normalized_page_value": 0.7,
        },
    )
    pages = [page("/help", family="help", role="utility")]
    disconnected = build_four_factor_priority(fix, pages)
    connected = build_four_factor_priority(
        {
            **fix,
            "gsc_priority_evidence": {
                "version": GSC_PAGE_VALUE_EVIDENCE_VERSION,
                "provider": "gsc",
                "state": "connected_valid",
                "freshness_state": "current",
                "normalized_page_value": 0.7,
            },
        },
        pages,
    )

    assert disconnected["page_value"] == 0.1
    assert disconnected["page_value_source"] == "base_role"
    assert connected["page_value"] == 0.7
    assert connected["page_value_source"] == "base_role+gsc_verified"


def test_confidence_uses_verified_heuristic_unverified_blueprint_values():
    pages = [page("/products/a")]
    verified = build_four_factor_priority(verified_fix(), pages)
    heuristic = build_four_factor_priority(
        verified_fix(verification_state="heuristic", evidence_status="provisional"), pages
    )
    unverified = build_four_factor_priority(
        verified_fix(verification_state="not_verified", evidence_status="unknown"), pages
    )

    assert verified["confidence"] == 1.0
    assert heuristic["confidence"] == 0.7
    assert unverified["confidence"] == 0.4


def test_conflicting_verified_and_unknown_markers_fail_closed_to_unverified():
    factors = build_four_factor_priority(
        verified_fix(verification_state="verified", evidence_status="unknown"),
        [page("/products/a")],
    )
    assert factors["confidence_state"] == "unverified"
    assert factors["confidence"] == 0.4
