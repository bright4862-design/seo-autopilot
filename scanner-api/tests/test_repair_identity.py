from app.repair_identity import build_repair_identity, compare_repair_runs


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


def page(url):
    return {"url": url, "status_code": 200, "content_type": "text/html"}


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


def test_missing_repair_is_verified_only_when_all_previous_pages_are_rechecked():
    previous = stable_fix()
    result = compare_repair_runs(previous, [], [page("/a"), page("/b"), page("/other")])
    assert result["state"] == "verified_fixed"
    assert result["rechecked_pages"] == 2


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
