"""Pure marginal-yield benchmark curves for the Lane-A adaptive crawl experiment.

This module performs no network or persistence work and cannot authorize a crawl
budget. It compares deterministic Smart and FIFO populations at 150/500/1000
checkpoints so engineering can see what each additional tranche actually discovers.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from .adaptive_crawl import MAX_ADAPTIVE_TARGET, select_adaptive_urls
from .sampling import route_signature

ADAPTIVE_MARGINAL_BENCHMARK_VERSION = "adaptive_marginal_benchmark_v1"
ADAPTIVE_MARGINAL_GAP_VERSION = "adaptive_marginal_gap_v1"
MARGINAL_CHECKPOINTS = (150, 500, 1000)


def _strict_unique_urls(urls: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in urls:
        if not isinstance(raw, str) or not raw or raw.strip() != raw:
            raise ValueError("invalid_url_identity")
        if raw not in seen:
            seen.add(raw)
            ordered.append(raw)
    return tuple(ordered)


def _fingerprint(urls: Sequence[str]) -> str:
    digest = hashlib.sha256()
    digest.update(b"adaptive_marginal_population_v1\0")
    for url in urls:
        digest.update(url.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _fingerprint_set(
    selected: Sequence[str],
    evidence_by_url: Mapping[str, Iterable[str]],
) -> set[str]:
    result: set[str] = set()
    for url in selected:
        for raw in evidence_by_url.get(url, ()):
            text = str(raw or "").strip()
            if text:
                result.add(text)
    return result


def _summary_sets(
    selected: Sequence[str],
    family_of: Callable[[str], str],
    path_of: Callable[[str], str],
    *,
    finding_fingerprints_by_url: Mapping[str, Iterable[str]],
    high_impact_finding_fingerprints_by_url: Mapping[str, Iterable[str]] | None,
    template_key_by_url: Mapping[str, str] | None,
) -> dict[str, set[str]]:
    return {
        "findings": _fingerprint_set(selected, finding_fingerprints_by_url),
        "high_impact": (
            _fingerprint_set(selected, high_impact_finding_fingerprints_by_url)
            if high_impact_finding_fingerprints_by_url is not None
            else set()
        ),
        "templates": {
            str((template_key_by_url or {}).get(url) or family_of(url) or "unknown")
            for url in selected
        },
        "families": {str(family_of(url) or "unknown") for url in selected},
        "routes": {route_signature(path_of(url)) for url in selected},
    }


def _per_100(value: int, pages_added: int) -> float | None:
    if pages_added <= 0:
        return None
    return round(value * 100.0 / pages_added, 4)


def _coverage(covered: int, reference: int) -> float | None:
    if reference <= 0:
        return None
    return round(covered / reference, 4)


def _build_curve(
    strategy: str,
    populations: Sequence[tuple[int, Sequence[str]]],
    family_of: Callable[[str], str],
    path_of: Callable[[str], str],
    *,
    finding_fingerprints_by_url: Mapping[str, Iterable[str]],
    high_impact_finding_fingerprints_by_url: Mapping[str, Iterable[str]] | None,
    template_key_by_url: Mapping[str, str] | None,
    reference_findings: set[str],
    reference_high_impact: set[str] | None,
) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    previous_pages = 0
    previous_sets = {
        "findings": set(),
        "high_impact": set(),
        "templates": set(),
        "families": set(),
        "routes": set(),
    }

    for target, population in populations:
        current = _summary_sets(
            population,
            family_of,
            path_of,
            finding_fingerprints_by_url=finding_fingerprints_by_url,
            high_impact_finding_fingerprints_by_url=high_impact_finding_fingerprints_by_url,
            template_key_by_url=template_key_by_url,
        )
        pages = len(population)
        pages_added = pages - previous_pages
        new_findings = len(current["findings"] - previous_sets["findings"])
        new_templates = len(current["templates"] - previous_sets["templates"])
        new_families = len(current["families"] - previous_sets["families"])
        new_routes = len(current["routes"] - previous_sets["routes"])
        reference_findings_covered = len(current["findings"] & reference_findings)

        if high_impact_finding_fingerprints_by_url is None:
            new_high_impact: int | None = None
            cumulative_high_impact: int | None = None
            reference_high_impact_covered: int | None = None
            high_impact_yield: float | None = None
            high_impact_coverage: float | None = None
        else:
            new_high_impact = len(current["high_impact"] - previous_sets["high_impact"])
            cumulative_high_impact = len(current["high_impact"])
            reference_high_impact_covered = len(
                current["high_impact"] & (reference_high_impact or set())
            )
            high_impact_yield = _per_100(new_high_impact, pages_added)
            high_impact_coverage = _coverage(
                reference_high_impact_covered,
                len(reference_high_impact or set()),
            )

        rows.append(
            {
                "strategy": strategy,
                "target": target,
                "pages_assessed": pages,
                "pages_added": pages_added,
                "population_fingerprint": _fingerprint(population),
                "state": "observed" if pages_added > 0 else "no_incremental_pages",
                "new_finding_fingerprints": new_findings,
                "new_finding_yield_per_100": _per_100(new_findings, pages_added),
                "new_high_impact_finding_fingerprints": new_high_impact,
                "new_high_impact_finding_yield_per_100": high_impact_yield,
                "new_template_keys": new_templates,
                "new_families": new_families,
                "new_route_signatures": new_routes,
                "cumulative_template_keys": len(current["templates"]),
                "cumulative_families": len(current["families"]),
                "cumulative_route_signatures": len(current["routes"]),
                "cumulative_finding_fingerprints": len(current["findings"]),
                "cumulative_high_impact_finding_fingerprints": cumulative_high_impact,
                "reference_findings_covered": reference_findings_covered,
                "reference_high_impact_findings_covered": reference_high_impact_covered,
                "finding_coverage_vs_blind_1000": _coverage(
                    reference_findings_covered,
                    len(reference_findings),
                ),
                "high_impact_coverage_vs_blind_1000": high_impact_coverage,
            }
        )
        previous_pages = pages
        previous_sets = current

    return tuple(rows)


def build_marginal_yield_benchmark(
    urls: Iterable[str],
    family_of: Callable[[str], str],
    path_of: Callable[[str], str],
    *,
    finding_fingerprints_by_url: Mapping[str, Iterable[str]],
    high_impact_finding_fingerprints_by_url: Mapping[str, Iterable[str]] | None = None,
    template_key_by_url: Mapping[str, str] | None = None,
    metadata_by_url: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build deterministic 150/500/1000 marginal-yield curves for Smart and FIFO."""
    ordered = _strict_unique_urls(urls)
    blind_populations = tuple(
        (target, ordered[: min(target, len(ordered), MAX_ADAPTIVE_TARGET)])
        for target in MARGINAL_CHECKPOINTS
    )
    smart_populations = tuple(
        (
            target,
            tuple(
                select_adaptive_urls(
                    ordered,
                    family_of,
                    path_of,
                    min(target, len(ordered), MAX_ADAPTIVE_TARGET),
                    metadata_by_url=metadata_by_url,
                )
            ),
        )
        for target in MARGINAL_CHECKPOINTS
    )

    blind_reference = blind_populations[-1][1]
    reference_sets = _summary_sets(
        blind_reference,
        family_of,
        path_of,
        finding_fingerprints_by_url=finding_fingerprints_by_url,
        high_impact_finding_fingerprints_by_url=high_impact_finding_fingerprints_by_url,
        template_key_by_url=template_key_by_url,
    )
    reference_high_impact = (
        reference_sets["high_impact"]
        if high_impact_finding_fingerprints_by_url is not None
        else None
    )

    smart_curve = _build_curve(
        "smart",
        smart_populations,
        family_of,
        path_of,
        finding_fingerprints_by_url=finding_fingerprints_by_url,
        high_impact_finding_fingerprints_by_url=high_impact_finding_fingerprints_by_url,
        template_key_by_url=template_key_by_url,
        reference_findings=reference_sets["findings"],
        reference_high_impact=reference_high_impact,
    )
    blind_curve = _build_curve(
        "blind",
        blind_populations,
        family_of,
        path_of,
        finding_fingerprints_by_url=finding_fingerprints_by_url,
        high_impact_finding_fingerprints_by_url=high_impact_finding_fingerprints_by_url,
        template_key_by_url=template_key_by_url,
        reference_findings=reference_sets["findings"],
        reference_high_impact=reference_high_impact,
    )

    return {
        "version": ADAPTIVE_MARGINAL_BENCHMARK_VERSION,
        "candidate_count": len(ordered),
        "checkpoints": MARGINAL_CHECKPOINTS,
        "reference_strategy": "blind_1000",
        "reference_pages_assessed": len(blind_reference),
        "reference_finding_fingerprints": len(reference_sets["findings"]),
        "reference_high_impact_finding_fingerprints": (
            len(reference_sets["high_impact"])
            if high_impact_finding_fingerprints_by_url is not None
            else None
        ),
        "high_impact_evidence_state": (
            "observed"
            if high_impact_finding_fingerprints_by_url is not None
            else "not_observed"
        ),
        "inventory_limited": len(ordered) < MAX_ADAPTIVE_TARGET,
        "population_scope_complete": False,
        "smart": smart_curve,
        "blind": blind_curve,
    }


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _expected_rate(count: int, pages_added: int) -> float | None:
    return _per_100(count, pages_added)


def validate_marginal_yield_benchmark(result: Mapping[str, Any] | Any) -> dict[str, Any]:
    """Fail closed on malformed or arithmetically inconsistent marginal evidence."""
    if not isinstance(result, Mapping):
        return {"valid": False, "reason": "result_not_mapping"}
    if result.get("version") != ADAPTIVE_MARGINAL_BENCHMARK_VERSION:
        return {"valid": False, "reason": "version_mismatch"}
    if tuple(result.get("checkpoints") or ()) != MARGINAL_CHECKPOINTS:
        return {"valid": False, "reason": "checkpoint_mismatch"}
    if result.get("population_scope_complete") is not False:
        return {"valid": False, "reason": "population_scope_claim_invalid"}

    candidate_count = _nonnegative_int(result.get("candidate_count"))
    reference_pages = _nonnegative_int(result.get("reference_pages_assessed"))
    reference_findings = _nonnegative_int(result.get("reference_finding_fingerprints"))
    if None in (candidate_count, reference_pages, reference_findings):
        return {"valid": False, "reason": "invalid_reference_count"}
    assert candidate_count is not None
    assert reference_pages is not None
    assert reference_findings is not None
    if reference_pages != min(candidate_count, MAX_ADAPTIVE_TARGET):
        return {"valid": False, "reason": "reference_page_count_mismatch"}
    if result.get("inventory_limited") is not (candidate_count < MAX_ADAPTIVE_TARGET):
        return {"valid": False, "reason": "inventory_limited_mismatch"}
    if result.get("reference_strategy") != "blind_1000":
        return {"valid": False, "reason": "reference_strategy_mismatch"}

    high_state = result.get("high_impact_evidence_state")
    reference_high = result.get("reference_high_impact_finding_fingerprints")
    if high_state == "observed":
        reference_high_int = _nonnegative_int(reference_high)
        if reference_high_int is None:
            return {"valid": False, "reason": "invalid_high_impact_reference_count"}
    elif high_state == "not_observed":
        if reference_high is not None:
            return {"valid": False, "reason": "unexpected_high_impact_reference_count"}
        reference_high_int = None
    else:
        return {"valid": False, "reason": "invalid_high_impact_evidence_state"}

    for strategy in ("smart", "blind"):
        rows = result.get(strategy)
        if isinstance(rows, (str, bytes, Mapping)) or not isinstance(rows, Sequence):
            return {"valid": False, "reason": f"{strategy}_curve_invalid"}
        if len(rows) != len(MARGINAL_CHECKPOINTS):
            return {"valid": False, "reason": f"{strategy}_curve_length_mismatch"}

        previous_pages = 0
        previous_cumulative_findings = 0
        previous_reference_covered = 0
        previous_cumulative_high = 0
        previous_reference_high_covered = 0
        previous_cumulative_templates = 0
        previous_cumulative_families = 0
        previous_cumulative_routes = 0

        for target, row in zip(MARGINAL_CHECKPOINTS, rows):
            if not isinstance(row, Mapping) or row.get("strategy") != strategy or row.get("target") != target:
                return {"valid": False, "reason": f"{strategy}_row_identity_mismatch"}
            pages = _nonnegative_int(row.get("pages_assessed"))
            pages_added = _nonnegative_int(row.get("pages_added"))
            if pages is None or pages_added is None:
                return {"valid": False, "reason": f"{strategy}_page_count_invalid"}
            if pages > min(target, candidate_count, MAX_ADAPTIVE_TARGET):
                return {"valid": False, "reason": f"{strategy}_page_cap_exceeded"}
            if pages < previous_pages or pages_added != pages - previous_pages:
                return {"valid": False, "reason": f"{strategy}_page_delta_mismatch"}

            fingerprint = row.get("population_fingerprint")
            if not isinstance(fingerprint, str) or len(fingerprint) != 64:
                return {"valid": False, "reason": f"{strategy}_population_fingerprint_invalid"}

            state = row.get("state")
            if state != ("observed" if pages_added > 0 else "no_incremental_pages"):
                return {"valid": False, "reason": f"{strategy}_state_mismatch"}

            new_findings = _nonnegative_int(row.get("new_finding_fingerprints"))
            cumulative_findings = _nonnegative_int(row.get("cumulative_finding_fingerprints"))
            covered = _nonnegative_int(row.get("reference_findings_covered"))
            if None in (new_findings, cumulative_findings, covered):
                return {"valid": False, "reason": f"{strategy}_finding_count_invalid"}
            assert new_findings is not None
            assert cumulative_findings is not None
            assert covered is not None
            if cumulative_findings - previous_cumulative_findings != new_findings:
                return {"valid": False, "reason": f"{strategy}_finding_delta_mismatch"}
            if covered < previous_reference_covered or covered > min(cumulative_findings, reference_findings):
                return {"valid": False, "reason": f"{strategy}_reference_finding_count_invalid"}
            if row.get("new_finding_yield_per_100") != _expected_rate(new_findings, pages_added):
                return {"valid": False, "reason": f"{strategy}_finding_yield_mismatch"}
            if row.get("finding_coverage_vs_blind_1000") != _coverage(covered, reference_findings):
                return {"valid": False, "reason": f"{strategy}_finding_coverage_mismatch"}

            for new_field, cumulative_field, previous_value in (
                ("new_template_keys", "cumulative_template_keys", previous_cumulative_templates),
                ("new_families", "cumulative_families", previous_cumulative_families),
                ("new_route_signatures", "cumulative_route_signatures", previous_cumulative_routes),
            ):
                new_value = _nonnegative_int(row.get(new_field))
                cumulative_value = _nonnegative_int(row.get(cumulative_field))
                if new_value is None or cumulative_value is None:
                    return {"valid": False, "reason": f"{strategy}_{new_field}_invalid"}
                if cumulative_value - previous_value != new_value:
                    return {"valid": False, "reason": f"{strategy}_{new_field}_delta_mismatch"}

            previous_cumulative_templates = int(row["cumulative_template_keys"])
            previous_cumulative_families = int(row["cumulative_families"])
            previous_cumulative_routes = int(row["cumulative_route_signatures"])

            if high_state == "observed":
                new_high = _nonnegative_int(row.get("new_high_impact_finding_fingerprints"))
                cumulative_high = _nonnegative_int(row.get("cumulative_high_impact_finding_fingerprints"))
                covered_high = _nonnegative_int(row.get("reference_high_impact_findings_covered"))
                if None in (new_high, cumulative_high, covered_high):
                    return {"valid": False, "reason": f"{strategy}_high_impact_count_invalid"}
                assert new_high is not None
                assert cumulative_high is not None
                assert covered_high is not None
                assert reference_high_int is not None
                if cumulative_high - previous_cumulative_high != new_high:
                    return {"valid": False, "reason": f"{strategy}_high_impact_delta_mismatch"}
                if covered_high < previous_reference_high_covered or covered_high > min(cumulative_high, reference_high_int):
                    return {"valid": False, "reason": f"{strategy}_reference_high_impact_count_invalid"}
                if row.get("new_high_impact_finding_yield_per_100") != _expected_rate(new_high, pages_added):
                    return {"valid": False, "reason": f"{strategy}_high_impact_yield_mismatch"}
                if row.get("high_impact_coverage_vs_blind_1000") != _coverage(covered_high, reference_high_int):
                    return {"valid": False, "reason": f"{strategy}_high_impact_coverage_mismatch"}
                previous_cumulative_high = cumulative_high
                previous_reference_high_covered = covered_high
            else:
                for field in (
                    "new_high_impact_finding_fingerprints",
                    "new_high_impact_finding_yield_per_100",
                    "cumulative_high_impact_finding_fingerprints",
                    "reference_high_impact_findings_covered",
                    "high_impact_coverage_vs_blind_1000",
                ):
                    if row.get(field) is not None:
                        return {"valid": False, "reason": f"{strategy}_unexpected_high_impact_metric"}

            previous_pages = pages
            previous_cumulative_findings = cumulative_findings
            previous_reference_covered = covered

        if strategy == "blind":
            final_row = rows[-1]
            if final_row.get("pages_assessed") != reference_pages:
                return {"valid": False, "reason": "blind_reference_pages_mismatch"}
            if final_row.get("cumulative_finding_fingerprints") != reference_findings:
                return {"valid": False, "reason": "blind_reference_findings_mismatch"}
            if reference_findings > 0 and final_row.get("finding_coverage_vs_blind_1000") != 1.0:
                return {"valid": False, "reason": "blind_reference_coverage_mismatch"}
            if high_state == "observed":
                if final_row.get("cumulative_high_impact_finding_fingerprints") != reference_high_int:
                    return {"valid": False, "reason": "blind_reference_high_impact_mismatch"}
                if reference_high_int and final_row.get("high_impact_coverage_vs_blind_1000") != 1.0:
                    return {"valid": False, "reason": "blind_reference_high_impact_coverage_mismatch"}

    return {
        "valid": True,
        "reason": "ok",
        "version": ADAPTIVE_MARGINAL_BENCHMARK_VERSION,
        "population_scope_complete": False,
    }


def summarize_smart_500_gap(result: Mapping[str, Any] | Any) -> dict[str, Any]:
    """Extract the decision-relevant Smart-500 gap without authorizing production."""
    integrity = validate_marginal_yield_benchmark(result)
    if integrity.get("valid") is not True:
        return {
            "version": ADAPTIVE_MARGINAL_GAP_VERSION,
            "state": "insufficient_evidence",
            "reason": integrity.get("reason"),
            "production_budget_authorized": False,
            "site_fully_understood": False,
        }

    smart_500 = result["smart"][1]
    blind_1000 = result["blind"][2]
    blind_500 = result["blind"][1]
    reference_findings = int(result["reference_finding_fingerprints"])
    missed_findings = reference_findings - int(smart_500["reference_findings_covered"])

    high_state = result["high_impact_evidence_state"]
    if high_state == "observed":
        reference_high = int(result["reference_high_impact_finding_fingerprints"])
        missed_high: int | None = reference_high - int(
            smart_500["reference_high_impact_findings_covered"]
        )
        blind_tail_new_high: int | None = int(
            blind_1000["cumulative_high_impact_finding_fingerprints"]
        ) - int(blind_500["cumulative_high_impact_finding_fingerprints"])
        blind_tail_high_yield: float | None = _per_100(
            blind_tail_new_high,
            int(blind_1000["pages_assessed"]) - int(blind_500["pages_assessed"]),
        )
    else:
        missed_high = None
        blind_tail_new_high = None
        blind_tail_high_yield = None

    blind_tail_pages = int(blind_1000["pages_assessed"]) - int(blind_500["pages_assessed"])
    blind_tail_new_findings = int(blind_1000["cumulative_finding_fingerprints"]) - int(
        blind_500["cumulative_finding_fingerprints"]
    )

    return {
        "version": ADAPTIVE_MARGINAL_GAP_VERSION,
        "state": "observed" if blind_tail_pages > 0 else "inventory_limited",
        "smart_500_pages_assessed": int(smart_500["pages_assessed"]),
        "blind_1000_pages_assessed": int(blind_1000["pages_assessed"]),
        "blind_tail_pages": blind_tail_pages,
        "smart_500_reference_finding_coverage": smart_500["finding_coverage_vs_blind_1000"],
        "smart_500_missed_reference_findings": missed_findings,
        "blind_tail_new_findings": blind_tail_new_findings,
        "blind_tail_new_finding_yield_per_100": _per_100(
            blind_tail_new_findings,
            blind_tail_pages,
        ),
        "smart_500_reference_high_impact_coverage": smart_500[
            "high_impact_coverage_vs_blind_1000"
        ],
        "smart_500_missed_reference_high_impact_findings": missed_high,
        "blind_tail_new_high_impact_findings": blind_tail_new_high,
        "blind_tail_new_high_impact_yield_per_100": blind_tail_high_yield,
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }
