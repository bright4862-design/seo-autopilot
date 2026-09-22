from app.nextgen_fix_verification import (
    PASS,
    PARTIAL,
    FAIL,
    COULD_NOT_VERIFY,
    MAX_RECHECK_URLS,
    build_acceptance_criterion,
    build_targeted_recheck_plan,
    evaluate_verification_plan,
    regression_reopen_decision,
    verified_fixed_transition_allowed,
)
from app.repair_coverage import PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION

ORIGIN = "https://example.com"


def fix(**overrides):
    base = {
        "rule": "missing_meta_description",
        "category": "meta_description",
        "repair_surface": "product_template",
        "remediation_family": "add_meta_description",
        "affected_pages": ["/a", "/b"],
        "rule_definition_version": "missing_meta_description_v3",
        "comparison_profile_version": "standard150_review_v2",
        "evidence_url_identity_version": PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION,
    }
    base.update(overrides)
    return base


def contract(**overrides):
    base = {
        "rule_definition_version": "missing_meta_description_v3",
        "comparison_profile_version": "standard150_review_v2",
        "evidence_url_identity_version": PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION,
    }
    base.update(overrides)
    return base


def pages(*urls, **extra):
    return [
        {"url": url, "status_code": 200, "content_type": "text/html", "indexable": True, **extra}
        for url in urls
    ]


def evaluations(plan, detected_states):
    rows = []
    for request, detected in zip(plan["requests"], detected_states):
        rows.append({
            "url": request["url"],
            "evidence_key": request["evidence_key"],
            "criterion_id": plan["criterion_id"],
            "repair_fingerprint": plan["repair_fingerprint"],
            "rule_definition_version": plan["rule_definition_version"],
            "comparison_profile_version": plan["comparison_profile_version"],
            "evidence_url_identity_version": plan["evidence_url_identity_version"],
            "evaluated": True,
            "defect_detected": detected,
        })
    return rows


def test_criterion_is_deterministic_and_versioned():
    first = build_acceptance_criterion(fix())
    second = build_acceptance_criterion(fix())
    assert first["state"] == "ready"
    assert first["criterion_id"] == second["criterion_id"]
    assert first["predicate_contract"]["requires_actual_re_evaluation"] is True


def test_missing_identity_or_versions_block_new_plan():
    plan = build_targeted_recheck_plan(
        fix(repair_surface="", rule_definition_version=""),
        previous_scan_origin=ORIGIN,
    )
    assert plan["state"] == "blocked"
    assert "stable_repair_identity_required" in plan["blockers"]
    assert "rule_definition_version_required" in plan["blockers"]


def test_plan_is_bounded_and_incomplete_population_cannot_pass():
    many = [f"/p/{index}" for index in range(MAX_RECHECK_URLS + 10)]
    previous = fix(affected_pages=many)
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN, max_urls=999)
    assert plan["state"] == "bounded_incomplete"
    assert len(plan["requests"]) == MAX_RECHECK_URLS
    assert plan["omitted_population_count"] == 10
    result = evaluate_verification_plan(
        plan,
        previous,
        pages(*many),
        [],
        contract(),
        scan_origin=ORIGIN,
    )
    assert result["state"] == COULD_NOT_VERIFY


def test_pass_requires_every_page_and_explicit_predicate_re_evaluation():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    result = evaluate_verification_plan(
        plan,
        previous,
        pages("/a", "/b"),
        evaluations(plan, [False, False]),
        contract(),
        scan_origin=ORIGIN,
    )
    assert result["state"] == PASS
    assert result["evaluated_population_count"] == 2


def test_disappeared_url_is_never_proof_of_fix():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    result = evaluate_verification_plan(
        plan,
        previous,
        pages("/a"),
        evaluations(plan, [False, False]),
        contract(),
        scan_origin=ORIGIN,
    )
    assert result["state"] == COULD_NOT_VERIFY
    assert any(item["reason"] == "required_page_not_observed" for item in result["unverifiable_scope"])


def test_still_detected_is_fail():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    result = evaluate_verification_plan(
        plan,
        previous,
        pages("/a", "/b"),
        evaluations(plan, [True, True]),
        contract(),
        scan_origin=ORIGIN,
    )
    assert result["state"] == FAIL
    assert len(result["unresolved_scope"]) == 2


def test_partial_retains_exact_unresolved_scope():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    result = evaluate_verification_plan(
        plan,
        previous,
        pages("/a", "/b"),
        evaluations(plan, [False, True]),
        contract(),
        scan_origin=ORIGIN,
    )
    assert result["state"] == PARTIAL
    assert result["resolved_scope"] == ["https://example.com/a"]
    assert result["unresolved_scope"] == ["https://example.com/b"]


def test_ineligible_404_cannot_verify_even_if_predicate_says_resolved():
    previous = fix(affected_pages=["/a"])
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    current_pages = [{"url": "/a", "status_code": 404, "content_type": "text/html", "indexable": True}]
    result = evaluate_verification_plan(
        plan,
        previous,
        current_pages,
        evaluations(plan, [False]),
        contract(),
        scan_origin=ORIGIN,
    )
    assert result["state"] == COULD_NOT_VERIFY
    assert "HTTP 404" in result["unverifiable_scope"][0]["reason"]


def test_nonindex_search_page_cannot_verify_even_if_predicate_says_resolved():
    previous = fix(affected_pages=["/a"])
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    current_pages = [{"url": "/a", "status_code": 200, "content_type": "text/html", "indexable": False}]
    result = evaluate_verification_plan(
        plan,
        previous,
        current_pages,
        evaluations(plan, [False]),
        contract(),
        scan_origin=ORIGIN,
    )
    assert result["state"] == COULD_NOT_VERIFY
    assert "non-indexable" in result["unverifiable_scope"][0]["reason"]


def test_changed_rule_version_fails_closed():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    result = evaluate_verification_plan(
        plan,
        previous,
        pages("/a", "/b"),
        evaluations(plan, [False, False]),
        contract(rule_definition_version="missing_meta_description_v4"),
        scan_origin=ORIGIN,
    )
    assert result["state"] == COULD_NOT_VERIFY


def test_ambiguous_duplicate_rule_evaluation_fails_closed():
    previous = fix(affected_pages=["/a"])
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    rows = evaluations(plan, [False])
    rows.append(dict(rows[0]))
    result = evaluate_verification_plan(
        plan,
        previous,
        pages("/a"),
        rows,
        contract(),
        scan_origin=ORIGIN,
    )
    assert result["state"] == COULD_NOT_VERIFY
    assert result["unverifiable_scope"][0]["reason"] == "ambiguous_duplicate_rule_evaluation"


def test_verified_fixed_gate_is_conjunctive_not_replaced():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    result = evaluate_verification_plan(
        plan,
        previous,
        pages("/a", "/b"),
        evaluations(plan, [False, False]),
        contract(),
        scan_origin=ORIGIN,
    )
    assert verified_fixed_transition_allowed(result, {"state": "verified_fixed"}) is True
    assert verified_fixed_transition_allowed(result, {"state": "could_not_verify"}) is False


def test_regression_reopens_only_on_proven_fail_or_partial():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    current = evaluate_verification_plan(
        plan,
        previous,
        pages("/a", "/b"),
        evaluations(plan, [False, True]),
        contract(),
        scan_origin=ORIGIN,
    )
    decision = regression_reopen_decision(
        {"repair_fingerprint": plan["repair_fingerprint"], "verification_state": "verified_fixed"},
        current,
    )
    assert decision["should_reopen"] is True
    assert decision["reopen_scope"] == ["https://example.com/b"]


def test_could_not_verify_never_reopens_by_itself():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    current = evaluate_verification_plan(
        plan,
        previous,
        pages("/a"),
        evaluations(plan, [False, False]),
        contract(),
        scan_origin=ORIGIN,
    )
    decision = regression_reopen_decision(
        {"repair_fingerprint": plan["repair_fingerprint"], "verification_state": "verified_fixed"},
        current,
    )
    assert current["state"] == COULD_NOT_VERIFY
    assert decision["should_reopen"] is False


def test_tampered_plan_cannot_drop_historical_population_member():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    plan["requests"] = plan["requests"][:1]
    result = evaluate_verification_plan(
        plan,
        previous,
        pages("/a", "/b"),
        evaluations(plan, [False]),
        contract(),
        scan_origin=ORIGIN,
    )
    assert result["state"] == COULD_NOT_VERIFY
    assert "complete historical evidence population" in result["reason"]


def test_invalid_population_count_fails_closed_without_exception():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    plan["population_count"] = "not-an-int"
    result = evaluate_verification_plan(
        plan,
        previous,
        pages("/a", "/b"),
        evaluations(plan, [False, False]),
        contract(),
        scan_origin=ORIGIN,
    )
    assert result["state"] == COULD_NOT_VERIFY
    assert result["required_population_count"] == 0


def test_tampered_criterion_identity_fails_closed():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    plan["criterion"] = {**plan["criterion"], "criterion_id": "tampered"}
    result = evaluate_verification_plan(
        plan,
        previous,
        pages("/a", "/b"),
        evaluations(plan, [False, False]),
        contract(),
        scan_origin=ORIGIN,
    )
    assert result["state"] == COULD_NOT_VERIFY
    assert "historical repair contract" in result["reason"]


def test_recheck_request_url_must_match_declared_evidence_key():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    plan["requests"][0] = {**plan["requests"][0], "url": "/different"}
    result = evaluate_verification_plan(
        plan,
        previous,
        pages("/a", "/b"),
        evaluations(plan, [False, False]),
        contract(),
        scan_origin=ORIGIN,
    )
    assert result["state"] == COULD_NOT_VERIFY
    assert "declared evidence identity" in result["reason"]
