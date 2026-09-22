"""Population-bound smart-500 vs blind-1000 benchmark helpers.

This module is engineering-only shadow tooling. It binds the finding-yield and
priority-page benchmark envelopes to the same exact selected URL populations so
a later corpus comparison cannot accidentally combine results produced from
different smart/blind samples. It performs no network work, does not authorize a
crawl budget, and never claims whole-site completeness.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from .adaptive_benchmark_integrity import (
    summarize_benchmark_corpus,
    validate_adaptive_benchmark,
)
from .adaptive_crawl import (
    MAX_ADAPTIVE_TARGET,
    benchmark_smart_500_vs_blind_1000,
    select_adaptive_urls,
)
from .adaptive_priority_benchmark import (
    SMART_PAGE_CAP,
    build_priority_page_benchmark,
    summarize_priority_benchmark_corpus,
    validate_priority_page_benchmark,
)

ADAPTIVE_BENCHMARK_BUNDLE_VERSION = "adaptive_benchmark_bundle_v1"
ADAPTIVE_BENCHMARK_BUNDLE_CORPUS_VERSION = "adaptive_benchmark_bundle_corpus_v1"
ADAPTIVE_BENCHMARK_POPULATION_VERSION = "adaptive_benchmark_population_v1"


def _invalid(reason: str) -> dict[str, Any]:
    return {
        "version": ADAPTIVE_BENCHMARK_BUNDLE_VERSION,
        "state": "invalid_evidence",
        "valid": False,
        "reason": reason,
        "population_scope_complete": False,
    }


def _materialize_urls(values: Iterable[str] | Any) -> tuple[tuple[str, ...] | None, str | None]:
    if isinstance(values, (str, bytes, Mapping)):
        return None, "candidate_urls_not_sequence"
    try:
        materialized = tuple(values)
    except TypeError:
        return None, "candidate_urls_not_sequence"
    for value in materialized:
        if not isinstance(value, str) or not value or value != value.strip():
            return None, "candidate_urls_invalid_identity"
    return materialized, None


def _unique_exact(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return tuple(ordered)


def _selected_sequence(values: Any, *, field: str, cap: int) -> tuple[tuple[str, ...] | None, str | None]:
    if isinstance(values, (str, bytes, Mapping)):
        return None, f"{field}_not_sequence"
    try:
        materialized = tuple(values)
    except TypeError:
        return None, f"{field}_not_sequence"
    for value in materialized:
        if not isinstance(value, str) or not value or value != value.strip():
            return None, f"{field}_invalid_identity"
    if len(set(materialized)) != len(materialized):
        return None, f"{field}_duplicate_identity"
    if len(materialized) > cap:
        return None, f"{field}_page_cap_exceeded"
    return materialized, None


def _population_fingerprint(role: str, urls: tuple[str, ...]) -> str:
    payload = json.dumps(
        {
            "version": ADAPTIVE_BENCHMARK_POPULATION_VERSION,
            "role": role,
            "urls": urls,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_adaptive_benchmark_bundle(
    urls: Iterable[str],
    family_of: Callable[[str], str],
    path_of: Callable[[str], str],
    *,
    finding_fingerprints_by_url: Mapping[str, Iterable[str]],
    important_urls: Iterable[str],
    high_value_urls: Iterable[str] = (),
    template_key_by_url: Mapping[str, str] | None = None,
    metadata_by_url: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build paired benchmark evidence from one exact candidate population.

    Discovery duplicates are de-duplicated by exact identity for the benchmark
    universe, matching ``benchmark_smart_500_vs_blind_1000``. No URL
    normalization, lower-casing, slash folding or redirect inference occurs.
    """
    raw_urls, reason = _materialize_urls(urls)
    if reason:
        return _invalid(reason)
    assert raw_urls is not None
    ordered = _unique_exact(raw_urls)

    smart = tuple(
        select_adaptive_urls(
            ordered,
            family_of,
            path_of,
            min(SMART_PAGE_CAP, len(ordered)),
            metadata_by_url=metadata_by_url,
        )
    )
    blind = ordered[: min(MAX_ADAPTIVE_TARGET, len(ordered))]

    finding = benchmark_smart_500_vs_blind_1000(
        ordered,
        family_of,
        path_of,
        finding_fingerprints_by_url=finding_fingerprints_by_url,
        template_key_by_url=template_key_by_url,
        metadata_by_url=metadata_by_url,
    )
    finding_integrity = validate_adaptive_benchmark(finding)
    if finding_integrity.get("valid") is not True:
        return _invalid(f"finding_benchmark_{finding_integrity.get('reason') or 'invalid'}")

    priority = build_priority_page_benchmark(
        smart,
        blind,
        important_urls=important_urls,
        high_value_urls=high_value_urls,
    )
    priority_integrity = validate_priority_page_benchmark(priority)
    if priority_integrity.get("valid") is not True:
        return _invalid(f"priority_benchmark_{priority_integrity.get('reason') or priority.get('reason') or 'invalid'}")

    return {
        "version": ADAPTIVE_BENCHMARK_BUNDLE_VERSION,
        "state": "observed",
        "valid": True,
        "reason": "paired_benchmark_population_bound",
        "population_scope_complete": False,
        "candidate_urls_supplied": len(raw_urls),
        "candidate_urls_unique": len(ordered),
        "duplicate_candidate_identities_removed": len(raw_urls) - len(ordered),
        "smart_selected": smart,
        "blind_selected": blind,
        "smart_population_sha256": _population_fingerprint("smart_500", smart),
        "blind_population_sha256": _population_fingerprint("blind_1000", blind),
        "finding_benchmark": finding,
        "priority_benchmark": priority,
    }


def validate_adaptive_benchmark_bundle(result: Mapping[str, Any] | Any) -> dict[str, Any]:
    """Fail closed unless both nested benchmarks bind to one exact population."""
    if not isinstance(result, Mapping):
        return {"version": ADAPTIVE_BENCHMARK_BUNDLE_VERSION, "valid": False, "reason": "bundle_not_mapping"}
    if result.get("version") != ADAPTIVE_BENCHMARK_BUNDLE_VERSION:
        return {"version": ADAPTIVE_BENCHMARK_BUNDLE_VERSION, "valid": False, "reason": "bundle_version_mismatch"}
    if result.get("valid") is not True or result.get("state") != "observed":
        return {"version": ADAPTIVE_BENCHMARK_BUNDLE_VERSION, "valid": False, "reason": "bundle_not_valid"}
    if result.get("population_scope_complete") is not False:
        return {"version": ADAPTIVE_BENCHMARK_BUNDLE_VERSION, "valid": False, "reason": "population_scope_claim_invalid"}

    smart, reason = _selected_sequence(result.get("smart_selected"), field="smart_selected", cap=SMART_PAGE_CAP)
    if reason:
        return {"version": ADAPTIVE_BENCHMARK_BUNDLE_VERSION, "valid": False, "reason": reason}
    blind, reason = _selected_sequence(result.get("blind_selected"), field="blind_selected", cap=MAX_ADAPTIVE_TARGET)
    if reason:
        return {"version": ADAPTIVE_BENCHMARK_BUNDLE_VERSION, "valid": False, "reason": reason}
    assert smart is not None and blind is not None
    if len(smart) > len(blind):
        return {"version": ADAPTIVE_BENCHMARK_BUNDLE_VERSION, "valid": False, "reason": "smart_pages_exceed_blind_pages"}

    supplied = result.get("candidate_urls_supplied")
    unique = result.get("candidate_urls_unique")
    duplicates = result.get("duplicate_candidate_identities_removed")
    for value in (supplied, unique, duplicates):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return {"version": ADAPTIVE_BENCHMARK_BUNDLE_VERSION, "valid": False, "reason": "invalid_candidate_population_count"}
    if supplied != unique + duplicates or unique < len(blind) or unique < len(smart):
        return {"version": ADAPTIVE_BENCHMARK_BUNDLE_VERSION, "valid": False, "reason": "candidate_population_count_mismatch"}

    if result.get("smart_population_sha256") != _population_fingerprint("smart_500", smart):
        return {"version": ADAPTIVE_BENCHMARK_BUNDLE_VERSION, "valid": False, "reason": "smart_population_fingerprint_mismatch"}
    if result.get("blind_population_sha256") != _population_fingerprint("blind_1000", blind):
        return {"version": ADAPTIVE_BENCHMARK_BUNDLE_VERSION, "valid": False, "reason": "blind_population_fingerprint_mismatch"}

    finding = result.get("finding_benchmark")
    finding_integrity = validate_adaptive_benchmark(finding)
    if finding_integrity.get("valid") is not True:
        return {
            "version": ADAPTIVE_BENCHMARK_BUNDLE_VERSION,
            "valid": False,
            "reason": f"finding_benchmark_{finding_integrity.get('reason') or 'invalid'}",
        }
    priority = result.get("priority_benchmark")
    priority_integrity = validate_priority_page_benchmark(priority)
    if priority_integrity.get("valid") is not True:
        return {
            "version": ADAPTIVE_BENCHMARK_BUNDLE_VERSION,
            "valid": False,
            "reason": f"priority_benchmark_{priority_integrity.get('reason') or 'invalid'}",
        }

    if int(finding["smart_500"]["pages_assessed"]) != len(smart):
        return {"version": ADAPTIVE_BENCHMARK_BUNDLE_VERSION, "valid": False, "reason": "finding_smart_population_count_mismatch"}
    if int(finding["blind_1000"]["pages_assessed"]) != len(blind):
        return {"version": ADAPTIVE_BENCHMARK_BUNDLE_VERSION, "valid": False, "reason": "finding_blind_population_count_mismatch"}
    if int(priority["smart_pages_assessed"]) != len(smart):
        return {"version": ADAPTIVE_BENCHMARK_BUNDLE_VERSION, "valid": False, "reason": "priority_smart_population_count_mismatch"}
    if int(priority["blind_pages_assessed"]) != len(blind):
        return {"version": ADAPTIVE_BENCHMARK_BUNDLE_VERSION, "valid": False, "reason": "priority_blind_population_count_mismatch"}

    smart_set = set(smart)
    blind_set = set(blind)
    if int(priority["smart_pages_inside_blind"]) != len(smart_set & blind_set):
        return {"version": ADAPTIVE_BENCHMARK_BUNDLE_VERSION, "valid": False, "reason": "priority_inside_blind_population_mismatch"}
    if int(priority["smart_pages_outside_blind"]) != len(smart_set - blind_set):
        return {"version": ADAPTIVE_BENCHMARK_BUNDLE_VERSION, "valid": False, "reason": "priority_outside_blind_population_mismatch"}

    return {
        "version": ADAPTIVE_BENCHMARK_BUNDLE_VERSION,
        "valid": True,
        "reason": "paired_benchmark_population_integrity_verified",
    }


def summarize_adaptive_benchmark_bundle_corpus(results_by_site: Mapping[str, Any] | Any) -> dict[str, Any]:
    """Aggregate only population-bound paired benchmark results."""
    if not isinstance(results_by_site, Mapping) or not results_by_site:
        return {
            "version": ADAPTIVE_BENCHMARK_BUNDLE_CORPUS_VERSION,
            "state": "insufficient_evidence",
            "valid": False,
            "reason": "no_bundles",
            "site_count": 0,
        }

    site_ids = tuple(results_by_site.keys())
    if any(not isinstance(site_id, str) or not site_id.strip() for site_id in site_ids):
        return {
            "version": ADAPTIVE_BENCHMARK_BUNDLE_CORPUS_VERSION,
            "state": "invalid_benchmark",
            "valid": False,
            "reason": "invalid_site_identity",
            "site_count": len(site_ids),
        }
    ordered = tuple(sorted(site_ids))

    invalid: list[tuple[str, str]] = []
    for site_id in ordered:
        integrity = validate_adaptive_benchmark_bundle(results_by_site[site_id])
        if integrity.get("valid") is not True:
            invalid.append((site_id, str(integrity.get("reason") or "invalid")))
    if invalid:
        return {
            "version": ADAPTIVE_BENCHMARK_BUNDLE_CORPUS_VERSION,
            "state": "invalid_benchmark",
            "valid": False,
            "reason": "member_integrity_failed",
            "site_count": len(ordered),
            "invalid_sites": tuple(invalid),
        }

    finding_by_site = {site_id: results_by_site[site_id]["finding_benchmark"] for site_id in ordered}
    priority_by_site = {site_id: results_by_site[site_id]["priority_benchmark"] for site_id in ordered}
    finding_summary = summarize_benchmark_corpus(finding_by_site)
    priority_summary = summarize_priority_benchmark_corpus(priority_by_site)
    if finding_summary.get("valid") is not True or priority_summary.get("valid") is not True:
        return {
            "version": ADAPTIVE_BENCHMARK_BUNDLE_CORPUS_VERSION,
            "state": "invalid_benchmark",
            "valid": False,
            "reason": "nested_corpus_integrity_failed",
            "site_count": len(ordered),
        }

    if tuple(finding_summary.get("site_ids") or ()) != ordered or tuple(priority_summary.get("site_ids") or ()) != ordered:
        return {
            "version": ADAPTIVE_BENCHMARK_BUNDLE_CORPUS_VERSION,
            "state": "invalid_benchmark",
            "valid": False,
            "reason": "nested_corpus_site_population_mismatch",
            "site_count": len(ordered),
        }
    if finding_summary["smart_pages_assessed"] != priority_summary["smart_pages_assessed"]:
        return {
            "version": ADAPTIVE_BENCHMARK_BUNDLE_CORPUS_VERSION,
            "state": "invalid_benchmark",
            "valid": False,
            "reason": "nested_corpus_smart_page_count_mismatch",
            "site_count": len(ordered),
        }
    if finding_summary["blind_pages_assessed"] != priority_summary["blind_pages_assessed"]:
        return {
            "version": ADAPTIVE_BENCHMARK_BUNDLE_CORPUS_VERSION,
            "state": "invalid_benchmark",
            "valid": False,
            "reason": "nested_corpus_blind_page_count_mismatch",
            "site_count": len(ordered),
        }

    population_fingerprints = tuple(
        (
            site_id,
            str(results_by_site[site_id]["smart_population_sha256"]),
            str(results_by_site[site_id]["blind_population_sha256"]),
        )
        for site_id in ordered
    )
    return {
        "version": ADAPTIVE_BENCHMARK_BUNDLE_CORPUS_VERSION,
        "state": "observed",
        "valid": True,
        "reason": "paired_benchmark_corpus_integrity_verified",
        "site_count": len(ordered),
        "site_ids": ordered,
        "population_fingerprints": population_fingerprints,
        "full_500_vs_1000_sites": int(finding_summary["full_500_vs_1000_sites"]),
        "inventory_limited_sites": int(finding_summary["inventory_limited_sites"]),
        "smart_pages_assessed": int(finding_summary["smart_pages_assessed"]),
        "blind_pages_assessed": int(finding_summary["blind_pages_assessed"]),
        "pages_saved_by_smart": int(finding_summary["pages_saved_by_smart"]),
        "smart_finding_coverage_vs_blind": finding_summary["smart_finding_coverage_vs_blind"],
        "median_site_finding_coverage_vs_blind": finding_summary["median_site_finding_coverage_vs_blind"],
        "important_coverage_vs_blind": priority_summary["important_coverage_vs_blind"],
        "median_site_important_coverage_vs_blind": priority_summary["median_site_important_coverage_vs_blind"],
        "high_value_coverage_vs_blind": priority_summary["high_value_coverage_vs_blind"],
        "median_site_high_value_coverage_vs_blind": priority_summary["median_site_high_value_coverage_vs_blind"],
        "population_scope_complete": False,
    }
