"""Pure, shadow-only helpers for adaptive crawl planning and selection.

Nothing in this module performs network I/O or changes the production Standard 150
budget. The serialized integrator may later wire these helpers behind an opt-in
next-generation mode.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from .sampling import (
    MONEY_FAMILIES,
    is_trust_path,
    route_signature,
    select_balanced_urls,
    strip_locale_prefix,
)

ADAPTIVE_CRAWL_VERSION = "adaptive_crawl_v1_shadow"
ADAPTIVE_SCORE_VERSION = "adaptive_candidate_score_v1"
ADAPTIVE_TELEMETRY_VERSION = "adaptive_tranche_yield_v1"
ADAPTIVE_BENCHMARK_VERSION = "adaptive_benchmark_v1"
STANDARD_150_TARGET = 150
MAX_ADAPTIVE_TARGET = 1000
DEFAULT_TRANCHE_TARGETS = (150, 500, 1000)


def _unique_urls(urls: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in urls:
        url = str(raw or "").strip()
        if url and url not in seen:
            seen.add(url)
            ordered.append(url)
    return ordered


def _top_prefix(path: str) -> str:
    normalized = strip_locale_prefix(str(path or "/"))
    segments = [segment for segment in normalized.split("/") if segment]
    return f"/{segments[0].lower()}" if segments else "/"


def _bounded_unit(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return max(0.0, min(1.0, number))


def _normalized_targets(candidate_targets: Sequence[int]) -> list[int]:
    normalized: set[int] = set()
    for raw_target in candidate_targets:
        try:
            target = int(raw_target)
        except (TypeError, ValueError, OverflowError):
            continue
        if target > 0:
            normalized.add(min(MAX_ADAPTIVE_TARGET, target))
    return sorted(normalized)


def plan_tranche_targets(
    discovered_urls: int,
    *,
    ceiling: int = MAX_ADAPTIVE_TARGET,
    candidate_targets: Sequence[int] = DEFAULT_TRANCHE_TARGETS,
) -> dict[str, Any]:
    """Return bounded assessment targets without claiming discovery is complete.

    The caller may request a smaller ceiling, but this pure lane deliberately cannot
    authorize more than ``MAX_ADAPTIVE_TARGET`` pages. A future higher cap would need
    an explicit contract/version change plus serialized-integrator budget review.
    """
    discovered = max(0, int(discovered_urls or 0))
    requested_ceiling = max(0, int(ceiling or 0))
    hard_ceiling = min(requested_ceiling, MAX_ADAPTIVE_TARGET)
    bound = min(discovered, hard_ceiling)
    normalized = _normalized_targets(candidate_targets)
    if bound <= 0 or not normalized:
        targets: list[int] = []
    else:
        targets = sorted({min(bound, target) for target in normalized if target > 0})
        if bound not in targets:
            targets.append(bound)
            targets.sort()
    return {
        "version": ADAPTIVE_CRAWL_VERSION,
        "discovered_urls": discovered,
        "requested_ceiling": requested_ceiling,
        "assessment_ceiling": hard_ceiling,
        "targets": targets,
        "discovery_scope_complete": False,
    }


def adaptive_candidate_score(
    url: str,
    *,
    family: str,
    path: str,
    covered_families: set[str],
    covered_signatures: set[str],
    covered_prefixes: set[str],
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Score one already-discovered URL using only supplied evidence."""
    meta = metadata or {}
    score = 0.0
    reasons: list[str] = []
    signature = route_signature(path)
    prefix = _top_prefix(path)

    if family not in covered_families:
        score += 40.0
        reasons.append("uncovered_family")
    if signature not in covered_signatures:
        score += 24.0
        reasons.append("new_route_signature")
    if prefix not in covered_prefixes:
        score += 16.0
        reasons.append("new_path_prefix")
    if family in MONEY_FAMILIES or meta.get("high_value") is True:
        score += 20.0
        reasons.append("high_value_family")
    if is_trust_path(path):
        score += 8.0
        reasons.append("trust_route")

    for key, weight, reason in (
        ("template_novelty", 20.0, "template_novelty"),
        ("graph_novelty", 15.0, "graph_novelty"),
        ("finding_affinity", 18.0, "finding_affinity"),
    ):
        value = _bounded_unit(meta.get(key))
        if value is not None and value > 0:
            score += value * weight
            reasons.append(reason)

    return {
        "version": ADAPTIVE_SCORE_VERSION,
        "url": url,
        "score": round(score, 6),
        "reasons": tuple(reasons),
        "family": family,
        "route_signature": signature,
        "path_prefix": prefix,
    }


def select_adaptive_urls(
    urls: Iterable[str],
    family_of: Callable[[str], str],
    path_of: Callable[[str], str],
    target: int,
    *,
    metadata_by_url: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[str]:
    """Preserve Standard 150 exactly, then greedily diversify later tranches."""
    ordered = _unique_urls(urls)
    budget = max(0, min(len(ordered), int(target or 0), MAX_ADAPTIVE_TARGET))
    if budget <= 0:
        return []

    baseline_budget = min(STANDARD_150_TARGET, budget)
    selected = select_balanced_urls(ordered, family_of, path_of, baseline_budget)
    if budget <= STANDARD_150_TARGET or len(selected) >= budget:
        return selected[:budget]

    metadata = metadata_by_url or {}
    chosen = set(selected)
    covered_families = {family_of(url) for url in selected}
    covered_signatures = {route_signature(path_of(url)) for url in selected}
    covered_prefixes = {_top_prefix(path_of(url)) for url in selected}
    original_position = {url: index for index, url in enumerate(ordered)}

    while len(selected) < budget:
        candidates = [url for url in ordered if url not in chosen]
        if not candidates:
            break
        ranked: list[tuple[float, int, str, str, str, str]] = []
        for url in candidates:
            family = str(family_of(url) or "unknown")
            path = str(path_of(url) or "/")
            scored = adaptive_candidate_score(
                url,
                family=family,
                path=path,
                covered_families=covered_families,
                covered_signatures=covered_signatures,
                covered_prefixes=covered_prefixes,
                metadata=metadata.get(url),
            )
            ranked.append((
                -float(scored["score"]),
                original_position[url],
                url,
                family,
                str(scored["route_signature"]),
                str(scored["path_prefix"]),
            ))
        ranked.sort()
        _, _, url, family, signature, prefix = ranked[0]
        selected.append(url)
        chosen.add(url)
        covered_families.add(family)
        covered_signatures.add(signature)
        covered_prefixes.add(prefix)

    return selected[:budget]


def _as_set(snapshot: Mapping[str, Any], key: str) -> set[str] | None:
    if key not in snapshot or snapshot.get(key) is None:
        return None
    value = snapshot.get(key)
    if isinstance(value, str):
        return {value}
    try:
        return {str(item) for item in value if str(item)}
    except TypeError:
        return None


def _new_count(previous: Mapping[str, Any], current: Mapping[str, Any], key: str) -> int | None:
    before = _as_set(previous, key)
    after = _as_set(current, key)
    if before is None or after is None:
        return None
    return len(after - before)


def _per_100(value: int | None, pages_added: int) -> float | None:
    if value is None or pages_added <= 0:
        return None
    return round(value * 100.0 / pages_added, 4)


def build_tranche_yield_telemetry(
    previous: Mapping[str, Any],
    current: Mapping[str, Any],
    *,
    discovered_urls: int,
) -> dict[str, Any]:
    """Describe marginal assessed-page yield; missing/invalid signals remain unknown."""
    previous_assessed = max(0, int(previous.get("assessed_count") or 0))
    assessed = max(0, int(current.get("assessed_count") or 0))
    discovered = max(0, int(discovered_urls or 0))
    pages_added = max(0, assessed - previous_assessed)
    counts_valid = assessed >= previous_assessed and assessed <= discovered
    signal_keys = {
        "new_route_signatures": "route_signatures",
        "new_template_keys": "template_keys",
        "new_graph_edges": "graph_edges",
        "new_finding_fingerprints": "finding_fingerprints",
        "new_high_impact_findings": "high_impact_finding_fingerprints",
        "new_high_value_families": "high_value_families_assessed",
    }
    deltas = {name: _new_count(previous, current, key) for name, key in signal_keys.items()}
    rates = {f"{name}_per_100": _per_100(value, pages_added) for name, value in deltas.items()}
    regressed_signal_keys = tuple(sorted(
        key
        for key in signal_keys.values()
        if (
            (before := _as_set(previous, key)) is not None
            and (after := _as_set(current, key)) is not None
            and not before.issubset(after)
        )
    ))
    evidence_monotonic = not regressed_signal_keys
    if not counts_valid:
        signal_state = "invalid_counts"
    elif not evidence_monotonic:
        signal_state = "invalid_evidence"
    elif pages_added > 0 and all(value is not None for value in deltas.values()):
        signal_state = "observed"
    else:
        signal_state = "insufficient_evidence"
    return {
        "version": ADAPTIVE_TELEMETRY_VERSION,
        "discovered_urls": discovered,
        "previous_assessed_count": previous_assessed,
        "assessed_count": assessed,
        "pages_added": pages_added,
        "counts_valid": counts_valid,
        "evidence_monotonic": evidence_monotonic,
        "regressed_signal_keys": regressed_signal_keys,
        "signal_state": signal_state,
        **deltas,
        **rates,
    }


def continuation_decision(
    telemetry: Mapping[str, Any],
    *,
    tranche_targets: Sequence[int] = DEFAULT_TRANCHE_TARGETS,
) -> dict[str, Any]:
    """Choose whether another bounded tranche is justified by observed novelty."""
    assessed = max(0, int(telemetry.get("assessed_count") or 0))
    discovered = max(0, int(telemetry.get("discovered_urls") or 0))
    normalized_targets = _normalized_targets(tranche_targets)
    max_target = max(normalized_targets, default=0)

    if telemetry.get("version") != ADAPTIVE_TELEMETRY_VERSION:
        return {
            "version": ADAPTIVE_CRAWL_VERSION,
            "decision": "insufficient_evidence",
            "next_target": None,
            "reason": "telemetry_version_mismatch",
            "site_fully_understood": False,
        }
    if not normalized_targets:
        return {
            "version": ADAPTIVE_CRAWL_VERSION,
            "decision": "hold",
            "next_target": None,
            "reason": "no_tranche_targets_configured",
            "site_fully_understood": False,
        }
    if telemetry.get("signal_state") == "invalid_counts" or telemetry.get("counts_valid") is not True:
        return {
            "version": ADAPTIVE_CRAWL_VERSION,
            "decision": "insufficient_evidence",
            "next_target": None,
            "reason": "invalid_tranche_counts",
            "site_fully_understood": False,
        }
    if telemetry.get("signal_state") == "invalid_evidence" or telemetry.get("evidence_monotonic") is False:
        return {
            "version": ADAPTIVE_CRAWL_VERSION,
            "decision": "insufficient_evidence",
            "next_target": None,
            "reason": "regressed_tranche_evidence",
            "site_fully_understood": False,
        }
    if assessed >= max_target:
        return {
            "version": ADAPTIVE_CRAWL_VERSION,
            "decision": "hold",
            "next_target": None,
            "reason": "adaptive_ceiling_reached",
            "site_fully_understood": False,
        }
    if discovered <= assessed:
        return {
            "version": ADAPTIVE_CRAWL_VERSION,
            "decision": "discovered_inventory_exhausted",
            "next_target": None,
            "reason": "all_currently_discovered_urls_assessed",
            "site_fully_understood": False,
        }

    bounded_discovered = min(discovered, max_target)
    next_target = min(
        (target for target in normalized_targets if assessed < target <= bounded_discovered),
        default=None,
    )
    if next_target is None and assessed < bounded_discovered:
        next_target = bounded_discovered

    if telemetry.get("signal_state") != "observed":
        reason = "marginal_yield_signals_incomplete"
        return {
            "version": ADAPTIVE_CRAWL_VERSION,
            "decision": "insufficient_evidence",
            "next_target": next_target,
            "reason": reason,
            "site_fully_understood": False,
        }

    routes = float(telemetry.get("new_route_signatures_per_100") or 0.0)
    templates = float(telemetry.get("new_template_keys_per_100") or 0.0)
    graph = float(telemetry.get("new_graph_edges_per_100") or 0.0)
    findings = float(telemetry.get("new_high_impact_findings_per_100") or 0.0)
    high_value = int(telemetry.get("new_high_value_families") or 0)
    reasons: list[str] = []
    if routes >= 5.0:
        reasons.append("route_novelty")
    if templates >= 2.0:
        reasons.append("template_novelty")
    if graph >= 5.0:
        reasons.append("graph_novelty")
    if findings >= 0.5:
        reasons.append("high_impact_finding_yield")
    if high_value > 0:
        reasons.append("new_high_value_family")

    return {
        "version": ADAPTIVE_CRAWL_VERSION,
        "decision": "expand" if reasons and next_target is not None else "hold",
        "next_target": next_target if reasons else None,
        "reason": ",".join(reasons) if reasons else "marginal_yield_below_shadow_thresholds",
        "site_fully_understood": False,
    }


def _finding_set(
    selected: Sequence[str],
    finding_fingerprints_by_url: Mapping[str, Iterable[str]],
) -> set[str]:
    return {
        str(fingerprint)
        for url in selected
        for fingerprint in finding_fingerprints_by_url.get(url, ())
        if str(fingerprint)
    }


def _benchmark_summary(
    selected: Sequence[str],
    family_of: Callable[[str], str],
    path_of: Callable[[str], str],
    *,
    finding_fingerprints_by_url: Mapping[str, Iterable[str]],
    template_key_by_url: Mapping[str, str] | None,
) -> dict[str, Any]:
    findings = _finding_set(selected, finding_fingerprints_by_url)
    templates = {
        str((template_key_by_url or {}).get(url) or family_of(url) or "unknown")
        for url in selected
    }
    families = {str(family_of(url) or "unknown") for url in selected}
    signatures = {route_signature(path_of(url)) for url in selected}
    pages = len(selected)
    return {
        "pages_assessed": pages,
        "finding_fingerprints": len(findings),
        "finding_yield_per_100": round(len(findings) * 100.0 / pages, 4) if pages else 0.0,
        "template_keys": len(templates),
        "families": len(families),
        "route_signatures": len(signatures),
    }


def benchmark_smart_500_vs_blind_1000(
    urls: Iterable[str],
    family_of: Callable[[str], str],
    path_of: Callable[[str], str],
    *,
    finding_fingerprints_by_url: Mapping[str, Iterable[str]],
    template_key_by_url: Mapping[str, str] | None = None,
    metadata_by_url: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Deterministically compare adaptive 500-page selection with FIFO 1000."""
    ordered = _unique_urls(urls)
    smart = select_adaptive_urls(
        ordered,
        family_of,
        path_of,
        min(500, len(ordered)),
        metadata_by_url=metadata_by_url,
    )
    blind = ordered[: min(MAX_ADAPTIVE_TARGET, len(ordered))]
    smart_summary = _benchmark_summary(
        smart,
        family_of,
        path_of,
        finding_fingerprints_by_url=finding_fingerprints_by_url,
        template_key_by_url=template_key_by_url,
    )
    blind_summary = _benchmark_summary(
        blind,
        family_of,
        path_of,
        finding_fingerprints_by_url=finding_fingerprints_by_url,
        template_key_by_url=template_key_by_url,
    )
    smart_findings = _finding_set(smart, finding_fingerprints_by_url)
    blind_findings = _finding_set(blind, finding_fingerprints_by_url)
    shared_findings = smart_findings & blind_findings
    blind_yield = float(blind_summary["finding_yield_per_100"])
    efficiency_ratio = (
        round(float(smart_summary["finding_yield_per_100"]) / blind_yield, 4)
        if blind_yield > 0
        else None
    )
    coverage_ratio = (
        round(len(shared_findings) / len(blind_findings), 4)
        if blind_findings
        else None
    )
    return {
        "version": ADAPTIVE_BENCHMARK_VERSION,
        "smart_500": smart_summary,
        "blind_1000": blind_summary,
        "smart_finding_coverage_vs_blind": coverage_ratio,
        "smart_efficiency_vs_blind": efficiency_ratio,
        "finding_comparison_state": "observed" if blind_findings else "no_blind_findings",
        "shared_finding_fingerprints": len(shared_findings),
        "smart_only_finding_fingerprints": len(smart_findings - blind_findings),
        "blind_only_finding_fingerprints": len(blind_findings - smart_findings),
        "pages_saved_by_smart": max(0, len(blind) - len(smart)),
    }
