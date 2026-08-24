"""Patch D - a mixed finding stays mixed, and says what it is made of.

Suppressing an impossible ratio (the previous commit) stops the lie. It does not
tell the customer anything. 126 orphaned URLs spanning workshops, categories and
content are not one repair against one family -- they are partitions, and the
customer needs the breakdown to act on any of them.

The family must come from the family already stamped on authoritative page
evidence. Re-deriving it from the path here would be a second opinion competing
with the crawl's own, and inheriting the first member's family is how a mixed
group came to be labelled Homepage in the first place.
"""
import pytest

from app.repair_coverage import (
    REPAIR_COVERAGE_VERSION,
    normalize_repair_scope,
)


def page(path, family, *, usable=True):
    return {
        "url": f"https://ex.com{path}",
        "final_url": f"https://ex.com{path}",
        "path": path,
        "status_code": 200 if usable else 429,
        "content_type": "text/html",
        "page_evidence_class": "usable_html" if usable else "failed_access",
        "word_count": 300 if usable else 0,
        "title": "T" if usable else "",
        "h1": "H" if usable else "",
        "page_template_family": family,
    }


def test_the_pass_is_versioned():
    assert REPAIR_COVERAGE_VERSION.startswith("repair_coverage_")


# ------------------------------------------------------ one family stays one --


def test_a_single_family_group_keeps_family_scope():
    pages = [page(f"/p{i}", "product_page") for i in range(10)]
    fix = normalize_repair_scope(
        {"rule": "missing_h1", "affected_pages": [f"https://ex.com/p{i}" for i in range(4)]},
        pages,
    )

    assert fix["page_scope"] == "family"
    assert fix["page_template_family"] == "product_page"
    assert fix["family_breakdown"] == {"product_page": 4}
    assert fix["page_count"] == 4


def test_a_single_affected_page_is_page_scope():
    pages = [page("/p0", "product_page")]
    fix = normalize_repair_scope(
        {"rule": "missing_h1", "affected_pages": ["https://ex.com/p0"]}, pages
    )
    assert fix["page_scope"] == "page"
    assert fix["page_template_family"] == "product_page"


# ------------------------------------------------------- mixed stays mixed --


def test_the_wecandoo_group_is_partitioned_not_labelled_homepage():
    """126 mixed URLs. The live output said "126 of 1 searchable homepage pages"."""
    pages = (
        [page("/", "homepage")]
        + [page(f"/w{i}", "product_page") for i in range(60)]
        + [page(f"/c{i}", "category_listing") for i in range(40)]
        + [page(f"/g{i}", "guide_article") for i in range(26)]
    )
    affected = (
        [f"https://ex.com/w{i}" for i in range(60)]
        + [f"https://ex.com/c{i}" for i in range(40)]
        + [f"https://ex.com/g{i}" for i in range(26)]
    )
    fix = normalize_repair_scope({"rule": "potential_orphan_pages", "affected_pages": affected}, pages)

    assert fix["page_scope"] == "mixed"
    assert fix["page_template_family"] == "mixed"
    assert fix["family_breakdown"] == {"product_page": 60, "category_listing": 40, "guide_article": 26}
    assert fix["page_count"] == 126
    # Never the family of a page that is not even in the affected set.
    assert "homepage" not in fix["family_breakdown"]


def test_a_mixed_group_offers_a_representative_per_family():
    pages = [page("/w0", "product_page"), page("/c0", "category_listing")]
    fix = normalize_repair_scope(
        {"rule": "potential_orphan_pages", "affected_pages": ["https://ex.com/w0", "https://ex.com/c0"]},
        pages,
    )

    by_family = fix["representative_pages_by_family"]
    assert set(by_family) == {"product_page", "category_listing"}
    assert by_family["product_page"].endswith("/w0")
    assert by_family["category_listing"].endswith("/c0")


def test_a_representative_never_rewrites_the_scope():
    """The audit's exact mechanism: the chosen representative set the family."""
    pages = [page("/", "homepage"), page("/w0", "product_page")]
    fix = normalize_repair_scope(
        {
            "rule": "potential_orphan_pages",
            "page_url": "https://ex.com/",          # a homepage representative
            "page_template_family": "homepage",     # and a homepage stamp
            "affected_pages": ["https://ex.com/w0"],
        },
        pages,
    )

    assert fix["page_template_family"] == "product_page", "the affected evidence decides, not the representative"


# ------------------------------------------------- families come from evidence --


def test_the_family_is_read_from_page_evidence_not_re_derived():
    """The crawl already classified this page; this pass must not disagree."""
    pages = [page("/looks-like-a-blog-post", "product_page")]
    fix = normalize_repair_scope(
        {"rule": "missing_h1", "affected_pages": ["https://ex.com/looks-like-a-blog-post"]}, pages
    )
    assert fix["page_template_family"] == "product_page"


def test_affected_urls_with_no_page_evidence_are_an_unknown_partition():
    """Not silently dropped, and not folded into a family they were never in."""
    pages = [page("/p0", "product_page")]
    fix = normalize_repair_scope(
        {"rule": "missing_h1", "affected_pages": ["https://ex.com/p0", "https://ex.com/never-crawled"]},
        pages,
    )

    assert fix["family_breakdown"] == {"product_page": 1, "unknown": 1}
    assert fix["page_scope"] == "mixed"
    assert fix["page_count"] == 2


# ------------------------------------------------------------ explicit scope --


def test_explicit_sitewide_scope_is_preserved():
    pages = [page(f"/p{i}", "product_page") for i in range(5)]
    fix = normalize_repair_scope(
        {"rule": "robots_directive_conflict", "page_scope": "sitewide",
         "affected_pages": [f"https://ex.com/p{i}" for i in range(5)]},
        pages,
    )
    assert fix["page_scope"] == "sitewide"


def test_access_failure_evidence_is_cross_cutting_with_no_invented_family():
    pages = [page(f"/p{i}", "product_page") for i in range(6)]
    fix = normalize_repair_scope(
        {"rule": "rate_limited_page",
         "affected_pages": [f"https://ex.com/blocked/{i}" for i in range(47)]},
        pages,
    )

    assert fix["page_scope"] == "cross_cutting"
    assert fix["page_template_family"] == "mixed"


# ------------------------------------------------------------- invariants --


def test_query_variants_are_deduped_by_evidence_identity_not_template_path():
    pages = [page("/a", "product_page")]
    fix = normalize_repair_scope(
        {
            "rule": "missing_h1",
            "affected_pages": [
                "/a?b=1&c=2",
                "/a?c=2&b=1",
                "/a?b=1&c=2&utm_source=x",
                "/a?b=9&c=2",
            ],
        },
        pages,
    )

    assert fix["affected_pages"] == ["/a?b=1&c=2", "/a?b=9&c=2"]
    assert fix["page_count"] == 2
    assert fix["family_breakdown"] == {"product_page": 2}


def test_the_breakdown_always_accounts_for_every_affected_page():
    """page_count == unique(affected_pages) == sum(family_breakdown)."""
    pages = [page("/a", "product_page"), page("/b", "guide_article")]
    fix = normalize_repair_scope(
        {"rule": "missing_h1",
         "affected_pages": ["https://ex.com/a", "https://ex.com/b", "https://ex.com/a"]},
        pages,
    )

    assert fix["page_count"] == 2, "duplicates must not inflate the count"
    assert sum(fix["family_breakdown"].values()) == fix["page_count"]
    assert fix["affected_pages_complete"] is True


def test_a_truncated_affected_list_declares_itself_incomplete():
    """A sample compared against a total is the same defect in another shape."""
    pages = [page(f"/p{i}", "product_page") for i in range(200)]
    fix = normalize_repair_scope(
        {"rule": "missing_h1", "affected_pages": [f"https://ex.com/p{i}" for i in range(200)]},
        pages,
        max_affected=150,
    )

    assert fix["affected_pages_complete"] is False
    assert fix["page_count"] == 200, "the true total is kept even when the list is cut"
    assert len(fix["affected_pages"]) == 150


def test_the_pass_does_not_mutate_its_input():
    original = {"rule": "missing_h1", "affected_pages": ["https://ex.com/p0"]}
    snapshot = dict(original)
    normalize_repair_scope(original, [page("/p0", "product_page")])
    assert original == snapshot
