"""Patch D - a denominator must come from the same URL universe as its numerator.

Twenty of the thirty completed audit scans shipped a ratio that cannot be true.
Wecandoo told the customer "126 of 1 searchable homepage pages"; Airbnb 126/1;
Castorama 79/1; Pretto 35 affected loan pages out of 30 eligible; Meilleurtaux
47 access-limited loan pages out of 6, and 22 failed out of 6.

Two root causes, both traced in the audit's source-trace.md:

A. An aggregate navigation finding is built through the generic constructor with
   an empty page_url. classify_template("") returns "homepage", so the mixed
   group is *born* in the wrong family, before representative selection ever
   runs. Nothing downstream can recover the truth after that.

B. repair_priority counts every affected URL in the numerator but derives the
   denominator from usable HTML pages in one family. The two are different URL
   sets, so the ratio is not a ratio. Access and failure evidence is worst hit:
   those pages are deliberately absent from the usable-HTML denominator while
   remaining in the numerator.

Evidence: docs/audit/2026-08-21-production-50-site/
"""
import pytest

from app.extract import classify_template


# ----------------------------------------------------------- root cause A --


def test_an_empty_path_is_unknown_not_homepage():
    """The single line that births every mixed group as Homepage.

    An aggregate finding has no page of its own. Classifying its absent URL as
    the homepage is not a fallback, it is an assertion the scanner cannot
    support -- and it is why 126 mixed URLs end up compared against one page.
    """
    assert classify_template("") == "unknown"
    assert classify_template(None) == "unknown"


def test_the_real_homepage_is_still_the_homepage():
    """The fix must not cost the classification it exists to protect."""
    assert classify_template("/") == "homepage"
    assert classify_template("/?utm_source=x") == "homepage"
    assert classify_template("/#top") == "homepage"


def test_a_whitespace_only_path_is_unknown():
    assert classify_template("   ") == "unknown"


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/products/wine-1", "product_page"),
        ("/blog/post", "guide_article"),
        ("/tag/red", "archive"),
    ],
)
def test_ordinary_classification_is_untouched(path, expected):
    assert classify_template(path) == expected


# ----------------------------------------------------------- root cause B --

from app.repair_priority import build_coverage_context  # noqa: E402


def page(path, *, family="product_page", usable=True, status=200):
    return {
        "url": f"https://ex.com{path}",
        "final_url": f"https://ex.com{path}",
        "path": path,
        "status_code": status,
        "content_type": "text/html",
        "page_evidence_class": "usable_html" if usable else "failed_access",
        "word_count": 300 if usable else 0,
        "title": "T" if usable else "",
        "h1": "H" if usable else "",
        "page_template_family": family,
        "indexability_state": "indexable",
    }


def test_wecandoo_shape_cannot_report_more_affected_than_eligible():
    """126 mixed workshop URLs against one homepage. The live customer string
    was "126 of 1 searchable homepage pages"."""
    pages = [page("/", family="homepage")] + [page(f"/w{i}") for i in range(126)]
    fix = {
        "rule": "potential_orphan_pages",
        "page_template_family": "homepage",
        "affected_pages": [f"https://ex.com/w{i}" for i in range(126)],
    }
    context = build_coverage_context(fix, pages)

    if context.checked_eligible is not None:
        assert context.affected_eligible <= context.checked_eligible, (
            f"{context.affected_eligible} affected of {context.checked_eligible} eligible is impossible"
        )
    assert context.checked_coverage is None or 0.0 <= context.checked_coverage <= 1.0


def test_pretto_shape_cannot_report_35_of_30():
    """35 affected loan pages out of 30 eligible loan pages."""
    pages = [page(f"/loan/{i}", family="loan_program") for i in range(30)]
    fix = {
        "rule": "sitemap_redirect",
        "page_template_family": "loan_program",
        # Five affected URLs were never retained as usable HTML.
        "affected_pages": [f"https://ex.com/loan/{i}" for i in range(35)],
    }
    context = build_coverage_context(fix, pages)

    assert context.affected_eligible <= (context.checked_eligible or 0) or context.checked_eligible is None
    assert context.checked_coverage is None or context.checked_coverage <= 1.0


def test_meilleurtaux_access_evidence_shows_a_count_not_a_ratio():
    """47 access-limited loan pages out of 6 eligible.

    Access and failure evidence is the worst case: those pages are deliberately
    excluded from the usable-HTML denominator while staying in the numerator, so
    the ratio was guaranteed to be impossible. With no measured universe the
    honest output is an observation count.
    """
    pages = [page(f"/loan/{i}", family="loan_program") for i in range(6)]
    fix = {
        "rule": "site_access_limited",
        "page_template_family": "loan_program",
        "affected_pages": [f"https://ex.com/blocked/{i}" for i in range(47)],
    }
    context = build_coverage_context(fix, pages)

    assert context.checked_coverage is None or context.checked_coverage <= 1.0
    assert context.affected_eligible <= (context.checked_eligible or context.affected_eligible)


def test_a_genuine_one_family_group_still_reports_a_real_ratio():
    """The fix must not suppress ratios that were always correct."""
    pages = [page(f"/p{i}") for i in range(20)]
    fix = {
        "rule": "missing_h1",
        "page_template_family": "product_page",
        "affected_pages": [f"https://ex.com/p{i}" for i in range(5)],
    }
    context = build_coverage_context(fix, pages)

    assert context.checked_eligible == 20
    assert context.affected_eligible == 5
    assert context.checked_coverage == pytest.approx(0.25)


def test_the_invariants_hold_for_every_production_shape():
    """0 <= affected_eligible <= affected_observed <= affected_reported."""
    pages = [page("/", family="homepage")] + [page(f"/w{i}") for i in range(126)]
    fix = {
        "rule": "potential_orphan_pages",
        "page_template_family": "homepage",
        "affected_pages": [f"https://ex.com/w{i}" for i in range(126)],
    }
    context = build_coverage_context(fix, pages)

    assert 0 <= context.affected_eligible <= context.affected_observed <= context.affected_reported
    if context.checked_eligible is not None:
        assert context.affected_eligible <= context.checked_eligible
    assert 0 <= context.indexable_affected <= context.affected_eligible
