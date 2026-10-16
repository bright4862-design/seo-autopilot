from app.stage3_root_causes import (
    ROOT_CAUSE_EVIDENCE_VERSION,
    ROOT_CAUSE_GROUPING_VERSION,
    group_evidenced_root_causes,
)


def evidence(root_cause_id, *refs, state="verified", surface=""):
    value = {
        "version": ROOT_CAUSE_EVIDENCE_VERSION,
        "state": state,
        "root_cause_id": root_cause_id,
        "evidence_refs": list(refs),
    }
    if surface:
        value["repair_surface_id"] = surface
    return value


def test_same_family_similarity_alone_never_groups_repairs():
    fixes = [
        {
            "id": "seo-title-a",
            "rule": "missing_meta_description",
            "finding_domain": "seo",
            "page_template_family": "product_page",
            "affected_pages": ["/products/a"],
        },
        {
            "id": "seo-title-b",
            "rule": "missing_meta_description",
            "finding_domain": "seo",
            "page_template_family": "product_page",
            "affected_pages": ["/products/b"],
        },
    ]

    groups = group_evidenced_root_causes(fixes, scan_id="scan-1")

    assert len(groups) == 2
    assert all(group["member_count"] == 1 for group in groups)
    assert all(group["grouping_state"] == "not_verified" for group in groups)
    assert all(group["root_cause_id"] is None for group in groups)


def test_verified_shared_cause_merges_seo_and_geo_but_keeps_partitions():
    fixes = [
        {
            "id": "seo-nav",
            "rule": "internal_link_redirect",
            "finding_domain": "seo",
            "page_template_family": "collection_page",
            "affected_pages": ["/shop", "/collections/a"],
            "observation_ids": ["obs-seo"],
            "root_cause_evidence": evidence(
                "shared-nav-links",
                "ev-nav-html",
                surface="header-nav",
            ),
        },
        {
            "id": "geo-nav",
            "rule": "geo_entity_navigation_gap",
            "finding_domain": "geo",
            "page_template_family": "location_landing",
            "affected_pages": ["/locations/paris", "/shop"],
            "observation_ids": ["obs-geo"],
            "root_cause_evidence": evidence(
                "shared-nav-links",
                "ev-nav-rendered",
                surface="header-nav",
            ),
        },
    ]

    groups = group_evidenced_root_causes(fixes, scan_id="scan-1")

    assert len(groups) == 1
    group = groups[0]
    assert group["version"] == ROOT_CAUSE_GROUPING_VERSION
    assert group["grouping_state"] == "verified"
    assert group["root_cause_id"] == "shared-nav-links"
    assert group["repair_surface_id"] == "header-nav"
    assert group["member_ids"] == ["seo-nav", "geo-nav"]
    assert group["domains"] == ["seo", "geo"]
    assert group["family_partitions"] == {
        "collection_page": ["seo-nav"],
        "location_landing": ["geo-nav"],
    }
    assert group["affected_pages"] == ["/shop", "/collections/a", "/locations/paris"]
    assert group["affected_page_count"] == 3
    assert group["contributing_evidence_refs"] == ["ev-nav-html", "ev-nav-rendered"]
    assert group["contributing_observation_ids"] == ["obs-seo", "obs-geo"]
    assert group["suppressed_members"] == [
        {
            "member_id": "geo-nav",
            "reason": "same_verified_root_cause",
            "root_cause_id": "shared-nav-links",
            "repair_surface_id": "header-nav",
            "evidence_refs": ["ev-nav-rendered"],
        }
    ]


def test_exact_affected_url_spellings_are_unioned_without_normalization():
    fixes = [
        {
            "id": "one",
            "page_template_family": "product_page",
            "affected_pages": ["https://example.com/x", "https://example.com/x/"],
            "root_cause_evidence": evidence("template-x", "ev-1"),
        },
        {
            "id": "two",
            "page_template_family": "product_page",
            "affected_pages": ["https://example.com/X", "https://example.com/x"],
            "root_cause_evidence": evidence("template-x", "ev-2"),
        },
    ]

    group = group_evidenced_root_causes(fixes, scan_id="scan-1")[0]

    assert group["affected_pages"] == [
        "https://example.com/x",
        "https://example.com/x/",
        "https://example.com/X",
    ]
    assert group["affected_page_count"] == 3


def test_conflicted_root_cause_evidence_fails_closed_as_singleton():
    fixes = [
        {
            "id": "verified",
            "page_template_family": "product_page",
            "affected_pages": ["/a"],
            "root_cause_evidence": evidence("same-id", "ev-a"),
        },
        {
            "id": "conflicted",
            "page_template_family": "product_page",
            "affected_pages": ["/b"],
            "root_cause_evidence": evidence("same-id", "ev-b", state="conflicted"),
        },
    ]

    groups = group_evidenced_root_causes(fixes, scan_id="scan-1")

    assert len(groups) == 2
    conflicted = next(group for group in groups if group["member_ids"] == ["conflicted"])
    verified = next(group for group in groups if group["member_ids"] == ["verified"])
    assert conflicted["grouping_state"] == "conflicted"
    assert verified["grouping_state"] == "verified"
    assert verified["member_count"] == 1


def test_verified_cause_without_evidence_references_does_not_group():
    fixes = [
        {
            "id": "a",
            "affected_pages": ["/a"],
            "root_cause_evidence": evidence("template-root"),
        },
        {
            "id": "b",
            "affected_pages": ["/b"],
            "root_cause_evidence": evidence("template-root"),
        },
    ]

    groups = group_evidenced_root_causes(fixes, scan_id="scan-1")

    assert len(groups) == 2
    assert all(group["grouping_state"] == "not_verified" for group in groups)
    assert all("no contributing evidence references" in group["grouping_reason"] for group in groups)


def test_repair_local_scan_identity_cannot_create_trust_without_producer_identity():
    fixes = [
        {
            "id": "scan-a",
            "scan_id": "scan-a-id",
            "page_template_family": "product_page",
            "affected_pages": ["/a"],
            "root_cause_evidence": evidence("same-root", "ev-a"),
        },
        {
            "id": "scan-b",
            "scan_id": "scan-b-id",
            "page_template_family": "product_page",
            "affected_pages": ["/b"],
            "root_cause_evidence": evidence("same-root", "ev-b"),
        },
    ]

    groups = group_evidenced_root_causes(fixes)

    assert len(groups) == 2
    assert all(group["scan_id"] is None for group in groups)
    assert all(group["member_count"] == 1 for group in groups)
    assert all(group["grouping_state"] == "not_verified" for group in groups)
    assert all("requires exact scan identity" in group["grouping_reason"] for group in groups)


def test_verified_cause_without_scan_identity_does_not_group():
    fixes = [
        {
            "id": "a",
            "affected_pages": ["/a"],
            "root_cause_evidence": evidence("same-root", "ev-a"),
        },
        {
            "id": "b",
            "affected_pages": ["/b"],
            "root_cause_evidence": evidence("same-root", "ev-b"),
        },
    ]

    groups = group_evidenced_root_causes(fixes)

    assert len(groups) == 2
    assert all(group["member_count"] == 1 for group in groups)
    assert all(group["grouping_state"] == "not_verified" for group in groups)
    assert all("requires exact scan identity" in group["grouping_reason"] for group in groups)
    assert all(group["scan_id"] is None for group in groups)


def test_same_root_cause_id_with_different_repair_surfaces_stays_separate():
    fixes = [
        {
            "id": "header",
            "affected_pages": ["/a"],
            "root_cause_evidence": evidence("nav-root", "ev-header", surface="header"),
        },
        {
            "id": "footer",
            "affected_pages": ["/b"],
            "root_cause_evidence": evidence("nav-root", "ev-footer", surface="footer"),
        },
    ]

    groups = group_evidenced_root_causes(fixes, scan_id="scan-1")

    assert len(groups) == 2
    assert {group["repair_surface_id"] for group in groups} == {"header", "footer"}


def test_grouping_preserves_first_seen_rank_order_when_later_member_joins():
    fixes = [
        {
            "id": "ranked-first",
            "affected_pages": ["/a"],
            "root_cause_evidence": evidence("shared-root", "ev-a", surface="template"),
        },
        {
            "id": "later-singleton",
            "affected_pages": ["/b"],
        },
        {
            "id": "ranked-first-geo",
            "finding_domain": "geo",
            "page_template_family": "location_landing",
            "affected_pages": ["/c"],
            "root_cause_evidence": evidence("shared-root", "ev-c", surface="template"),
        },
    ]

    groups = group_evidenced_root_causes(fixes, scan_id="scan-1")

    assert [group["member_ids"] for group in groups] == [
        ["ranked-first", "ranked-first-geo"],
        ["later-singleton"],
    ]
