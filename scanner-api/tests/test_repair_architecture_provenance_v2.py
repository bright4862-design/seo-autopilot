"""Provenance gate and identity adversarial tests for isolated shadow candidate."""
from app.repair_architecture_provenance import (
    architectural_evidence_key,
    provenance_decision,
)
from app.repair_architecture_priority import (
    architecture_context,
    page_role,
    role_counts_for_affected,
)
from app.repair_priority_calibration import annotate_calibrated_repair_priority

VERSION = "architecture_role_evidence_v1"


def page(path, family="collection_page", **extras):
    return {"url": "https://example.com" + path, "page_template_family": family, **extras}


def evidence(role, source, *, ref="scan:1"):
    return {"version": VERSION, "claims": [{
        "producer": "fixlist_scanner_verified", "source": source,
        "role": role, "verified": True, "evidence_id": ref,
    }]}


def finding(*urls):
    return {"rule": "canonical_missing", "category": "canonical",
            "priority": "medium", "affected_pages": list(urls),
            "page_template_family": "mixed"}


def test_template_only_keeps_legacy_hub():
    p = page("/category/widgets")
    assert provenance_decision(p) == ("template_only", None)
    assert page_role(p) == "structural"


def test_unversioned_and_untrusted_role_claims_cannot_promote():
    p = page("/offer/123", "product_page")
    candidate = evidence("structural", "verified_directory")
    for bad in [{**candidate, "version": "wrong"},
                {"version": VERSION, "claims": [{"source": "verified_directory",
                  "role": "structural", "verified": True, "evidence_id": "x"}]},
                {"version": VERSION, "claims": [{"source": "verified_directory",
                  "role": "structural", "producer": "fixlist_scanner_verified",
                  "verified": True, "evidence_id": ""}]}]:
        p["architecture_role_evidence"] = bad
        assert provenance_decision(p) == ("insufficient_evidence", None)
        assert page_role(p) == "commercial_leaf"


def test_source_role_mismatch_fails_closed():
    p = page("/offer/x", "product_page",
             architecture_role_evidence=evidence("structural", "verified_customer_journey"))
    assert provenance_decision(p)[0] == "insufficient_evidence"
    assert page_role(p) == "commercial_leaf"


def test_conflicting_verified_claims_fail_closed():
    p = page("/products", "collection_page")
    e = evidence("structural", "verified_taxonomy")
    e["claims"].append(evidence("support", "verified_promotional_surface")["claims"][0])
    p["architecture_role_evidence"] = e
    assert provenance_decision(p) == ("conflicted", None)
    assert page_role(p) == "structural"


def test_verified_promo_demotes_pseudo_hub():
    p = page("/sale/flash", architecture_role_evidence=evidence("support", "verified_promotional_surface"))
    assert provenance_decision(p) == ("promotional_or_transient", "support")
    assert page_role(p) == "support"


def test_verified_directory_structural_without_template_guessing():
    p = page("/sellers", "seller_directory",
             architecture_role_evidence=evidence("structural", "verified_directory"))
    assert provenance_decision(p) == ("proven_structural", "structural")
    assert page_role(p) == "structural"
    assert page_role(page("/sellers", "seller_directory")) == "other"


def test_verified_business_journey_in_unknown_family():
    p = page("/checkout", "standard",
             architecture_role_evidence=evidence("business_critical", "verified_customer_journey"))
    assert provenance_decision(p) == ("proven_business_critical", "business_critical")
    assert page_role(p) == "business_critical"


def test_seller_profile_not_promoted_by_collection_template():
    assert page_role(page("/seller/123", entity_scope="seller_profile")) == "commercial_leaf"
    assert page_role(page("/seller/123", "seller_profile")) == "commercial_leaf"


def test_multiple_offers_for_one_explicit_product_count_once():
    pages = [page("/offers/s1/sku-123", "product_offer", product_entity_id="SKU-123"),
             page("/offers/s2/sku-123", "product_offer", product_entity_id="SKU-123")]
    fix = finding("/offers/s1/sku-123", "/offers/s2/sku-123")
    counts = role_counts_for_affected(fix, pages)
    assert counts.commercial_leaf == 1
    context = architecture_context(fix, pages, checked_eligible=None)
    assert context["role_counts"]["commercial_leaf"] == 1


def test_unknown_query_is_distinct_but_utm_and_fragment_are_not():
    assert architectural_evidence_key("/paint?brand=A&utm_source=x#top") == "/paint?brand=A"
    assert architectural_evidence_key("/paint?brand=A") != architectural_evidence_key("/paint?brand=B")
    assert architectural_evidence_key("/paint?utm_own=1&gclid=xx") == "/paint"


def test_affected_tracking_aliases_dedupe_in_shadow():
    p = page("/sale", "product_page")
    fix = finding("/sale?utm_source=x", "/sale#hero", "/sale?gclid=123")
    assert role_counts_for_affected(fix, [p]).commercial_leaf == 1


def test_substantive_facets_do_not_collapse_to_one_architectural_identity():
    a = page("/paint?brand=A", "product_page")
    b = page("/paint?brand=B", "product_page")
    fix = finding("/paint?brand=A", "/paint?brand=B")
    assert role_counts_for_affected(fix, [a, b]).commercial_leaf == 2


def test_existing_public_priority_fields_unchanged_and_new_metadata_nested():
    p = page("/sale", "product_page")
    fix = finding("/sale")
    out = annotate_calibrated_repair_priority(fix, [p])
    for field in ("base_severity", "action_priority", "action_priority_score",
                  "priority_context", "priority_reason", "repair_leverage_confirmed"):
        assert field in out
    assert out["priority_context"]["architecture_priority_version"] == "repair_architecture_priority_v2_provenance_shadow"
    assert out["priority_context"]["architecture_role_counts"]["commercial_leaf"] == 1
    assert out["priority_context"]["architecture_role_bonus"] > 0
