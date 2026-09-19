from __future__ import annotations

from typing import Any, Mapping


STAGE2_PROBE_ALLOCATION_VERSION = "stage2_probe_allocation_v1_shared_remaining_budget"
STAGE2_PROBE_PURPOSE_ORDER = (
    "soft_404_baseline",
    "sitemap_target",
    "url_variant",
)


def _nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def remaining_shared_probe_requests(scheduler_summary: Any) -> int:
    """Read the already-existing scheduler's remaining request capacity.

    This helper never derives a second allowance. Missing or malformed scheduler
    evidence fails closed to zero so later Stage-2 features cannot escape the
    single shared request pool.
    """
    if not isinstance(scheduler_summary, dict):
        return 0
    request_budget = scheduler_summary.get("request_budget")
    if not isinstance(request_budget, dict):
        return 0
    return _nonnegative_int(request_budget.get("requests_remaining"))


def allocate_stage2_probe_candidates(
    scheduler_summary: Any,
    desired_counts: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Fairly reserve candidate starts inside the scheduler's remaining pool.

    B06 internal-link verification may have consumed part of the finite probe
    pool already. B07/B09/B16 therefore receive only the remaining capacity.
    Allocation is deterministic round-robin across the three approved purposes,
    never exceeds a purpose's eligible candidate count, and never increases the
    scheduler's own request allowance.
    """
    remaining = remaining_shared_probe_requests(scheduler_summary)
    desired_source = desired_counts if isinstance(desired_counts, Mapping) else {}
    desired = {
        purpose: _nonnegative_int(desired_source.get(purpose))
        for purpose in STAGE2_PROBE_PURPOSE_ORDER
    }
    allocated = {purpose: 0 for purpose in STAGE2_PROBE_PURPOSE_ORDER}

    capacity = remaining
    while capacity > 0:
        progressed = False
        for purpose in STAGE2_PROBE_PURPOSE_ORDER:
            if capacity <= 0:
                break
            if allocated[purpose] >= desired[purpose]:
                continue
            allocated[purpose] += 1
            capacity -= 1
            progressed = True
        if not progressed:
            break

    return {
        "version": STAGE2_PROBE_ALLOCATION_VERSION,
        "shared_requests_remaining_before_allocation": remaining,
        "desired": desired,
        "allocated": allocated,
        "allocated_total": sum(allocated.values()),
        "unallocated_shared_capacity": capacity,
        "single_shared_budget": True,
    }
