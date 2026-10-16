from __future__ import annotations

from typing import Any, Awaitable, Callable

from .coverage_probes import (
    SOFT_404_PROBE_VERSION,
    SharedCoverageProbeScheduler,
    build_soft_404_baseline_record,
    build_soft_404_probe_candidates,
    soft_404_signature_tokens,
)
from .robots_policy import SCANNER_USER_AGENT, annotate_robots_evidence


ACTIVE_SOFT404_ORCHESTRATION_VERSION = "active_soft404_orchestration_v1_shared_scheduler"
MAX_ACTIVE_SOFT404_BASELINE_RECORDS = 40


def _unique_nonempty(values: Any) -> list[str]:
    output: list[str] = []
    for value in values if isinstance(values, (list, tuple, set)) else []:
        cleaned = str(value or "").strip()
        if cleaned and cleaned not in output:
            output.append(cleaned)
    return output


def uniform_observed_group_provenance(members: list[dict]) -> dict[str, Any]:
    """Return group-level observed provenance only when every member agrees.

    A versioned member must never lend its authority to an unversioned member.
    The caller should remove inherited provenance from its lead/sample row before
    applying this return value.
    """
    if not members:
        return {}
    versions = [str(member.get("observed_evidence_version") or "").strip() for member in members]
    if any(not version for version in versions) or len(set(versions)) != 1:
        return {}
    verified = _unique_nonempty([
        page
        for member in members
        for page in (
            member.get("verified_observed_pages")
            if isinstance(member.get("verified_observed_pages"), list)
            else []
        )
    ])
    if not verified:
        return {}
    return {
        "observed_evidence_version": versions[0],
        "verified_observed_pages": verified,
    }


def _unknown_baseline(probe_url: str, metadata: dict, reason: str) -> dict[str, Any]:
    return build_soft_404_baseline_record(
        {
            "status_code": 0,
            "fetch_error": str(reason or "request_unverified")[:220],
        },
        probe_url,
        metadata,
    )


def _bounded_candidate_rows(
    origin: str,
    scope_prefix: str,
    pages: list[dict],
    max_candidates: int | None,
) -> list[dict[str, Any]]:
    """Return the deterministic eligible prefix selected for this shared-pool slice.

    The global ``SharedCoverageProbeScheduler`` remains the actual request bound.
    This local selection exists so B07 cannot monopolize the shared Stage-2 pool
    before B09/B16 have an opportunity to register their own bounded evidence.
    ``None`` preserves the historical helper behavior for existing callers/tests.
    """
    candidates = build_soft_404_probe_candidates(origin, scope_prefix, pages)
    if max_candidates is None:
        return candidates
    try:
        limit = int(max_candidates)
    except (TypeError, ValueError):
        limit = 0
    limit = max(0, min(MAX_ACTIVE_SOFT404_BASELINE_RECORDS, limit))
    return candidates[:limit]


async def collect_active_soft404_baselines(
    *,
    client: Any,
    pages: list[dict],
    origin: str,
    scope_prefix: str,
    robots_policy: Any,
    probe_scheduler: SharedCoverageProbeScheduler,
    fetch_page: Callable[..., Awaitable[dict]],
    max_candidates: int | None = None,
) -> list[dict[str, Any]]:
    """Collect bounded active soft-404 evidence through the shared probe pool.

    The returned records are follow-up evidence only. This function never mutates
    or appends to the assessed ``pages`` collection. Network requests are made
    only through ``probe_scheduler`` by passing its ``fetch_once`` method to the
    caller-supplied hardened fetch path.

    ``max_candidates`` optionally reserves the remainder of the *same* scheduler
    for other Stage-2 purposes. It does not create a second request allowance and
    therefore cannot increase the shared request budget.
    """
    for candidate in _bounded_candidate_rows(origin, scope_prefix, pages, max_candidates):
        probe_scheduler.register(
            purpose="soft_404_baseline",
            url=candidate["url"],
            metadata=candidate.get("metadata") or {},
        )

    baselines: list[dict[str, Any]] = []

    def retain(record: dict[str, Any]) -> None:
        if len(baselines) < MAX_ACTIVE_SOFT404_BASELINE_RECORDS:
            baselines.append(record)

    for candidate in probe_scheduler.candidates("soft_404_baseline"):
        target = str(candidate.get("url") or "")
        metadata = dict(candidate.get("metadata") or {})
        if not target:
            continue

        if not probe_scheduler.can_start_candidate("soft_404_baseline", target):
            reason = (
                "deadline_exhausted"
                if probe_scheduler.deadline_exhausted
                else "request_budget_exhausted"
            )
            probe_scheduler.record_exhausted(
                "soft_404_baseline",
                target,
                metadata=metadata,
            )
            retain(_unknown_baseline(target, metadata, reason))
            continue

        if robots_policy.allowed(SCANNER_USER_AGENT, target) is False:
            probe_scheduler.record_skipped(
                "soft_404_baseline",
                target,
                reason="blocked_by_robots_txt",
                metadata=metadata,
            )
            retain(_unknown_baseline(target, metadata, "blocked_by_robots_txt"))
            continue

        probe_scheduler.begin_candidate("soft_404_baseline")
        probe_page = await fetch_page(
            client,
            target,
            {
                "discovered_from": ["synthetic_soft_404_probe"],
                "source_pages": [],
                "link_text_samples": [],
            },
            robots_policy=robots_policy,
            request_provider=probe_scheduler.fetch_once,
        )
        if not isinstance(probe_page, dict):
            probe_page = {
                "status_code": 0,
                "fetch_error": "probe_fetch_returned_no_page",
            }
        annotate_robots_evidence(probe_page, robots_policy, target)
        baseline = build_soft_404_baseline_record(probe_page, target, metadata)
        if (
            baseline.get("version") == SOFT_404_PROBE_VERSION
            and baseline.get("state") == "fail"
            and baseline.get("reason") == "http_200_missing_intent_baseline"
        ):
            baseline["signature_tokens"] = soft_404_signature_tokens(probe_page)

        probe_scheduler.record_result(
            "soft_404_baseline",
            target,
            state=str(baseline.get("state") or "not_verified"),
            reason=str(baseline.get("reason") or "request_unverified"),
            status_code=int(baseline.get("status_code") or 0),
            final_url=str(probe_page.get("final_url") or target),
            metadata=metadata,
        )
        retain(baseline)

    return baselines
