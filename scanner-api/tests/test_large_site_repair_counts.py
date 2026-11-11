from app.repair_contract_v2 import _merge_repair_group, _normalize_canonical_repair_evidence, apply_canonical_repair_contract
from app.repair_coverage import PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION, first_failed_repair_invariant, normalize_repair_scope
from app.review import build_page_pattern_findings, build_site_fingerprint, get_playbook, prepare_fixes


def pages(count=500):
    return [{
        "url": f"https://example.com/products/item-{i}",
        "final_url": f"https://example.com/products/item-{i}",
        "status_code": 200, "content_type": "text/html", "page_evidence_class": "usable_html",
        "page_template_family": "product_page", "indexable": True,
        "title": f"Product {i}", "h1": f"Product {i}", "h1_count": 1,
        "meta_description": "", "meta_description_state": "missing",
        "canonical": f"https://example.com/products/item-{i}",
        "schema_types": ["Product"], "importance_score": i / 500,
    } for i in range(count)]


def test_large_review_preserves_actual_affected_total_with_bounded_priority_sample():
    evidence = pages()
    body = {"website_url": "https://example.com", "pages_found": 500, "pages_crawled": 500, "pages": evidence}
    fingerprint = build_site_fingerprint(body, evidence, body["website_url"])
    fixes = prepare_fixes(build_page_pattern_findings(evidence), fingerprint, body, get_playbook(fingerprint["primary_archetype"]), evidence)
    [fix] = [fix for fix in fixes if fix["rule"] == "missing_meta_description"]
    assert fix["page_count"] == fix["affected_page_count"] == 500
    assert len(fix["affected_pages"]) == 150
    assert fix["affected_pages_complete"] is False
    assert fix["affected_pages"][0].endswith("item-499")
    assert sum(fix["family_breakdown"].values()) == 500
    assert first_failed_repair_invariant(fix) == ""
    canonical = apply_canonical_repair_contract({"recommendations": [fix], "cleaned_fixes": [fix]}, body)
    [persisted] = canonical["canonical_repairs"]
    assert persisted["affected_page_count"] == persisted["page_count"] == 500
    assert len(persisted["affected_pages"]) == 150
    assert first_failed_repair_invariant(persisted) == ""


def test_normalizing_an_already_bounded_card_does_not_reset_its_total():
    evidence = pages()
    fix = normalize_repair_scope({"rule": "missing_meta_description", "affected_pages": [page["url"] for page in evidence]}, evidence)
    normalized = normalize_repair_scope(fix, evidence)
    assert normalized["affected_page_count"] == normalized["page_count"] == 500
    assert normalized["affected_pages_complete"] is False
    assert normalized["family_breakdown"] == {"product_page": 500}
    assert first_failed_repair_invariant(normalized) == ""


def test_canonical_normalization_caps_direct_full_lists_before_persistence():
    evidence = pages()
    fix = _normalize_canonical_repair_evidence({"rule": "missing_meta_description", "affected_pages": [page["url"] for page in evidence]}, evidence)
    assert fix["affected_page_count"] == 500
    assert len(fix["affected_pages"]) == 150
    assert fix["affected_pages_complete"] is False


def test_published_evidence_contract_preserves_the_500_page_observed_count():
    evidence = pages()
    body = {"website_url": "https://example.com", "pages_found": 500, "pages_crawled": 500, "pages": evidence}
    fingerprint = build_site_fingerprint(body, evidence, body["website_url"])
    context = {"scan_origin": "https://example.com", "identity_version": PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION}
    fixes = prepare_fixes(build_page_pattern_findings(evidence, **context), fingerprint, body, get_playbook(fingerprint["primary_archetype"]), evidence, **context)
    [fix] = [fix for fix in fixes if fix["rule"] == "missing_meta_description"]
    canonical = apply_canonical_repair_contract({"recommendations": [fix], "cleaned_fixes": [fix]}, body, identity_version=PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION)
    [persisted] = canonical["canonical_repairs"]
    assert persisted["affected_page_count"] == persisted["page_count"] == 500
    assert len(persisted["affected_pages"]) == 150
    assert persisted["stage3_counts"]["unique_affected_page_count"] == 500
    assert persisted["stage3_counts"]["observation_count"] == 500
    assert persisted["stage3_priority_factors"]["reach"] == 1.0
    assert first_failed_repair_invariant(persisted, **context) == ""


def test_overlapping_incomplete_groups_never_add_counts_as_if_disjoint():
    evidence = pages()
    card = normalize_repair_scope({"rule": "missing_meta_description", "affected_pages": [page["url"] for page in evidence]}, evidence)
    merged = _merge_repair_group([card, dict(card)], evidence)
    assert merged["page_count"] == merged["affected_page_count"] == 500
    assert merged["affected_page_count_is_lower_bound"] is True
    assert len(merged["affected_pages"]) == 150
    assert merged["family_breakdown"] == {"product_page": 500}
    assert first_failed_repair_invariant(merged) == ""


def test_template_estimate_requires_full_observed_agreement_and_is_labelled():
    evidence = pages(5)
    body = {"website_url": "https://example.com", "pages_found": 1000, "pages_crawled": 5, "pages": evidence,
            "sampling_evidence": {"route_patterns": {"/products/:slug": {"inventory_count": 1000, "checked_count": 5, "selected_count": 5}}}}
    fingerprint = build_site_fingerprint(body, evidence, body["website_url"])
    def findings():
        return prepare_fixes(build_page_pattern_findings(evidence), fingerprint, body, get_playbook(fingerprint["primary_archetype"]), evidence)
    [fix] = [fix for fix in findings() if fix["rule"] == "missing_meta_description"]
    [estimate] = fix["template_impact_estimates"]
    assert estimate["observed_affected_count"] == estimate["checked_sample_count"] == 5
    assert estimate["estimated_affected_page_count"] == 1000
    assert estimate["is_extrapolation"] is True
    assert "estimate" in estimate["qualification"]
    assert fix["page_count"] == 5
    evidence[-1]["meta_description"] = "A useful description"
    evidence[-1]["meta_description_state"] = "present_valid"
    [fix] = [fix for fix in findings() if fix["rule"] == "missing_meta_description"]
    assert "template_impact_estimates" not in fix
