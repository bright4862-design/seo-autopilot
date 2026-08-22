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


COVERAGE_AUTHORITY_EVIDENCE_VERSION = "coverage_authority_evidence_v2_authoritative"

# The assessment now decides, so it is its own release component.
COVERAGE_AUTHORITY_VERSION = "coverage_authority_v1_shared_decision"

# Closed vocabulary. review.py and evidence_quality.py must both speak it, and
# neither may invent a state of its own.
COVERAGE_STATES = ("sufficient", "limited_coverage", "inventory_unproven", "access_limited")

# A crawl that is mostly challenges is access-limited, not thin. The customer
# needs the real reason, and a coverage ratio would hide it.
ACCESS_LIMITED_BLOCKED_RATIO = 0.5

# Below this, a sample cannot stand on its own: it is only trustworthy if an
# inventory source positively proves the site really is that small.
MIN_SELF_SUFFICIENT_PAGES = 4

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



def _sources(raw: Any) -> list[dict[str, Any]]:
    return [item for item in (raw or []) if isinstance(item, dict)]


def assess_coverage(inputs: dict[str, Any]) -> dict[str, Any]:
    """The one coverage decision, from explicit counts.

    Pure by construction: it takes numbers rather than a scan payload, so
    review.py and evidence_quality.py can both call it without either importing
    the other, and without a second opinion existing anywhere. It never mutates
    its argument.
    """
    inputs = _dict(inputs)
    discovered = _int(inputs.get("discovered"))
    attempted = _int(inputs.get("attempted"))
    retained = _int(inputs.get("retained_usable_html"))
    duplicates = _int(inputs.get("final_url_duplicates_deduped"))
    queued_remaining = _int(inputs.get("queued_remaining"))
    blocked = _int(inputs.get("blocked_or_429_pages"))
    coverage_ratio = round(retained / discovered, 6) if discovered > 0 else None

    sources = _sources(inputs.get("sitemap_sources"))
    truncated = bool(
        inputs.get("sitemap_budget_exhausted") is True
        or inputs.get("sitemap_fetch_limit_reached") is True
    )
    # Proof is judged per source. A speculative /sitemap.xml that 404s says
    # nothing about a robots-declared sitemap that worked, so a failure only
    # discredits the source it happened to, never the set.
    working = [source for source in sources if source.get("outcome") == "urls"]
    # Every URL the crawler took off the queue is accounted for, whether or not
    # it yielded usable HTML. A rate-limited page is explained evidence, not a
    # missing page, so accounting must compare against what was attempted.
    accounted = discovered <= attempted + duplicates
    positively_established = bool(working and not truncated and accounted)

    proof = {
        "sources": [dict(source) for source in sources],
        "working_source_count": len(working),
        "truncated_by_budget_or_limit": truncated,
        "discovered_accounted_for": accounted,
        "positively_established": positively_established,
    }

    reasons: list[str] = []

    if retained == 0:
        state = "access_limited" if blocked else "inventory_unproven"
        reasons.append("access_limited" if blocked else "no_usable_html_pages")
    elif blocked and blocked / max(retained + blocked, 1) >= ACCESS_LIMITED_BLOCKED_RATIO:
        state = "access_limited"
        reasons.append("access_limited")
    elif retained < MIN_SELF_SUFFICIENT_PAGES and not positively_established:
        # A handful of pages only means a small site if something proved the
        # site is small. Queue exhaustion and zero fetch errors are not proof:
        # they are equally consistent with discovery having been blocked.
        state = "inventory_unproven"
        reasons.append("small_site_inventory_unproven")
        if not working:
            reasons.append("no_working_inventory_source")
        if truncated:
            reasons.append("inventory_source_truncated")
        if not accounted:
            reasons.append("discovered_urls_unaccounted")
    elif (
        discovered >= MIN_INVENTORY_FOR_RATIO_TEST
        and retained < MIN_RETAINED_PAGES
        and coverage_ratio is not None
        and coverage_ratio < MIN_RETAINED_RATIO
    ):
        state = "limited_coverage"
        reasons.extend(["retained_pages_below_minimum", "coverage_ratio_below_minimum"])
    elif discovered < MIN_INVENTORY_FOR_RATIO_TEST and not accounted:
        # Below the inventory floor a ratio is too noisy to mean anything, so
        # the question becomes whether the discovered URLs were accounted for at
        # all. Above the floor the ratio has already decided, which is what
        # keeps 21/172 sufficient rather than second-guessing it here.
        state = "inventory_unproven"
        reasons.append("discovered_urls_unaccounted")
    else:
        state = "sufficient"
        reasons.append("coverage_within_expected_sampling_bounds")

    sufficient = state == "sufficient"
    return {
        "coverage_authority_version": COVERAGE_AUTHORITY_VERSION,
        "state": state,
        "reasons": reasons,
        "authoritative": sufficient,
        "score_is_provisional": not sufficient,
        "release_gate_eligible": sufficient,
        "inventory": {
            "discovered_target": discovered,
            "attempted": attempted,
            "retained_usable_html": retained,
            "final_url_duplicates_deduped": duplicates,
            "queued_remaining": queued_remaining,
            "blocked_or_429_pages": blocked,
            "coverage_ratio": coverage_ratio,
        },
        "inventory_proof": proof,
        "thresholds": {
            "min_retained_pages": MIN_RETAINED_PAGES,
            "min_retained_ratio": MIN_RETAINED_RATIO,
            "min_inventory_for_ratio_test": MIN_INVENTORY_FOR_RATIO_TEST,
            "access_limited_blocked_ratio": ACCESS_LIMITED_BLOCKED_RATIO,
        },
    }



def coverage_inputs_from_payload(
    payload: dict[str, Any],
    *,
    retained_usable_html: int,
    blocked_or_429_pages: int = 0,
) -> dict[str, Any]:
    """Build the shared assessment's inputs from a scan payload.

    One adapter, so review.py and evidence_quality.py cannot read the same crawl
    into two different sets of numbers and reach two different verdicts.
    """
    payload = _dict(payload)
    crawl_timing = _dict(payload.get("crawl_timing"))
    return {
        "discovered": _int(payload.get("pages_found")),
        "attempted": _int(payload.get("pages_crawled")),
        "retained_usable_html": _int(retained_usable_html),
        "final_url_duplicates_deduped": _int(crawl_timing.get("final_url_duplicates_deduped")),
        "queued_remaining": _int(payload.get("queued_remaining")),
        "queue_exhausted": crawl_timing.get("queue_exhausted") is True,
        "failed_fetch_count": _int(crawl_timing.get("failed_fetch_count")),
        "blocked_or_429_pages": _int(blocked_or_429_pages),
        "sitemap_sources": crawl_timing.get("sitemap_sources") or [],
        "sitemap_budget_exhausted": crawl_timing.get("sitemap_budget_exhausted") is True,
        "sitemap_fetch_limit_reached": crawl_timing.get("sitemap_fetch_limit_reached") is True,
    }


def assess_coverage_authority(
    payload: dict[str, Any],
    quality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Describe crawl coverage. Never decides anything."""
    # Local import: evidence_quality consumes the shared decision below, so a
    # module-level import here would close the cycle.
    from .evidence_quality import evaluate_evidence_quality

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
