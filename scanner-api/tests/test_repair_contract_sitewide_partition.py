from copy import deepcopy

from app.repair_contract_v2 import _normalize_canonical_repair_evidence
from app.repair_coverage import first_failed_repair_invariant


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

    normalized = _normalize_canonical_repair_evidence(repair, pages)

    assert normalized["page_count"] == 12
    assert normalized["family_breakdown"] == {
        "activity_detail": 5,
        "collection_page": 4,
        "standard": 3,
    }
    assert sum(normalized["family_breakdown"].values()) == normalized["page_count"]
    assert normalized["repair_identity"]["page_scope"] == "sitewide"


def test_non_sitewide_repairs_are_reconciled_at_the_canonical_boundary():
    pages = [_page("/a", "collection_page"), _page("/b", "collection_page")]
    repair = {
        "fix_id": "family-repair",
        "rule": "missing_h1",
        "source": "page_pattern:missing_h1:collection_page",
        "page_scope": "page",  # deliberately stale
        "page_template_family": "homepage",
        "affected_pages": ["/a", "/b", "/a"],
        "page_count": 99,
        "family_breakdown": {"homepage": 99},
        "representative_pages_by_family": {"homepage": ["/"]},
    }
    before = deepcopy(repair)

    normalized = _normalize_canonical_repair_evidence(repair, pages)

    assert repair == before, "canonical reconciliation must not mutate finished review output"
    assert normalized["affected_pages"] == ["/a", "/b"]
    assert normalized["page_count"] == 2
    assert normalized["page_scope"] == "family"
    assert normalized["page_template_family"] == "collection_page"
    assert normalized["family_breakdown"] == {"collection_page": 2}
    assert first_failed_repair_invariant(normalized) == ""


def test_query_variants_use_the_same_evidence_identity_as_base44():
    pages = [_page("/a", "collection_page")]
    repair = {
        "fix_id": "query-repair",
        "rule": "missing_h1",
        "page_scope": "family",
        "page_template_family": "collection_page",
        "affected_pages": [
            "/a?b=1&c=2",
            "/a?c=2&b=1",             # same evidence, reordered query
            "/a?b=1&c=2&utm_source=x", # same evidence, tracking only
            "/a?b=9&c=2",              # genuinely different evidence
        ],
        "page_count": 4,
        "family_breakdown": {"collection_page": 4},
    }

    normalized = _normalize_canonical_repair_evidence(repair, pages)

    assert normalized["affected_pages"] == ["/a?b=1&c=2", "/a?b=9&c=2"]
    assert normalized["page_count"] == 2
    assert normalized["family_breakdown"] == {"collection_page": 2}
    assert first_failed_repair_invariant(normalized) == ""


def test_incomplete_affected_sample_preserves_the_proven_total():
    repair = {
        "fix_id": "sampled-repair",
        "rule": "potential_orphan_pages",
        "page_scope": "family",
        "page_template_family": "activity_detail",
        "affected_pages": [f"/a{i}" for i in range(150)],
        "page_count": 200,
        "family_breakdown": {"activity_detail": 200},
        "representative_pages_by_family": {"activity_detail": ["/a0"]},
        "affected_pages_complete": False,
    }

    normalized = _normalize_canonical_repair_evidence(repair, [])

    assert normalized["page_count"] == 200
    assert len(normalized["affected_pages"]) == 150
    assert normalized["affected_pages_complete"] is False
    assert normalized["family_breakdown"] == {"activity_detail": 200}
    assert first_failed_repair_invariant(normalized) == ""
