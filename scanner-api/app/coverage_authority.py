"""Coverage and inventory diagnostics for a completed crawl.

The 50-site production audit sealed three scans as complete, non-provisional
and release-eligible on evidence that cannot support them: Tanners at 38 of
3,689 discovered URLs, Decathlon at 40 of 1,374, and Habito at a single page
on a real multi-page site. The durable record could not explain any of them,
because the counts that would explain them were never written.

This module answers "how much of this site did we actually see, and do we have
positive proof of how big it is" as a versioned, scanner-owned record. It is
deliberately observational: nothing here changes scan status, provisional
state, release eligibility, or score. Gating belongs to a later patch, and the
audit's own implementation order asks for the assessment to be designed first.

Two things the audit proved, which shape the rules below:

Ratio alone is useless. Across the 30 completed scans, "retained/discovered
below 10%" flags 23 of them, including every ordinary 150/5,000 Standard scan.
A valid Standard sample IS a small fraction of a large site. So the sample test
is a conjunction -- few pages retained AND a low share AND a real inventory to
have missed -- with 150/5,000 and 21/172 as the controls that must keep
passing.

Absence of evidence is not proof of a small site. A one-page result only means
a one-page site if something positively established the inventory. A sitemap
that 404s plus an empty link frontier produces exactly the same shape as a
genuinely single-page site, so the sitemap must have been fetched, and have
worked, before a single page can be called complete.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .evidence_quality import evaluate_evidence_quality

COVERAGE_AUTHORITY_EVIDENCE_VERSION = "coverage_authority_evidence_v1"

# Tactical thresholds from the audit report. All three must hold together
# before a sample is called insufficient.
MIN_RETAINED_PAGES = 50
MIN_RETAINED_RATIO = 0.10
MIN_INVENTORY_FOR_RATIO_TEST = 100


def _int(value: Any) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return 0
    return max(0, number)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _terminal_reason(payload: dict[str, Any], crawl_timing: dict[str, Any]) -> str:
    """Why the crawl stopped, in the order that a stop actually binds."""
    if crawl_timing.get("crawl_deadline_reached") is True:
        return "crawl_deadline_reached"
    if payload.get("scan_deadline_reached") is True:
        return "scan_deadline_reached"
    if crawl_timing.get("queue_exhausted") is True:
        return "queue_exhausted"
    if _int(payload.get("queued_remaining")) > 0:
        return "page_cap_reached"
    return "unknown"


def _inventory_proof(payload: dict[str, Any], crawl_timing: dict[str, Any]) -> dict[str, Any]:
    """Did anything positively establish how big this site is?

    Positive proof means the sitemap was actually fetched and actually worked,
    and the link frontier was walked to exhaustion without losing pages. A
    sitemap that was never fetched, or that failed, proves nothing about size
    -- which is the difference between a real one-page site and a site whose
    discovery was blocked.
    """
    failure_buckets = _dict(crawl_timing.get("sitemap_failure_reason_buckets"))
    sitemap_fetch_count = _int(crawl_timing.get("sitemap_fetch_count"))
    sitemap_failed = bool(
        failure_buckets
        or crawl_timing.get("sitemap_budget_exhausted") is True
        or crawl_timing.get("sitemap_fetch_limit_reached") is True
    )
    queue_exhausted = crawl_timing.get("queue_exhausted") is True
    failed_fetch_count = _int(crawl_timing.get("failed_fetch_count"))
    queued_remaining = _int(payload.get("queued_remaining"))

    positively_established = bool(
        sitemap_fetch_count > 0
        and not sitemap_failed
        and queue_exhausted
        and failed_fetch_count == 0
        and queued_remaining == 0
    )
    return {
        "sitemap_fetch_count": sitemap_fetch_count,
        "sitemap_urls_discovered": _int(crawl_timing.get("sitemap_urls_discovered")),
        "sitemap_failed": sitemap_failed,
        "sitemap_failure_reason_buckets": dict(failure_buckets),
        "sitemap_budget_exhausted": crawl_timing.get("sitemap_budget_exhausted") is True,
        "sitemap_fetch_limit_reached": crawl_timing.get("sitemap_fetch_limit_reached") is True,
        "queue_exhausted": queue_exhausted,
        "failed_fetch_count": failed_fetch_count,
        "positively_established": positively_established,
    }


def assess_coverage_authority(
    payload: dict[str, Any],
    quality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Describe crawl coverage. Never decides anything."""
    payload = _dict(payload)
    crawl_timing = _dict(payload.get("crawl_timing"))
    if quality is None:
        quality = evaluate_evidence_quality(payload)

    discovered = _int(payload.get("pages_found"))
    attempted = _int(payload.get("pages_crawled"))
    retained = _int(quality.get("usable_html_page_count"))
    representative = _int(quality.get("representative_html_page_count"))
    default_routes = _int(quality.get("default_route_page_count"))
    coverage_ratio = round(retained / discovered, 6) if discovered > 0 else None

    proof = _inventory_proof(payload, crawl_timing)
    reasons: list[str] = []

    if retained == 0:
        assessment = "no_usable_html"
        reasons.append("no_usable_html_pages")
    elif retained == 1 and not proof["positively_established"]:
        # One page is only a one-page site when something proved it. This is
        # checked before the sample test because a one-page inventory never
        # reaches the ratio floor and would otherwise pass silently.
        assessment = "single_page_inventory_unproven"
        reasons.append("single_page_inventory_unproven")
        if proof["sitemap_failed"]:
            reasons.append("sitemap_discovery_failed")
        elif proof["sitemap_fetch_count"] == 0:
            reasons.append("sitemap_never_fetched")
        if not proof["queue_exhausted"]:
            reasons.append("link_frontier_not_exhausted")
    elif (
        discovered >= MIN_INVENTORY_FOR_RATIO_TEST
        and retained < MIN_RETAINED_PAGES
        and coverage_ratio is not None
        and coverage_ratio < MIN_RETAINED_RATIO
    ):
        assessment = "insufficient_sample"
        reasons.extend(["retained_pages_below_minimum", "coverage_ratio_below_minimum"])
    else:
        assessment = "sufficient"
        reasons.append("coverage_within_expected_sampling_bounds")

    return {
        "coverage_authority_evidence_version": COVERAGE_AUTHORITY_EVIDENCE_VERSION,
        "assessment": assessment,
        # Advisory only. Patch B persists this; it does not act on it. The name
        # is deliberately conditional so a reader cannot mistake it for a gate.
        "would_gate_as_insufficient": assessment != "sufficient",
        "reasons": reasons,
        "inventory": {
            "discovered_target": discovered,
            "attempted": attempted,
            "retained_usable_html": retained,
            "retained_representative_html": representative,
            "default_route_pages": default_routes,
            "final_url_duplicates_deduped": _int(crawl_timing.get("final_url_duplicates_deduped")),
            "queued_remaining": _int(payload.get("queued_remaining")),
            "coverage_ratio": coverage_ratio,
        },
        "terminal_reason": _terminal_reason(payload, crawl_timing),
        "inventory_proof": proof,
        "thresholds": {
            "min_retained_pages": MIN_RETAINED_PAGES,
            "min_retained_ratio": MIN_RETAINED_RATIO,
            "min_inventory_for_ratio_test": MIN_INVENTORY_FOR_RATIO_TEST,
        },
    }


def attach_coverage_authority_evidence(
    result: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Add the coverage record to a review result and change nothing else.

    Deliberately separate from apply_evidence_quality_gate: that function
    decides, this one only describes. Keeping them apart is what makes "no
    authority change" checkable by reading the function rather than by
    trusting a test.
    """
    if not isinstance(result, dict):
        return result
    described = deepcopy(result)
    described["coverage_authority_evidence"] = assess_coverage_authority(payload)
    return described
