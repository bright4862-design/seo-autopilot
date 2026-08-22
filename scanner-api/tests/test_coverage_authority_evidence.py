"""Patch B - coverage/inventory diagnostics, persisted without changing authority.

The 50-site production audit found three scans sealed as complete,
non-provisional and release-eligible on evidence that cannot support them:

    Tanners    38 of 3,689 discovered URLs  (1.0%)
    Decathlon  40 of 1,374 discovered URLs  (2.9%)
    Habito      1 page on a real multi-page mortgage site

Nothing in the durable record explains why those were acceptable, because the
counts that would explain them are never written: every completed ScanRun
inspected carried usable_html_page_count == 0 and
representative_html_page_count == 0 while claiming evidence quality 100 with
reason representative_html_evidence.

This patch makes the coverage question answerable. It does NOT answer it:
the assessment is observational, and every authority field keeps the value it
has today. Gating on it is a later patch, by design -- the audit's own
implementation order says to design the assessment before moving thresholds.

Evidence: docs/audit/2026-08-21-production-50-site/
"""
import pytest

from app.coverage_authority import (
    COVERAGE_AUTHORITY_EVIDENCE_VERSION,
    MIN_INVENTORY_FOR_RATIO_TEST,
    MIN_RETAINED_PAGES,
    MIN_RETAINED_RATIO,
    assess_coverage_authority,
    attach_coverage_authority_evidence,
)

AUTHORITY_FIELDS = (
    "scan_status",
    "review_confidence_state",
    "score_is_provisional",
    "release_gate_eligible",
    "evidence_quality_blocking",
    "evidence_quality_state",
    "evidence_quality_score",
    "health_score",
    "health_grade",
    "seo_score",
    "limitation",
    "next_best_step",
)


def page(path: str, *, words: int = 180, family: str = "standard", intent: str = "standard") -> dict:
    return {
        "url": f"https://example.com{path}",
        "final_url": f"https://example.com{path}",
        "path": path,
        "status_code": 200,
        "content_type": "text/html",
        "fetch_error": "",
        "title": "Useful page title",
        "h1": "Useful heading",
        "word_count": words,
        "page_template_family": family,
        "estimated_page_intent": intent,
    }


def payload(
    *,
    retained: int,
    discovered: int,
    crawled: int | None = None,
    sitemap_urls: int | None = None,
    sitemap_failures: dict | None = None,
    sitemap_fetch_count: int = 3,
    queue_exhausted: bool = False,
    crawl_deadline_reached: bool = False,
    failed_fetch_count: int = 0,
    queued_remaining: int = 0,
    pages: list[dict] | None = None,
) -> dict:
    body = pages if pages is not None else [page(f"/p{index}") for index in range(retained)]
    return {
        "website_url": "https://example.com/",
        "pages_found": discovered,
        "pages_crawled": crawled if crawled is not None else retained,
        "crawled_pages": body,
        "queued_remaining": queued_remaining,
        "crawl_timing": {
            "queue_exhausted": queue_exhausted,
            "crawl_deadline_reached": crawl_deadline_reached,
            "failed_fetch_count": failed_fetch_count,
            "final_url_duplicates_deduped": 0,
            "sitemap_fetch_count": sitemap_fetch_count,
            "sitemap_urls_discovered": discovered if sitemap_urls is None else sitemap_urls,
            "sitemap_failure_reason_buckets": sitemap_failures or {},
            "sitemap_budget_exhausted": False,
            "sitemap_fetch_limit_reached": False,
        },
    }


def complete_result() -> dict:
    return {
        "scan_status": "complete",
        "review_confidence_state": "complete",
        "score_is_provisional": False,
        "release_gate_eligible": True,
        "evidence_quality_blocking": False,
        "evidence_quality_state": "representative",
        "evidence_quality_score": 100,
        "health_score": 79,
        "seo_score": 79,
        "health_grade": "Good",
        "limitation": "",
        "next_best_step": "Keep going",
    }


# ------------------------------------------------------------- the contract --


def test_the_assessment_is_versioned():
    """Bumped in Patch C: the assessment now decides rather than only describes."""
    assert COVERAGE_AUTHORITY_EVIDENCE_VERSION == "coverage_authority_evidence_v2_authoritative"


def test_the_assessment_reports_the_full_inventory_chain():
    """target -> attempted -> retained, plus why the crawl stopped.

    A ratio alone cannot separate a valid 150/5,000 Standard sample from a
    crawl that died at 38 pages, so the record has to carry the chain.
    """
    evidence = assess_coverage_authority(payload(retained=150, discovered=5000, queued_remaining=120))
    inventory = evidence["inventory"]

    assert inventory["discovered_target"] == 5000
    assert inventory["attempted"] == 150
    assert inventory["retained_usable_html"] == 150
    assert inventory["queued_remaining"] == 120
    assert inventory["coverage_ratio"] == pytest.approx(0.03, abs=1e-6)
    assert evidence["terminal_reason"]
    assert evidence["coverage_authority_evidence_version"] == COVERAGE_AUTHORITY_EVIDENCE_VERSION


def test_the_record_carries_the_thresholds_that_judged_it():
    """A persisted verdict must stay readable after the thresholds move."""
    evidence = assess_coverage_authority(payload(retained=150, discovered=5000))
    assert evidence["thresholds"] == {
        "min_retained_pages": MIN_RETAINED_PAGES,
        "min_retained_ratio": MIN_RETAINED_RATIO,
        "min_inventory_for_ratio_test": MIN_INVENTORY_FOR_RATIO_TEST,
    }


# ------------------------------------------------ the three audit controls --


def test_tanners_is_advised_insufficient():
    evidence = assess_coverage_authority(payload(retained=38, discovered=3689))
    assert evidence["assessment"] == "insufficient_sample"
    assert evidence["would_gate_as_insufficient"] is True
    assert "retained_pages_below_minimum" in evidence["reasons"]
    assert "coverage_ratio_below_minimum" in evidence["reasons"]


def test_decathlon_is_advised_insufficient():
    evidence = assess_coverage_authority(payload(retained=40, discovered=1374))
    assert evidence["assessment"] == "insufficient_sample"
    assert evidence["would_gate_as_insufficient"] is True


def test_habito_single_page_on_a_real_site_is_advised_unproven():
    """One page, and nothing positively establishing that is the whole site."""
    evidence = assess_coverage_authority(
        payload(retained=1, discovered=1, sitemap_urls=0, sitemap_failures={"http_404": 1})
    )
    assert evidence["assessment"] == "single_page_inventory_unproven"
    assert evidence["would_gate_as_insufficient"] is True
    assert evidence["inventory_proof"]["positively_established"] is False


def test_a_single_page_that_is_not_a_meaningful_root_is_still_unproven():
    """The production hole the audit report did not name.

    evidence_quality only applies its one-page guard when the single page is a
    meaningful root; anything else falls through to the catch-all and is
    scored 81 as "representative", non-blocking. Habito persisted 81, not the
    small-site 85, so production took exactly this path. Coverage must not
    depend on that branch.
    """
    thin = page("/", words=4)
    thin.update({"title": "", "h1": ""})
    evidence = assess_coverage_authority(
        payload(retained=1, discovered=1, pages=[thin], sitemap_fetch_count=0)
    )
    assert evidence["assessment"] == "single_page_inventory_unproven"
    assert evidence["would_gate_as_insufficient"] is True


# ------------------------------------------------------- the controls that must pass --


def test_an_ordinary_standard_150_scan_stays_sufficient():
    """150/5,000 is 3%. A naive ratio gate rejects it, and would have rejected
    23 of the 30 completed audit scans. The gate is a conjunction."""
    evidence = assess_coverage_authority(payload(retained=150, discovered=5000, queued_remaining=400))
    assert evidence["assessment"] == "sufficient"
    assert evidence["would_gate_as_insufficient"] is False


def test_a_small_site_sample_above_the_ratio_stays_sufficient():
    """21/172 is 12.2%: few pages, but a real share of a small inventory."""
    evidence = assess_coverage_authority(payload(retained=21, discovered=172))
    assert evidence["assessment"] == "sufficient"
    assert evidence["would_gate_as_insufficient"] is False


def test_a_genuinely_small_site_with_a_working_sitemap_stays_sufficient():
    evidence = assess_coverage_authority(
        payload(retained=1, discovered=1, sitemap_urls=1, queue_exhausted=True)
    )
    assert evidence["assessment"] == "sufficient"
    assert evidence["inventory_proof"]["positively_established"] is True


def test_a_thin_inventory_below_the_ratio_test_floor_is_not_judged_on_ratio():
    """Under 100 discovered URLs the ratio is too noisy to mean anything."""
    evidence = assess_coverage_authority(payload(retained=8, discovered=40))
    assert evidence["assessment"] != "insufficient_sample"


# ------------------------------------------------------ authority is untouched --


@pytest.mark.parametrize(
    "case",
    [
        payload(retained=38, discovered=3689),
        payload(retained=40, discovered=1374),
        payload(retained=1, discovered=1, sitemap_urls=0, sitemap_failures={"http_404": 1}),
        payload(retained=150, discovered=5000),
    ],
)
def test_attaching_the_evidence_changes_no_authority_field(case):
    """Patch B observes. It does not gate, downgrade, or re-score."""
    before = complete_result()
    after = attach_coverage_authority_evidence(before, case)

    for field in AUTHORITY_FIELDS:
        assert after[field] == before[field], field


def test_attaching_the_evidence_adds_exactly_one_key():
    before = complete_result()
    after = attach_coverage_authority_evidence(before, payload(retained=38, discovered=3689))
    assert set(after) - set(before) == {"coverage_authority_evidence"}


def test_attaching_the_evidence_does_not_mutate_the_input():
    before = complete_result()
    attach_coverage_authority_evidence(before, payload(retained=38, discovered=3689))
    assert "coverage_authority_evidence" not in before


def test_an_unusable_payload_is_indeterminate_rather_than_a_false_verdict():
    """Absent diagnostics must not read as a proven-sufficient crawl."""
    evidence = assess_coverage_authority({})
    assert evidence["assessment"] == "no_usable_html"
    assert evidence["would_gate_as_insufficient"] is True
