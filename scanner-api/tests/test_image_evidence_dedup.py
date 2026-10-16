"""Material image repairs must not erase separate image-purpose review work."""

import pytest

from app.extract import extract_page
from app.repair_dedup import (
    suppress_duplicate_group_cards,
    suppress_group_covered_singletons,
)
from app.scan_job import build_local_review
from app.scanner import build_findings, group_findings


ORIGIN = "https://example.com"


@pytest.mark.parametrize("material_count,uncertain_count", [(2, 2), (3, 3), (2, 3), (3, 2)])
def test_real_review_keeps_overlapping_material_and_uncertain_image_groups(material_count, uncertain_count):
    page_count = max(material_count, uncertain_count)
    urls = [f"{ORIGIN}/exhibits/{index}" for index in range(page_count)]
    pages = []
    for index, url in enumerate(urls):
        images = []
        if index < material_count:
            images.append('<figure><img src="subject.jpg"><figcaption>The exhibit</figcaption></figure>')
        if index < uncertain_count:
            images.append('<img src="other.jpg">')
        html = '<html><head><title>Exhibit guide</title></head><body><main><h1>Exhibit</h1>' + ''.join(images) + '</main></body></html>'
        pages.append({
            **extract_page(html, url, url, 200, "text/html", {"discovered_from": ["internal_link"]}),
            "page_template_family": "activity_detail",
        })
    raw = build_findings(pages)
    scan = {
        "success": True,
        "website_url": ORIGIN,
        "crawl_scope": {"requested_origin": ORIGIN},
        "pages": pages,
        "pages_found": page_count,
        "pages_crawled": page_count,
        "raw_findings": raw,
        "findings": group_findings(raw),
    }

    for rows in [raw, build_local_review(scan)["canonical_repairs"]]:
        image_rows = [row for row in rows if row["rule"] in {"image_alt_text", "image_alt_review"}]
        assert {row["rule"] for row in image_rows} == {"image_alt_text", "image_alt_review"}
        assert len(image_rows) == 2
        for row in image_rows:
            expected_kind = "uncertain" if row["rule"] == "image_alt_review" else "material"
            expected_count = uncertain_count if expected_kind == "uncertain" else material_count
            assert row["affected_pages"] == urls[:expected_count]
            assert row["page_count"] == expected_count
            assert row["repair_observation_count"] == expected_count
            assert {sample["decorative_state"] for sample in row["repair_observation_samples"]} == {expected_kind}
            if expected_kind == "uncertain":
                assert row["non_scoring"] is True
                assert row["verification_state"] == "needs_verification"
            else:
                assert row.get("non_scoring") is not True


def image_fix(rule, paths, **extra):
    return {
        "rule": rule,
        "category": "image_alt_text",
        "affected_pages": paths,
        **extra,
    }


@pytest.mark.parametrize("group_rule,singleton_rule", [
    ("image_alt_text", "image_alt_review"),
    ("image_alt_review", "image_alt_text"),
])
def test_generator_group_does_not_suppress_a_different_image_action(group_rule, singleton_rule):
    group = image_fix(group_rule, ["/a", "/b"], source=f"page_pattern:{group_rule}")
    matching_singleton = image_fix(group_rule, ["/a"])
    distinct_singleton = image_fix(singleton_rule, ["/a"])

    assert suppress_group_covered_singletons([group, matching_singleton, distinct_singleton]) == [
        group, distinct_singleton,
    ]


@pytest.mark.parametrize("rule", ["image_alt_text", "image_alt_review"])
def test_duplicate_groups_of_the_same_image_action_still_collapse(rule):
    group = image_fix(rule, ["/a", "/b"], source=f"page_pattern:{rule}")
    duplicate = image_fix(rule, ["/a", "/b"])

    assert suppress_duplicate_group_cards([group, duplicate]) == [group]
