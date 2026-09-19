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
from app.repair_coverage import PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION, normalize_repair_scope  # noqa: E402


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


def test_published_scope_joins_stamps_by_exact_route_not_family_path():
    pages = [page("/x", family="product_page"), page("/x/", family="guide_article"),
             page("/X", family="location_landing")]
    fix = {"affected_pages": ["/x", "https://ex.com/x", "/x/", "/X", "https://foreign.example/x"]}
    normalized = normalize_repair_scope(fix, pages, scan_origin="https://ex.com",
                                        identity_version=PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION)
    assert normalized["page_count"] == 4
    assert normalized["family_breakdown"] == {
        "product_page": 1, "guide_article": 1, "location_landing": 1, "unknown": 1,
    }
    assert normalized["affected_pages"] == ["/x", "/x/", "/X", "https://foreign.example/x"]


def test_published_priority_joins_keep_indexability_and_origins_separate():
    pages = [page("/x"), page("/x/")]
    pages[0]["indexable"] = True
    pages[1]["indexable"] = False
    pages[1]["indexability_state"] = "non_indexable"
    fix = {"page_template_family": "product_page", "affected_pages": ["/x", "https://foreign.example/x/"]}
    context = build_coverage_context(fix, pages, scan_origin="https://ex.com",
                                     identity_version=PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION)
    assert context.affected_reported == 2
    assert context.affected_observed == 1
    assert context.indexable_affected == 1
    assert context.non_indexable_affected == 0
    assert context.checked_eligible == 2


def test_published_business_role_join_does_not_inherit_another_routes_role():
    from app.repair_architecture_priority import role_counts_for_affected

    pages = [page("/x", family="guide_article"), page("/x/", family="loan_program")]
    counts = role_counts_for_affected({"affected_pages": ["/x"]}, pages, scan_origin="https://ex.com",
                                     identity_version=PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION)
    assert counts.support == 1
    assert counts.business_critical == 0


def test_published_scope_does_not_silently_drop_unresolvable_affected_evidence():
    with pytest.raises(ValueError, match="unresolvable affected evidence"):
        normalize_repair_scope({"affected_pages": ["/x", "not-a-root-relative-url"]}, [page("/x")],
                               scan_origin="https://ex.com", identity_version=PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION)


def test_published_invariant_rejects_invalid_evidence_even_when_count_matches_valid_subset():
    from app.repair_coverage import first_failed_repair_invariant

    fix = {"affected_pages": ["/x", "not-a-root-relative-url"], "page_count": 1,
           "evidence_url_identity_version": PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION}
    assert first_failed_repair_invariant(fix, scan_origin="https://ex.com",
                                        identity_version=PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION) == "unresolvable_affected_evidence"


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



def test_confirmed_versioned_probe_is_observed_but_not_assessed():
    from app.coverage_probes import LINK_INTEGRITY_PROBE_VERSION

    fix = {
        "rule": "404_error",
        "page_template_family": "unknown",
        "affected_pages": ["/outside-sample"],
        "observed_evidence_version": LINK_INTEGRITY_PROBE_VERSION,
        "verified_observed_pages": ["/outside-sample"],
        "verification_state": "verified",
        "evidence_status": "confirmed",
    }
    context = build_coverage_context(
        fix,
        [page("/")],
        scan_origin="https://ex.com",
        identity_version=PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION,
    )

    assert context.affected_reported == 1
    assert context.affected_observed == 1
    assert context.affected_eligible == 0
    assert context.checked_eligible is None
    assert context.checked_coverage is None


@pytest.mark.parametrize(
    ("version", "verification_state", "evidence_status"),
    [
        ("unknown_probe_version", "verified", "confirmed"),
        ("link_integrity_probe_v1_unsampled_same_site", "not_verified", "confirmed"),
        ("link_integrity_probe_v1_unsampled_same_site", "verified", "needs_verification"),
    ],
)
def test_untrusted_or_unverified_probe_claim_does_not_inflate_observed_count(
    version, verification_state, evidence_status
):
    fix = {
        "rule": "404_error",
        "page_template_family": "unknown",
        "affected_pages": ["/outside-sample"],
        "observed_evidence_version": version,
        "verified_observed_pages": ["/outside-sample"],
        "verification_state": verification_state,
        "evidence_status": evidence_status,
    }
    context = build_coverage_context(
        fix,
        [page("/")],
        scan_origin="https://ex.com",
        identity_version=PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION,
    )

    assert context.affected_reported == 1
    assert context.affected_observed == 0
    assert context.affected_eligible == 0
    assert context.checked_coverage is None
