from copy import deepcopy

from app.repair_contract_v2 import _normalize_post_review_sitewide_evidence


def _page(path: str, family: str) -> dict:
    return {
        "url": f"https://example.com{path}",
        "final_url": f"https://example.com{path}",
        "status_code": 200,
        "page_template_family": family,
        "indexable": True,
    }


def test_sitewide_canonical_boundary_repartitions_unique_affected_pages_once():
    pages = []
    for family, paths in {
        "activity_detail": [f"/a{i}" for i in range(5)],
        "collection_page": [f"/c{i}" for i in range(4)],
        "standard": [f"/s{i}" for i in range(3)],
    }.items():
        pages.extend(_page(path, family) for path in paths)

    repair = {
        "fix_id": "sitewide-canonical",
        "rule": "canonical_missing",
        "source": "review_sitewide_collapse:canonical_missing",
        "page_scope": "sitewide",
        "page_template_family": "",
        "affected_pages": [f"/a{i}" for i in range(5)] + [f"/c{i}" for i in range(4)] + [f"/s{i}" for i in range(3)],
        "page_count": 12,
        # /a2 appeared in two pre-collapse candidate groups, so the old
        # producer could report 13 family memberships for 12 unique URLs.
        "family_breakdown": {"activity_detail": 6, "collection_page": 4, "standard": 3},
        "representative_pages_by_family": {
            "activity_detail": ["/a0", "/a1"],
            "collection_page": ["/c0"],
            "standard": ["/s0"],
        },
        "affected_pages_complete": True,
        "repair_coverage_version": "repair_coverage_v1_family_consistent",
        "repair_surface": "global_document_head",
        "remediation_family": "add_self_referencing_canonical",
    }

    normalized = _normalize_post_review_sitewide_evidence(repair, pages)

    assert normalized["page_count"] == 12
    assert normalized["family_breakdown"] == {
        "activity_detail": 5,
        "collection_page": 4,
        "standard": 3,
    }
    assert sum(normalized["family_breakdown"].values()) == normalized["page_count"]
    assert normalized["repair_identity"]["page_scope"] == "sitewide"


def test_non_sitewide_repairs_are_not_rewritten_by_cutover_normalizer():
    repair = {
        "fix_id": "family-repair",
        "rule": "missing_h1",
        "source": "page_pattern:missing_h1:collection_page",
        "page_scope": "family",
        "page_template_family": "collection_page",
        "affected_pages": ["/a", "/b"],
        "page_count": 2,
        "family_breakdown": {"collection_page": 2},
    }
    before = deepcopy(repair)

    assert _normalize_post_review_sitewide_evidence(repair, []) == before
    assert repair == before
