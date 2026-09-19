from __future__ import annotations

from typing import Any, Awaitable, Callable, Iterable
from urllib.parse import urlsplit

from .active_soft404_orchestration import collect_active_soft404_baselines
from .coverage_probes import build_soft_404_probe_candidates
from .robots_policy import SCANNER_USER_AGENT, annotate_robots_evidence
from .sitemap_integrity_evidence import (
    build_sitemap_source_evidence,
    classify_sitemap_target,
    register_sitemap_target_candidates,
    sitemap_coverage_from_scheduler,
)
from .stage2_probe_budget import allocate_stage2_probe_candidates
from .url_variant_evidence import (
    build_url_variant_candidates,
    classify_url_variant,
    register_url_variant_candidates,
    url_variant_coverage_from_scheduler,
)


STAGE2_SHARED_PROBE_ORCHESTRATION_VERSION = "stage2_shared_probe_orchestration_v1"


def _clean(value: Any, width: int = 2_000) -> str:
    return str(value or "").strip()[:width]


def _sitemap_entries(sitemap_urls: Iterable[str], diagnostics: Any) -> list[dict[str, str]]:
    """Return exact target→source rows when discovery retained them.

    A discovered sitemap target is still eligible for bounded verification when
    its exact source row is unavailable, but the row intentionally carries no
    invented sitemap URL. Downstream source evidence therefore stays unknown
    until exact provenance exists.
    """
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    source_rows = diagnostics.get("sitemap_target_sources") if isinstance(diagnostics, dict) else []
    for item in source_rows if isinstance(source_rows, list) else []:
        if not isinstance(item, dict):
            continue
        target = _clean(item.get("url"))
        source = _clean(item.get("sitemap_url"))
        if not target:
            continue
        key = (target, source)
        if key in seen:
            continue
        seen.add(key)
        rows.append({"url": target, "sitemap_url": source})

    mapped_targets = {row["url"] for row in rows}
    for value in sitemap_urls:
        target = _clean(value)
        if not target or target in mapped_targets:
            continue
        rows.append({"url": target, "sitemap_url": ""})
        mapped_targets.add(target)
    return rows


def _sitemap_provenance_complete(sitemap_urls: Iterable[str], diagnostics: Any) -> bool:
    discovered = {_clean(value) for value in sitemap_urls if _clean(value)}
    if not discovered:
        return True
    if not isinstance(diagnostics, dict) or diagnostics.get("sitemap_target_sources_truncated"):
        return False
    rows = diagnostics.get("sitemap_target_sources")
    if not isinstance(rows, list):
        return False
    mapped = {
        _clean(row.get("url"))
        for row in rows
        if isinstance(row, dict) and _clean(row.get("url")) and _clean(row.get("sitemap_url"))
    }
    return discovered.issubset(mapped)


def _variant_desired_count(rows: list[dict[str, Any]]) -> int:
    return max([int(row.get("eligible_candidate_count") or 0) for row in rows] or [0])


def _source_page_index(pages: list[dict]) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for page in pages:
        if not isinstance(page, dict):
            continue
        for key in ("url", "request_url"):
            value = _clean(page.get(key))
            if value and value not in index:
                index[value] = page
    return index


def _unknown_page(reason: str) -> dict[str, Any]:
    return {
        "status_code": 0,
        "fetch_error": _clean(reason, 220) or "request_unverified",
        "page_evidence_class": "failed_access",
    }


async def _fetch_registered_probe(
    *,
    client: Any,
    scheduler: Any,
    purpose: str,
    candidate: dict[str, Any],
    robots_policy: Any,
    fetch_page: Callable[..., Awaitable[dict]],
) -> tuple[dict[str, Any], bool]:
    """Fetch one registered candidate through the existing scheduler only.

    The boolean return says whether the scheduler already received a terminal
    skipped/exhausted observation. Normal response classification is deliberately
    left to the feature-specific B09/B16 evidence functions.
    """
    target = _clean(candidate.get("url"))
    source_pages = candidate.get("source_pages") or []
    metadata = candidate.get("metadata") or {}
    if not target:
        return _unknown_page("candidate_url_missing"), False

    if not scheduler.can_start_candidate(purpose, target):
        reason = "deadline_exhausted" if scheduler.deadline_exhausted else "request_budget_exhausted"
        scheduler.record_exhausted(
            purpose,
            target,
            source_pages=source_pages,
            metadata=metadata,
        )
        return _unknown_page(reason), True

    if robots_policy.allowed(SCANNER_USER_AGENT, target) is False:
        scheduler.record_skipped(
            purpose,
            target,
            reason="blocked_by_robots_txt",
            source_pages=source_pages,
            metadata=metadata,
        )
        return _unknown_page("blocked_by_robots_txt"), True

    scheduler.begin_candidate(purpose)
    try:
        page = await fetch_page(
            client,
            target,
            {
                "discovered_from": [f"stage2_{purpose}_probe"],
                "source_pages": list(source_pages),
                "link_text_samples": [],
            },
            robots_policy=robots_policy,
            request_provider=scheduler.fetch_once,
        )
    except RuntimeError as exc:
        reason = str(exc or "")
        if reason in {"coverage_probe_deadline_exhausted", "coverage_probe_request_budget_exhausted"}:
            scheduler.record_exhausted(
                purpose,
                target,
                source_pages=source_pages,
                metadata=metadata,
            )
            return _unknown_page(
                "deadline_exhausted"
                if reason == "coverage_probe_deadline_exhausted"
                else "request_budget_exhausted"
            ), True
        page = _unknown_page("request_unverified")
    except Exception:
        page = _unknown_page("request_unverified")

    if not isinstance(page, dict):
        page = _unknown_page("probe_fetch_returned_no_page")
    annotate_robots_evidence(page, robots_policy, target)
    return page, False


def _record_classification(
    scheduler: Any,
    *,
    purpose: str,
    candidate: dict[str, Any],
    evidence: dict[str, Any],
    page: dict[str, Any],
) -> None:
    scheduler.record_result(
        purpose,
        _clean(candidate.get("url")),
        state=_clean(evidence.get("state"), 100) or "not_verified",
        reason=_clean(evidence.get("reason"), 220) or "response_unverified",
        status_code=int(evidence.get("status_code") or page.get("status_code") or 0),
        final_url=_clean(evidence.get("final_url") or page.get("final_url") or candidate.get("url")),
        source_pages=candidate.get("source_pages") or [],
        metadata=candidate.get("metadata") or {},
    )


def _aggregate_variant_evidence(rows: list[dict[str, Any]]) -> tuple[str, str]:
    if not rows:
        return "not_verified", "variant_pair_evidence_unavailable"
    states = {_clean(row.get("state"), 100) or "not_verified" for row in rows}
    if "fail" in states:
        return "fail", "one_or_more_variant_pairs_failed"
    if "not_verified" in states or any(state not in {"pass", "fail"} for state in states):
        return "not_verified", "one_or_more_variant_pairs_unverified"
    return "pass", "registered_variant_pairs_checked"


async def run_stage2_shared_probe_orchestration(
    *,
    client: Any,
    pages: list[dict],
    sitemap_urls: Iterable[str],
    sitemap_diagnostics: Any,
    origin: str,
    scope_prefix: str,
    robots_policy: Any,
    probe_scheduler: Any,
    fetch_page: Callable[..., Awaitable[dict]],
    verified_alias_origins: Iterable[str] | None = None,
    meaningful_parameter_variants: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run B07/B09/B16 follow-up evidence through one already-owned scheduler.

    This is a producer adapter, not a second crawler. It registers every selected
    B07/B09/B16 candidate on the existing ``SharedCoverageProbeScheduler`` before
    any follow-up request starts, then uses that scheduler as the sole request
    provider. Probe-only URLs are never appended to ``pages`` and therefore can
    never change Standard 150 assessed-page counts.

    The allocator only selects candidate starts from the scheduler's remaining
    allowance. Redirect hops still spend that same finite request pool; if they
    consume the remainder, later purposes are recorded as exhausted/unknown
    rather than silently disappearing or being treated as checked.
    """
    assessed_count_before = len(pages)
    assessed_urls = [_clean(page.get("url")) for page in pages if isinstance(page, dict) and _clean(page.get("url"))]
    sitemap_entries = _sitemap_entries(sitemap_urls, sitemap_diagnostics)

    soft404_candidates = build_soft_404_probe_candidates(origin, scope_prefix, pages)
    sitemap_preview = register_sitemap_target_candidates(
        probe_scheduler,
        sitemap_entries,
        assessed_urls=assessed_urls,
        origin=origin,
        scope_prefix=scope_prefix,
        max_candidates=0,
    )
    variant_preview = build_url_variant_candidates(
        assessed_urls,
        origin=origin,
        scope_prefix=scope_prefix,
        verified_alias_origins=verified_alias_origins,
        meaningful_parameter_variants=meaningful_parameter_variants,
        max_candidates=100,
    )
    desired_variants = _variant_desired_count(variant_preview)

    allocation = allocate_stage2_probe_candidates(
        probe_scheduler.summary(),
        {
            "soft_404_baseline": len(soft404_candidates),
            "sitemap_target": int(sitemap_preview.get("eligible_unsampled") or 0),
            "url_variant": desired_variants,
        },
    )
    allocated = allocation.get("allocated") or {}

    for candidate in soft404_candidates[: max(0, int(allocated.get("soft_404_baseline") or 0))]:
        probe_scheduler.register(
            purpose="soft_404_baseline",
            url=_clean(candidate.get("url")),
            metadata=candidate.get("metadata") or {},
        )

    sitemap_registration = register_sitemap_target_candidates(
        probe_scheduler,
        sitemap_entries,
        assessed_urls=assessed_urls,
        origin=origin,
        scope_prefix=scope_prefix,
        max_candidates=max(0, int(allocated.get("sitemap_target") or 0)),
    )
    selected_variants = build_url_variant_candidates(
        assessed_urls,
        origin=origin,
        scope_prefix=scope_prefix,
        verified_alias_origins=verified_alias_origins,
        meaningful_parameter_variants=meaningful_parameter_variants,
        max_candidates=max(0, int(allocated.get("url_variant") or 0)),
    )
    register_url_variant_candidates(probe_scheduler, selected_variants, scope_prefix=scope_prefix)

    # All three purposes are now visible to the single scheduler before any
    # follow-up I/O starts. B07's existing helper can therefore fetch only the
    # pre-registered allocation while leaving B09/B16 as explicit eligible work.
    soft404_baselines = await collect_active_soft404_baselines(
        client=client,
        pages=pages,
        origin=origin,
        scope_prefix=scope_prefix,
        robots_policy=robots_policy,
        probe_scheduler=probe_scheduler,
        fetch_page=fetch_page,
        max_candidates=0,
    )

    sitemap_target_evidence: list[dict[str, Any]] = []
    for candidate in probe_scheduler.candidates("sitemap_target"):
        page, terminal_recorded = await _fetch_registered_probe(
            client=client,
            scheduler=probe_scheduler,
            purpose="sitemap_target",
            candidate=candidate,
            robots_policy=robots_policy,
            fetch_page=fetch_page,
        )
        evidence = classify_sitemap_target(
            page,
            requested_url=_clean(candidate.get("url")),
            sitemap_sources=candidate.get("source_pages") or [],
        )
        sitemap_target_evidence.append(evidence)
        if not terminal_recorded:
            _record_classification(
                probe_scheduler,
                purpose="sitemap_target",
                candidate=candidate,
                evidence=evidence,
                page=page,
            )

    variants_by_probe: dict[str, list[dict[str, Any]]] = {}
    for row in selected_variants:
        variants_by_probe.setdefault(_clean(row.get("probe_url")), []).append(row)
    assessed_index = _source_page_index(pages)
    variant_evidence: list[dict[str, Any]] = []
    for candidate in probe_scheduler.candidates("url_variant"):
        page, terminal_recorded = await _fetch_registered_probe(
            client=client,
            scheduler=probe_scheduler,
            purpose="url_variant",
            candidate=candidate,
            robots_policy=robots_policy,
            fetch_page=fetch_page,
        )
        pair_rows: list[dict[str, Any]] = []
        for row in variants_by_probe.get(_clean(candidate.get("url")), []):
            pair = classify_url_variant(
                assessed_index.get(_clean(row.get("source_url"))),
                page,
                row,
            )
            variant_evidence.append(pair)
            pair_rows.append(pair)
        if not terminal_recorded:
            state, reason = _aggregate_variant_evidence(pair_rows)
            _record_classification(
                probe_scheduler,
                purpose="url_variant",
                candidate=candidate,
                evidence={"state": state, "reason": reason},
                page=page,
            )

    summary = probe_scheduler.summary()
    sitemap_coverage = sitemap_coverage_from_scheduler(summary, registration=sitemap_registration)
    variant_coverage = url_variant_coverage_from_scheduler(summary, candidates=selected_variants)
    if desired_variants > len(selected_variants):
        variant_coverage = {
            **variant_coverage,
            "state": "not_verified",
            "reason": "candidate_universe_truncated_by_shared_allocation",
            "eligible_candidate_count": desired_variants,
            "candidate_universe_truncated": True,
        }

    summary.update({
        "stage2_orchestration_version": STAGE2_SHARED_PROBE_ORCHESTRATION_VERSION,
        "stage2_probe_allocation": allocation,
        "soft_404_baselines": soft404_baselines,
        "sitemap_integrity": {
            "registration": sitemap_registration,
            "source_evidence": build_sitemap_source_evidence(sitemap_diagnostics),
            "target_evidence": sitemap_target_evidence,
            "coverage": sitemap_coverage,
            "target_provenance_complete": _sitemap_provenance_complete(sitemap_urls, sitemap_diagnostics),
        },
        "url_variants": {
            "candidates": selected_variants,
            "evidence": variant_evidence,
            "coverage": variant_coverage,
        },
        "assessed_page_count_before": assessed_count_before,
        "assessed_page_count_after": len(pages),
        "assessed_page_count_unchanged": len(pages) == assessed_count_before,
        "single_shared_scheduler": True,
    })
    return summary
