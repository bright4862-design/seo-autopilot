from app.repair_identity import build_repair_identity, compare_repair_runs


def stable_fix(**overrides):
    base = {
        "rule_id": "missing_meta_description",
        "rule": "Missing meta description",
        "category": "meta_description",
        "page_scope": "family",
        "page_template_family": "product_page",
        "repair_surface": "product_template",
        "remediation_family": "add_meta_description",
        "affected_pages": ["/products/a"],
    }
    base.update(overrides)
    return base


def page(url):
    return {
        "url": url,
        "status_code": 200,
        "content_type": "text/html",
        "indexable": True,
    }


def test_stable_fingerprint_ignores_mutable_category_and_page_family():
    before = build_repair_identity(stable_fix())
    after = build_repair_identity(
        stable_fix(
            category="on_page",
            page_scope="page",
            page_template_family="standard",
        )
    )

    assert before["stable"] is True
    assert after["stable"] is True
    assert before["fingerprint"] == after["fingerprint"]


def test_stable_fingerprint_changes_when_technical_repair_surface_changes():
    before = build_repair_identity(stable_fix())
    after = build_repair_identity(stable_fix(repair_surface="cms_page_editor"))
    assert before["fingerprint"] != after["fingerprint"]


def test_stable_fingerprint_changes_when_remediation_family_changes():
    before = build_repair_identity(stable_fix())
    after = build_repair_identity(stable_fix(remediation_family="generate_description_from_product_data"))
    assert before["fingerprint"] != after["fingerprint"]


def test_classification_drift_cannot_make_existing_defect_look_fixed():
    previous = stable_fix()
    current = stable_fix(
        category="on_page",
        page_scope="page",
        page_template_family="standard",
    )

    result = compare_repair_runs(previous, [current], [page("/products/a")])
    assert result["state"] == "still_detected"


def test_human_rule_copy_change_does_not_override_canonical_rule_id():
    before = build_repair_identity(stable_fix(rule="Missing meta description"))
    after = build_repair_identity(stable_fix(rule="Add a useful meta description"))
    assert before["fingerprint"] == after["fingerprint"]
