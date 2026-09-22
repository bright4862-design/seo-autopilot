"""Strict population-integrity checks for Lane-A marginal crawl benchmarks.

This module is pure and shadow-only. It does not authorize crawl budgets or perform
network/persistence work. It layers stronger population invariants over the existing
``adaptive_marginal_benchmark_v1`` arithmetic validator so transported benchmark
evidence cannot silently shrink a checkpoint population or misrepresent a full
inventory-limited population as incomplete.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from .adaptive_crawl import MAX_ADAPTIVE_TARGET
from .adaptive_marginal_benchmark import (
    MARGINAL_CHECKPOINTS,
    validate_marginal_yield_benchmark,
)

ADAPTIVE_MARGINAL_POPULATION_INTEGRITY_VERSION = (
    "adaptive_marginal_population_integrity_v1"
)
_SHA256_HEX = re.compile(r"[0-9a-f]{64}")


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _fail(reason: str) -> dict[str, Any]:
    return {
        "version": ADAPTIVE_MARGINAL_POPULATION_INTEGRITY_VERSION,
        "valid": False,
        "reason": reason,
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }


def validate_marginal_population_integrity(
    result: Mapping[str, Any] | Any,
) -> dict[str, Any]:
    """Validate exact checkpoint populations and ceiling-equivalence invariants.

    The base marginal validator checks arithmetic consistency. This stricter layer
    additionally proves that every 150/500/1000 checkpoint contains the exact number
    of pages the deterministic selector is supposed to return, fingerprints use the
    published lowercase SHA-256 shape, unchanged populations retain fingerprints,
    discovery-cardinality metrics cannot exceed page cardinality, and a Smart crawl
    that contains the entire <=1000-page candidate inventory agrees exactly with the
    blind reference evidence population.
    """
    base = validate_marginal_yield_benchmark(result)
    if base.get("valid") is not True:
        return _fail(f"base:{base.get('reason') or 'invalid'}")
    if not isinstance(result, Mapping):
        return _fail("result_not_mapping")

    candidate_count = _nonnegative_int(result.get("candidate_count"))
    reference_findings = _nonnegative_int(result.get("reference_finding_fingerprints"))
    if candidate_count is None or reference_findings is None:
        return _fail("invalid_reference_count")

    high_state = result.get("high_impact_evidence_state")
    reference_high = result.get("reference_high_impact_finding_fingerprints")
    if high_state == "observed":
        reference_high_int = _nonnegative_int(reference_high)
        if reference_high_int is None:
            return _fail("invalid_high_impact_reference_count")
    else:
        reference_high_int = None

    expected_final_pages = min(candidate_count, MAX_ADAPTIVE_TARGET)

    for strategy in ("smart", "blind"):
        rows = result.get(strategy)
        if isinstance(rows, (str, bytes, Mapping)) or not isinstance(rows, Sequence):
            return _fail(f"{strategy}_curve_invalid")

        previous_pages: int | None = None
        previous_fingerprint: str | None = None
        for target, row in zip(MARGINAL_CHECKPOINTS, rows):
            if not isinstance(row, Mapping):
                return _fail(f"{strategy}_row_invalid")

            pages = _nonnegative_int(row.get("pages_assessed"))
            expected_pages = min(target, candidate_count, MAX_ADAPTIVE_TARGET)
            if pages != expected_pages:
                return _fail(f"{strategy}_checkpoint_population_mismatch")

            fingerprint = row.get("population_fingerprint")
            if not isinstance(fingerprint, str) or _SHA256_HEX.fullmatch(fingerprint) is None:
                return _fail(f"{strategy}_population_fingerprint_invalid")

            for field in (
                "cumulative_template_keys",
                "cumulative_families",
                "cumulative_route_signatures",
            ):
                cardinality = _nonnegative_int(row.get(field))
                if cardinality is None or cardinality > pages:
                    return _fail(f"{strategy}_{field}_cardinality_invalid")

            if previous_pages is not None and previous_fingerprint is not None:
                if pages == previous_pages and fingerprint != previous_fingerprint:
                    return _fail(f"{strategy}_unchanged_population_fingerprint_mismatch")
                if pages > previous_pages and fingerprint == previous_fingerprint:
                    return _fail(f"{strategy}_expanded_population_fingerprint_mismatch")

            previous_pages = pages
            previous_fingerprint = fingerprint

        final_row = rows[-1]
        if final_row.get("pages_assessed") != expected_final_pages:
            return _fail(f"{strategy}_final_population_mismatch")

    blind_final = result["blind"][-1]
    if blind_final.get("reference_findings_covered") != reference_findings:
        return _fail("blind_reference_findings_not_exact")
    if blind_final.get("cumulative_finding_fingerprints") != reference_findings:
        return _fail("blind_reference_findings_population_mismatch")

    if high_state == "observed":
        assert reference_high_int is not None
        if blind_final.get("reference_high_impact_findings_covered") != reference_high_int:
            return _fail("blind_reference_high_impact_not_exact")
        if blind_final.get("cumulative_high_impact_finding_fingerprints") != reference_high_int:
            return _fail("blind_reference_high_impact_population_mismatch")

    # At <=1000 unique candidates, both strategies contain the complete candidate
    # inventory at the final checkpoint. Their evidence sets must therefore agree
    # exactly even if adaptive selection reached that population in a different order.
    if candidate_count <= MAX_ADAPTIVE_TARGET:
        smart_final = result["smart"][-1]
        if smart_final.get("reference_findings_covered") != reference_findings:
            return _fail("smart_full_inventory_reference_findings_not_exact")
        if smart_final.get("cumulative_finding_fingerprints") != reference_findings:
            return _fail("smart_full_inventory_findings_population_mismatch")
        if high_state == "observed":
            assert reference_high_int is not None
            if smart_final.get("reference_high_impact_findings_covered") != reference_high_int:
                return _fail("smart_full_inventory_reference_high_impact_not_exact")
            if smart_final.get("cumulative_high_impact_finding_fingerprints") != reference_high_int:
                return _fail("smart_full_inventory_high_impact_population_mismatch")

    return {
        "version": ADAPTIVE_MARGINAL_POPULATION_INTEGRITY_VERSION,
        "valid": True,
        "reason": "ok",
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }
