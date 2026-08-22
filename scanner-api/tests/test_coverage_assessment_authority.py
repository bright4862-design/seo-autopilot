"""Patch C part 1 - one shared coverage decision, and it is authoritative.

Patch B recorded the coverage question. This answers it: a materially thin or
inventory-unproven crawl can no longer read as complete and release-eligible.

The audit controls, from docs/audit/2026-08-21-production-50-site/:

    Tanners    38 / 3,689  ->  limited, provisional, ineligible
    Decathlon  40 / 1,374  ->  limited, provisional, ineligible
    Habito      1 page     ->  inventory unproven, limited
    Standard  150 / 5,000  ->  sufficient (a deliberate cap, not a thin crawl)
    Pretto-like 21 / 172   ->  sufficient (12.2% of a small inventory)

review.py and evidence_quality.py must reach that verdict through one shared
module. Two modules with two opinions is how the fleet ended up asserting
evidence quality 100 on a 1% sample in the first place.
"""
import pytest

from app.coverage_authority import (
    COVERAGE_AUTHORITY_VERSION,
    COVERAGE_STATES,
    assess_coverage,
)


def sitemap_source(*, declared=True, outcome="urls", loc_count=120):
    return {
        "url": "https://example.com/sitemap.xml",
        "source": "robots_declared" if declared else "speculative_default",
        "outcome": outcome,
        "loc_count": loc_count,
    }


def inputs(
    *,
    discovered,
    retained,
    attempted=None,
    sources=None,
    queue_exhausted=True,
    failed_fetch_count=0,
    queued_remaining=0,
    duplicates=0,
    blocked=0,
    budget_exhausted=False,
    fetch_limit_reached=False,
):
    return {
        "discovered": discovered,
        "attempted": attempted if attempted is not None else retained,
        "retained_usable_html": retained,
        "final_url_duplicates_deduped": duplicates,
        "queued_remaining": queued_remaining,
        "queue_exhausted": queue_exhausted,
        "failed_fetch_count": failed_fetch_count,
        "blocked_or_429_pages": blocked,
        "sitemap_sources": sources if sources is not None else [sitemap_source()],
        "sitemap_budget_exhausted": budget_exhausted,
        "sitemap_fetch_limit_reached": fetch_limit_reached,
    }


# --------------------------------------------------------- the vocabulary --


def test_the_assessment_is_versioned_and_its_states_are_closed():
    assert COVERAGE_AUTHORITY_VERSION.startswith("coverage_authority_")
    assert COVERAGE_STATES == ("sufficient", "limited_coverage", "inventory_unproven", "access_limited")


def test_every_verdict_uses_a_declared_state_and_carries_reason_codes():
    verdict = assess_coverage(inputs(discovered=3689, retained=38))
    assert verdict["state"] in COVERAGE_STATES
    assert verdict["reasons"] and all(isinstance(code, str) for code in verdict["reasons"])
    assert verdict["coverage_authority_version"] == COVERAGE_AUTHORITY_VERSION


# ------------------------------------------------------- the audit failures --


@pytest.mark.parametrize(
    ("label", "retained", "discovered"),
    [("tanners", 38, 3689), ("decathlon", 40, 1374), ("existing", 7, 900)],
)
def test_a_materially_thin_sample_is_limited_not_authoritative(label, retained, discovered):
    verdict = assess_coverage(inputs(discovered=discovered, retained=retained))

    assert verdict["state"] == "limited_coverage", label
    assert verdict["authoritative"] is False
    assert verdict["score_is_provisional"] is True
    assert verdict["release_gate_eligible"] is False
    assert "retained_pages_below_minimum" in verdict["reasons"]


def test_a_single_page_with_no_working_inventory_source_is_unproven():
    """Habito: sitemap 404, empty frontier, one page. Not a one-page site."""
    verdict = assess_coverage(inputs(
        discovered=1, retained=1,
        sources=[sitemap_source(declared=False, outcome="failed", loc_count=0)],
    ))

    assert verdict["state"] == "inventory_unproven"
    assert verdict["authoritative"] is False
    assert verdict["release_gate_eligible"] is False


def test_a_single_page_with_no_sitemap_attempt_at_all_is_unproven():
    verdict = assess_coverage(inputs(discovered=1, retained=1, sources=[]))
    assert verdict["state"] == "inventory_unproven"


# ------------------------------------------------- the controls that must hold --


def test_the_standard_150_cap_stays_sufficient():
    """150/5,000 is 3%. It is a deliberate cap, not a failed crawl."""
    verdict = assess_coverage(inputs(
        discovered=5000, retained=150, queued_remaining=400, queue_exhausted=False,
    ))

    assert verdict["state"] == "sufficient"
    assert verdict["authoritative"] is True
    assert verdict["release_gate_eligible"] is True


def test_a_small_inventory_above_the_ratio_stays_sufficient():
    """21/172 is 12.2%: few pages, but a real share of a small site."""
    verdict = assess_coverage(inputs(discovered=172, retained=21))
    assert verdict["state"] == "sufficient"
    assert verdict["authoritative"] is True


def test_a_proven_one_page_site_stays_sufficient():
    verdict = assess_coverage(inputs(
        discovered=1, retained=1, sources=[sitemap_source(loc_count=1)],
    ))
    assert verdict["state"] == "sufficient"
    assert verdict["inventory_proof"]["positively_established"] is True


def test_a_thin_inventory_below_the_ratio_floor_is_not_judged_on_ratio():
    verdict = assess_coverage(inputs(discovered=40, retained=8))
    assert verdict["state"] != "limited_coverage"


# ------------------------------------------- proof is judged per source --


def test_a_failed_default_probe_does_not_invalidate_a_working_robots_sitemap():
    """The blueprint's mixed case, stated explicitly.

    Plenty of sites declare a sitemap in robots.txt and serve nothing at
    /sitemap.xml. Judging proof from the union of failures would call those
    sites unproven on the strength of a probe that was only ever speculative.
    """
    verdict = assess_coverage(inputs(
        discovered=1, retained=1,
        sources=[
            sitemap_source(declared=True, outcome="urls", loc_count=1),
            sitemap_source(declared=False, outcome="failed", loc_count=0),
        ],
    ))

    assert verdict["state"] == "sufficient"
    assert verdict["inventory_proof"]["positively_established"] is True
    # Both observations survive; nothing is discarded to reach the verdict.
    assert len(verdict["inventory_proof"]["sources"]) == 2


def test_a_source_truncated_by_its_own_budget_does_not_prove_an_inventory():
    verdict = assess_coverage(inputs(
        discovered=1, retained=1,
        sources=[sitemap_source(loc_count=1)],
        budget_exhausted=True,
    ))
    assert verdict["state"] == "inventory_unproven"


def test_a_source_cut_short_by_the_fetch_limit_does_not_prove_an_inventory():
    verdict = assess_coverage(inputs(
        discovered=1, retained=1,
        sources=[sitemap_source(loc_count=1)],
        fetch_limit_reached=True,
    ))
    assert verdict["state"] == "inventory_unproven"


def test_unaccounted_discovered_urls_contradict_a_small_site_claim():
    """Queue exhausted and a working sitemap, but pages went missing."""
    verdict = assess_coverage(inputs(discovered=40, retained=3, duplicates=0))
    assert verdict["state"] == "inventory_unproven"
    assert "discovered_urls_unaccounted" in verdict["reasons"]


def test_deduplicated_urls_count_toward_the_accounting():
    verdict = assess_coverage(inputs(discovered=5, retained=3, duplicates=2))
    assert verdict["state"] == "sufficient"


# ------------------------------------------------------------ access limits --


def test_a_predominantly_blocked_crawl_is_access_limited_not_thin():
    """The customer needs the real reason, not a coverage number."""
    verdict = assess_coverage(inputs(discovered=800, retained=4, blocked=40))

    assert verdict["state"] == "access_limited"
    assert verdict["authoritative"] is False
    assert "access_limited" in verdict["reasons"]


def test_no_usable_html_is_never_authoritative():
    verdict = assess_coverage(inputs(discovered=900, retained=0))
    assert verdict["authoritative"] is False
    assert verdict["release_gate_eligible"] is False


# ------------------------------------------------------- one shared decision --


def test_review_and_evidence_quality_consume_the_same_module():
    """Neither may invent a second coverage opinion."""
    from pathlib import Path

    app = Path(__file__).resolve().parents[1] / "app"
    for module in ("review.py", "evidence_quality.py"):
        source = (app / module).read_text(encoding="utf-8")
        assert "coverage_authority" in source, f"{module} does not use the shared assessment"


def test_the_assessment_is_pure():
    """Same inputs, same verdict, and the caller's dict is never mutated."""
    payload = inputs(discovered=3689, retained=38)
    snapshot = dict(payload)
    first = assess_coverage(payload)
    second = assess_coverage(payload)

    assert first == second
    assert payload == snapshot
