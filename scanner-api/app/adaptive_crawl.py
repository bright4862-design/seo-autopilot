"""Pure, shadow-only helpers for adaptive crawl planning and selection.

Nothing in this module performs network I/O or changes the production Standard 150
budget.  The serialized integrator may later wire these helpers behind an opt-in
next-generation mode.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any
from .sampling import MONEY_FAMILIES, is_trust_path, route_signature, select_balanced_urls

ADAPTIVE_CRAWL_VERSION = "adaptive_crawl_v1_shadow"
ADAPTIVE_SCORE_VERSION = "adaptive_candidate_score_v1"
ADAPTIVE_TELEMETRY_VERSION = "adaptive_tranche_yield_v1"
ADAPTIVE_BENCHMARK_VERSION = "adaptive_benchmark_v1"
STANDARD_150_TARGET = 150
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
    segments = [segment for segment in str(path or "/").split("/") if segment]
    return f"/{segments[0].lower()}" if segments else "/"


def _bounded_unit(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, number))


def plan_tranche_targets(
    discovered_urls: int,
    *,
    ceiling: int = 1000,
    candidate_targets: Sequence[int] = DEFAULT_TRANCHE_TARGETS,
) -> dict[str, Any]:
    """Return bounded assessment targets without claiming discovery is complete."""
    discovered = max(0, int(discovered_urls or 0))
    hard_ceiling = max(0, int(ceiling or 0))
    bound = min(discovered, hard_ceiling)
    if bound <= 0:
        targets: list[int] = []
    else:
        targets = sorted({min(bound, max(1, int(target))) for target in candidate_targets if int(target) > 0})
        if bound not in targets:
            targets.append(bound)
            targets.sort()
    return {
        "version": ADAPTIVE_CRAWL_VERSION,
        "discovered_urls": discovered,
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
    budget = max(0, min(len(ordered), int(target or 0)))
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
    """Describe marginal assessed-page yield; missing signals remain unknown."""
    previous_assessed = max(0, int(previous.get("assessed_count") or 0))
    assessed = max(0, int(current.get("assessed_count") or 0))
    pages_added = max(0, assessed - previous_assessed)
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
    signal_state = "observed" if pages_added > 0 and all(value is not None for value in deltas.values()) else "insufficient_evidence"
    return {
        "version": ADAPTIVE_TELEMETRY_VERSION,
        "discovered_urls": max(0, int(discovered_urls or 0)),
        "previous_assessed_count": previous_assessed,
        "assessed_count": assessed,
        "pages_added": pages_added,
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
    targets = sorted({int(target) for target in tranche_targets if int(target) > assessed})
    next_target = min((target for target in targets if target <= discovered), default=None)
    if next_target is None and discovered > assessed:
        next_target = discovered

    if discovered <= assessed:
        return {
            "version": ADAPTIVE_CRAWL_VERSION,
            "decision": "discovered_inventory_exhausted",
            "next_target": None,
            "reason": "all_currently_discovered_urls_assessed",
            "site_fully_understood": False,
        }
    if telemetry.get("signal_state") != "observed":
        return {
            "version": ADAPTIVE_CRAWL_VERSION,
            "decision": "insufficient_evidence",
            "next_target": next_target,
            "reason": "marginal_yield_signals_incomplete",
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


def _benchmark_summary(
    selected: Sequence[str],
    family_of: Callable[[str], str],
    path_of: Callable[[str], str],
    *,
    finding_fingerprints_by_url: Mapping[str, Iterable[str]],
    template_key_by_url: Mapping[str, str] | None,
) -> dict[str, Any]:
    findings = {
        str(fingerprint)
        for url in selected
        for fingerprint in finding_fingerprints_by_url.get(url, ())
        if str(fingerprint)
    }
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
    blind = ordered[: min(1000, len(ordered))]
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
    blind_findings = max(1, blind_summary["finding_fingerprints"])
    return {
        "version": ADAPTIVE_BENCHMARK_VERSION,
        "smart_500": smart_summary,
        "blind_1000": blind_summary,
        "smart_finding_coverage_vs_blind": round(smart_summary["finding_fingerprints"] / blind_findings, 4),
        "smart_efficiency_vs_blind": round(
            smart_summary["finding_yield_per_100"] / max(0.0001, blind_summary["finding_yield_per_100"]),
            4,
        ),
    }
