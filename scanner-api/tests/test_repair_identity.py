from app.repair_identity import build_repair_identity, compare_repair_runs, verification_eligibility


def stable_fix(**overrides):
    base = {
        "rule": "internal_link_redirect",
        "category": "internal_link",
        "page_scope": "family",
        "page_template_family": "navigation",
        "repair_surface": "shared_navigation",
        "remediation_family": "point_links_directly_to_final_url",
        "affected_pages": ["/a", "/b"],
    }
    base.update(overrides)
    return base


def page(url, **overrides):
    value = {"url": url, "status_code": 200, "content_type": "text/html"}
    value.update(overrides)
    return value


def search_fix(**overrides):
    base = stable_fix(
        rule="missing_meta_description",
        category="meta_description",
        page_template_family="product_page",
        repair_surface="product_template",
        remediation_family="add_meta_description",
        affected_pages=["/products/a"],
    )
    base.update(overrides)
    return base


def test_family_and_recommendation_copy_alone_are_not_stable_identity():
    identity = build_repair_identity({
        "rule": "missing_h1",
        "category": "thin_content",
        "page_template_family": "product_page",
        "recommended_value": "Add one H1 to the product template.",
        "affected_pages": ["/products/a", "/products/b"],
    })
    assert identity["state"] == "provisional"
    assert identity["stable"] is False
    assert identity["fingerprint"]


def test_explicit_surface_and_remediation_family_create_stable_identity():
    identity = build_repair_identity(stable_fix())
    assert identity["state"] == "stable"
    assert identity["stable"] is True
    assert len(identity["fingerprint"]) == 24


def test_stable_identity_does_not_change_when_affected_page_count_changes():
    first = build_repair_identity(stable_fix(affected_pages=["/a", "/b"]))
    second = build_repair_identity(stable_fix(affected_pages=["/a", "/b", "/c", "/d"]))
    assert first["fingerprint"] == second["fingerprint"]


def test_matching_repair_is_still_detected():
    previous = stable_fix()
    current = stable_fix(affected_pages=["/b"])
    result = compare_repair_runs(previous, [current], [page("/a"), page("/b")])
    assert result["state"] == "still_detected"


def test_previously_verified_repair_with_same_fingerprint_came_back():
    previous = stable_fix(verification_state="verified_fixed")
    current = stable_fix(affected_pages=["/a"])
    result = compare_repair_runs(previous, [current], [page("/a"), page("/b")])
    assert result["state"] == "came_back"


def test_missing_repair_is_verified_only_when_all_previous_pages_are_rechecked_and_eligible():
    previous = stable_fix()
    result = compare_repair_runs(previous, [], [page("/a"), page("/b"), page("/other")])
    assert result["state"] == "verified_fixed"
    assert result["rechecked_pages"] == 2
    assert result["eligible_rechecked_pages"] == 2


def test_missing_page_is_not_false_proof_of_fix():
    previous = stable_fix()
    result = compare_repair_runs(previous, [], [page("/a")])
    assert result["state"] == "could_not_verify"
    assert result["rechecked_pages"] == 1
    assert result["previous_affected_pages"] == 2


def test_provisional_identity_can_never_auto_verify_fixed():
    previous = {
        "rule": "missing_meta_description",
        "category": "meta_description",
        "page_template_family": "product_page",
        "recommended_value": "Add descriptions.",
        "affected_pages": ["/products/a"],
    }
    result = compare_repair_runs(previous, [], [page("/products/a")])
    assert result["state"] == "could_not_verify"
    assert "stable repair identity" in result["reason"].lower()


def test_search_facing_repair_does_not_verify_when_page_becomes_noindex():
    previous = search_fix()
    result = compare_repair_runs(previous, [], [page("/products/a", indexable=False)])
    assert result["state"] == "could_not_verify"
    assert result["eligible_rechecked_pages"] == 0
    assert result["non_comparable_pages"][0]["state"] == "ineligible"
    assert "non-indexable" in result["non_comparable_pages"][0]["reason"].lower()


def test_search_facing_repair_does_not_verify_when_page_becomes_redirect():
    previous = search_fix()
    result = compare_repair_runs(previous, [], [page("/products/a", status_code=301)])
    assert result["state"] == "could_not_verify"
    assert "http 301" in result["non_comparable_pages"][0]["reason"].lower()


def test_search_facing_repair_does_not_verify_when_page_becomes_error():
    previous = search_fix()
    result = compare_repair_runs(previous, [], [page("/products/a", status_code=404)])
    assert result["state"] == "could_not_verify"
    assert "http 404" in result["non_comparable_pages"][0]["reason"].lower()


def test_search_facing_repair_does_not_verify_when_access_is_blocked():
    previous = search_fix()
    result = compare_repair_runs(
        previous,
        [],
        [page("/products/a", status_code=403, page_evidence_class="failed_access")],
    )
    assert result["state"] == "could_not_verify"
    assert "failed_access" in result["non_comparable_pages"][0]["reason"].lower()


def test_non_html_page_is_not_comparable_repair_evidence():
    previous = stable_fix(affected_pages=["/a"])
    result = compare_repair_runs(previous, [], [page("/a", content_type="application/pdf")])
    assert result["state"] == "could_not_verify"
    assert "html" in result["non_comparable_pages"][0]["reason"].lower()


def test_unknown_indexability_remains_compatible_for_historical_scans():
    previous = search_fix()
    state, reason = verification_eligibility(previous, page("/products/a"))
    assert state == "eligible"
    assert "comparable" in reason.lower()


def test_different_query_variant_is_not_treated_as_rechecked_evidence():
    previous = search_fix(affected_pages=["/products/a?variant=red"])
    result = compare_repair_runs(previous, [], [page("/products/a?variant=blue")])
    assert result["state"] == "could_not_verify"
    assert result["rechecked_pages"] == 0


def test_same_query_variant_can_be_verified_when_still_eligible():
    previous = search_fix(affected_pages=["/products/a?variant=red"])
    result = compare_repair_runs(previous, [], [page("/products/a?variant=red", indexable=True)])
    assert result["state"] == "verified_fixed"
    assert result["eligible_rechecked_pages"] == 1
