"""Deterministic corpus aggregation for Lane-A Smart-500 marginal-gap evidence.

This module is pure and shadow-only. It validates each site with the stricter
population-integrity boundary before aggregating the blind 500->1000 tail. It does
not authorize crawl budgets, perform network work, or claim whole-site completeness.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from statistics import median
from typing import Any

from .adaptive_marginal_integrity import validate_marginal_population_integrity

ADAPTIVE_MARGINAL_CORPUS_VERSION = "adaptive_marginal_gap_corpus_v1"
_SHA256_HEX = re.compile(r"[0-9a-f]{64}")


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def _per_100(value: int, pages: int) -> float | None:
    if pages <= 0:
        return None
    return round(value * 100.0 / pages, 4)


def _median(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return round(float(median(values)), 4)


def _valid_site_id(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and value.strip() == value


def _member(site_id: str, result: Mapping[str, Any]) -> dict[str, Any]:
    integrity = validate_marginal_population_integrity(result)
    if integrity.get("valid") is not True:
        raise ValueError(f"member_invalid:{site_id}:{integrity.get('reason') or 'invalid'}")

    candidate_count = int(result["candidate_count"])
    smart_500 = result["smart"][1]
    blind_500 = result["blind"][1]
    blind_1000 = result["blind"][2]
    full_comparison = candidate_count >= 1000

    reference_findings = int(result["reference_finding_fingerprints"])
    smart_covered = int(smart_500["reference_findings_covered"])
    blind_tail_pages = int(blind_1000["pages_assessed"]) - int(blind_500["pages_assessed"])
    blind_tail_new_findings = (
        int(blind_1000["cumulative_finding_fingerprints"])
        - int(blind_500["cumulative_finding_fingerprints"])
    )

    high_state = result["high_impact_evidence_state"]
    if high_state == "observed":
        reference_high: int | None = int(result["reference_high_impact_finding_fingerprints"])
        smart_high_covered: int | None = int(smart_500["reference_high_impact_findings_covered"])
        blind_tail_new_high: int | None = (
            int(blind_1000["cumulative_high_impact_finding_fingerprints"])
            - int(blind_500["cumulative_high_impact_finding_fingerprints"])
        )
    else:
        reference_high = None
        smart_high_covered = None
        blind_tail_new_high = None

    return {
        "site_id": site_id,
        "state": "full_500_vs_1000" if full_comparison else "inventory_limited",
        "candidate_count": candidate_count,
        "smart_500_pages_assessed": int(smart_500["pages_assessed"]),
        "blind_1000_pages_assessed": int(blind_1000["pages_assessed"]),
        "blind_tail_pages": blind_tail_pages,
        "smart_500_population_fingerprint": smart_500["population_fingerprint"],
        "blind_1000_population_fingerprint": blind_1000["population_fingerprint"],
        "reference_finding_fingerprints": reference_findings,
        "smart_500_reference_findings_covered": smart_covered,
        "smart_500_missed_reference_findings": reference_findings - smart_covered,
        "smart_500_reference_finding_coverage": _ratio(smart_covered, reference_findings),
        "blind_tail_new_findings": blind_tail_new_findings,
        "blind_tail_new_finding_yield_per_100": _per_100(
            blind_tail_new_findings, blind_tail_pages
        ),
        "high_impact_evidence_state": high_state,
        "reference_high_impact_finding_fingerprints": reference_high,
        "smart_500_reference_high_impact_findings_covered": smart_high_covered,
        "smart_500_missed_reference_high_impact_findings": (
            reference_high - smart_high_covered
            if reference_high is not None and smart_high_covered is not None
            else None
        ),
        "smart_500_reference_high_impact_coverage": (
            _ratio(smart_high_covered, reference_high)
            if reference_high is not None and smart_high_covered is not None
            else None
        ),
        "blind_tail_new_high_impact_findings": blind_tail_new_high,
        "blind_tail_new_high_impact_yield_per_100": (
            _per_100(blind_tail_new_high, blind_tail_pages)
            if blind_tail_new_high is not None
            else None
        ),
    }


def summarize_marginal_gap_corpus(
    results_by_site: Mapping[str, Mapping[str, Any]] | Any,
) -> dict[str, Any]:
    """Aggregate strict per-site Smart-500 vs blind-1000 marginal-gap evidence.

    Site-scoped finding fingerprints are intentionally summed rather than globally
    deduplicated: identical textual fingerprints on two sites are two independent
    observations. Only sites with >=1000 discovered candidates contribute to the
    full 500-vs-1000 aggregate; inventory-limited sites remain visible separately.
    """
    if not isinstance(results_by_site, Mapping):
        return _invalid("results_not_mapping")

    raw_site_ids = tuple(results_by_site.keys())
    if any(not _valid_site_id(site_id) for site_id in raw_site_ids):
        return _invalid("invalid_site_identity")
    site_ids = tuple(sorted(raw_site_ids))

    members: list[dict[str, Any]] = []
    try:
        for site_id in site_ids:
            result = results_by_site[site_id]
            if not isinstance(result, Mapping):
                raise ValueError(f"member_invalid:{site_id}:result_not_mapping")
            members.append(_member(site_id, result))
    except ValueError as exc:
        return _invalid(str(exc))

    full = [member for member in members if member["state"] == "full_500_vs_1000"]
    limited = [member for member in members if member["state"] == "inventory_limited"]

    reference_findings = sum(member["reference_finding_fingerprints"] for member in full)
    covered_findings = sum(member["smart_500_reference_findings_covered"] for member in full)
    missed_findings = sum(member["smart_500_missed_reference_findings"] for member in full)
    tail_pages = sum(member["blind_tail_pages"] for member in full)
    tail_findings = sum(member["blind_tail_new_findings"] for member in full)
    site_coverages = [
        member["smart_500_reference_finding_coverage"]
        for member in full
        if member["smart_500_reference_finding_coverage"] is not None
    ]
    site_tail_yields = [
        member["blind_tail_new_finding_yield_per_100"]
        for member in full
        if member["blind_tail_new_finding_yield_per_100"] is not None
    ]

    high_observed = [member for member in full if member["high_impact_evidence_state"] == "observed"]
    if not full:
        aggregate_high_state = "not_applicable"
    elif len(high_observed) == len(full):
        aggregate_high_state = "observed"
    elif high_observed:
        aggregate_high_state = "partially_observed"
    else:
        aggregate_high_state = "not_observed"

    if aggregate_high_state == "observed":
        reference_high = sum(int(member["reference_high_impact_finding_fingerprints"]) for member in full)
        covered_high = sum(int(member["smart_500_reference_high_impact_findings_covered"]) for member in full)
        missed_high = sum(int(member["smart_500_missed_reference_high_impact_findings"]) for member in full)
        tail_high = sum(int(member["blind_tail_new_high_impact_findings"]) for member in full)
        high_coverage = _ratio(covered_high, reference_high)
        high_tail_yield = _per_100(tail_high, tail_pages)
    else:
        reference_high = None
        covered_high = None
        missed_high = None
        tail_high = None
        high_coverage = None
        high_tail_yield = None

    corpus = {
        "version": ADAPTIVE_MARGINAL_CORPUS_VERSION,
        "valid": True,
        "state": "observed" if full else "insufficient_evidence",
        "reason": "ok" if full else "no_full_500_vs_1000_sites",
        "site_count": len(members),
        "full_500_vs_1000_sites": len(full),
        "inventory_limited_sites": len(limited),
        "site_ids": site_ids,
        "sites": tuple(members),
        "full_reference_finding_fingerprints": reference_findings,
        "full_smart_500_reference_findings_covered": covered_findings,
        "full_smart_500_missed_reference_findings": missed_findings,
        "full_smart_500_reference_finding_coverage": _ratio(covered_findings, reference_findings),
        "median_full_site_reference_finding_coverage": _median(site_coverages),
        "full_blind_tail_pages": tail_pages,
        "full_blind_tail_new_findings": tail_findings,
        "full_blind_tail_new_finding_yield_per_100": _per_100(tail_findings, tail_pages),
        "median_full_site_blind_tail_finding_yield_per_100": _median(site_tail_yields),
        "full_high_impact_observed_sites": len(high_observed),
        "high_impact_evidence_state": aggregate_high_state,
        "full_reference_high_impact_finding_fingerprints": reference_high,
        "full_smart_500_reference_high_impact_findings_covered": covered_high,
        "full_smart_500_missed_reference_high_impact_findings": missed_high,
        "full_smart_500_reference_high_impact_coverage": high_coverage,
        "full_blind_tail_new_high_impact_findings": tail_high,
        "full_blind_tail_new_high_impact_yield_per_100": high_tail_yield,
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }
    validation = validate_marginal_gap_corpus(corpus)
    if validation.get("valid") is not True:
        return _invalid(f"internal_corpus_invalid:{validation.get('reason') or 'invalid'}")
    return corpus


def _invalid(reason: str) -> dict[str, Any]:
    return {
        "version": ADAPTIVE_MARGINAL_CORPUS_VERSION,
        "valid": False,
        "state": "insufficient_evidence",
        "reason": reason,
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }


def _same_optional_float(actual: Any, expected: float | None) -> bool:
    if expected is None:
        return actual is None
    if isinstance(actual, bool) or not isinstance(actual, (int, float)):
        return False
    return math.isfinite(float(actual)) and float(actual) == expected


def validate_marginal_gap_corpus(corpus: Mapping[str, Any] | Any) -> dict[str, Any]:
    """Validate transported corpus arithmetic and fail closed on aggregate drift."""
    if not isinstance(corpus, Mapping):
        return _invalid("corpus_not_mapping")
    if corpus.get("version") != ADAPTIVE_MARGINAL_CORPUS_VERSION:
        return _invalid("version_mismatch")
    if corpus.get("valid") is not True:
        return _invalid("corpus_not_valid")
    if corpus.get("population_scope_complete") is not False:
        return _invalid("population_scope_claim_invalid")
    if corpus.get("production_budget_authorized") is not False:
        return _invalid("production_budget_claim_invalid")
    if corpus.get("site_fully_understood") is not False:
        return _invalid("site_completeness_claim_invalid")

    site_count = _nonnegative_int(corpus.get("site_count"))
    full_count = _nonnegative_int(corpus.get("full_500_vs_1000_sites"))
    limited_count = _nonnegative_int(corpus.get("inventory_limited_sites"))
    if None in (site_count, full_count, limited_count):
        return _invalid("invalid_site_count")
    assert site_count is not None and full_count is not None and limited_count is not None
    if full_count + limited_count != site_count:
        return _invalid("site_population_count_mismatch")

    site_ids_raw = corpus.get("site_ids")
    members_raw = corpus.get("sites")
    if isinstance(site_ids_raw, (str, bytes, Mapping)) or not isinstance(site_ids_raw, Sequence):
        return _invalid("site_ids_invalid")
    if isinstance(members_raw, (str, bytes, Mapping)) or not isinstance(members_raw, Sequence):
        return _invalid("sites_invalid")
    site_ids = tuple(site_ids_raw)
    members = tuple(members_raw)
    if len(site_ids) != site_count or len(members) != site_count:
        return _invalid("site_population_length_mismatch")
    if any(not _valid_site_id(site_id) for site_id in site_ids):
        return _invalid("invalid_site_identity")
    if site_ids != tuple(sorted(site_ids)) or len(set(site_ids)) != len(site_ids):
        return _invalid("site_identity_order_or_uniqueness_invalid")

    full: list[Mapping[str, Any]] = []
    limited: list[Mapping[str, Any]] = []
    for expected_site_id, member in zip(site_ids, members):
        if not isinstance(member, Mapping) or member.get("site_id") != expected_site_id:
            return _invalid("member_site_identity_mismatch")
        candidate_count = _nonnegative_int(member.get("candidate_count"))
        smart_pages = _nonnegative_int(member.get("smart_500_pages_assessed"))
        blind_pages = _nonnegative_int(member.get("blind_1000_pages_assessed"))
        tail_pages = _nonnegative_int(member.get("blind_tail_pages"))
        reference = _nonnegative_int(member.get("reference_finding_fingerprints"))
        covered = _nonnegative_int(member.get("smart_500_reference_findings_covered"))
        missed = _nonnegative_int(member.get("smart_500_missed_reference_findings"))
        tail_findings = _nonnegative_int(member.get("blind_tail_new_findings"))
        if None in (candidate_count, smart_pages, blind_pages, tail_pages, reference, covered, missed, tail_findings):
            return _invalid("member_count_invalid")
        assert candidate_count is not None and smart_pages is not None and blind_pages is not None
        assert tail_pages is not None and reference is not None and covered is not None
        assert missed is not None and tail_findings is not None
        expected_state = "full_500_vs_1000" if candidate_count >= 1000 else "inventory_limited"
        if member.get("state") != expected_state:
            return _invalid("member_state_mismatch")
        if smart_pages != min(500, candidate_count) or blind_pages != min(1000, candidate_count):
            return _invalid("member_checkpoint_page_count_mismatch")
        if tail_pages != blind_pages - smart_pages:
            return _invalid("member_tail_page_count_mismatch")
        if covered > reference or missed != reference - covered:
            return _invalid("member_finding_partition_mismatch")
        if not _same_optional_float(member.get("smart_500_reference_finding_coverage"), _ratio(covered, reference)):
            return _invalid("member_finding_coverage_mismatch")
        if not _same_optional_float(member.get("blind_tail_new_finding_yield_per_100"), _per_100(tail_findings, tail_pages)):
            return _invalid("member_tail_finding_yield_mismatch")
        for field in ("smart_500_population_fingerprint", "blind_1000_population_fingerprint"):
            fingerprint = member.get(field)
            if not isinstance(fingerprint, str) or _SHA256_HEX.fullmatch(fingerprint) is None:
                return _invalid("member_population_fingerprint_invalid")

        high_state = member.get("high_impact_evidence_state")
        high_fields = (
            "reference_high_impact_finding_fingerprints",
            "smart_500_reference_high_impact_findings_covered",
            "smart_500_missed_reference_high_impact_findings",
            "smart_500_reference_high_impact_coverage",
            "blind_tail_new_high_impact_findings",
            "blind_tail_new_high_impact_yield_per_100",
        )
        if high_state == "observed":
            reference_high = _nonnegative_int(member.get(high_fields[0]))
            covered_high = _nonnegative_int(member.get(high_fields[1]))
            missed_high = _nonnegative_int(member.get(high_fields[2]))
            tail_high = _nonnegative_int(member.get(high_fields[4]))
            if None in (reference_high, covered_high, missed_high, tail_high):
                return _invalid("member_high_impact_count_invalid")
            assert reference_high is not None and covered_high is not None
            assert missed_high is not None and tail_high is not None
            if covered_high > reference_high or missed_high != reference_high - covered_high:
                return _invalid("member_high_impact_partition_mismatch")
            if not _same_optional_float(member.get(high_fields[3]), _ratio(covered_high, reference_high)):
                return _invalid("member_high_impact_coverage_mismatch")
            if not _same_optional_float(member.get(high_fields[5]), _per_100(tail_high, tail_pages)):
                return _invalid("member_tail_high_impact_yield_mismatch")
        elif high_state == "not_observed":
            if any(member.get(field) is not None for field in high_fields):
                return _invalid("member_unexpected_high_impact_metric")
        else:
            return _invalid("member_high_impact_state_invalid")

        (full if expected_state == "full_500_vs_1000" else limited).append(member)

    if len(full) != full_count or len(limited) != limited_count:
        return _invalid("member_state_population_mismatch")
    expected_state = "observed" if full else "insufficient_evidence"
    expected_reason = "ok" if full else "no_full_500_vs_1000_sites"
    if corpus.get("state") != expected_state or corpus.get("reason") != expected_reason:
        return _invalid("corpus_state_mismatch")

    reference = sum(int(member["reference_finding_fingerprints"]) for member in full)
    covered = sum(int(member["smart_500_reference_findings_covered"]) for member in full)
    missed = sum(int(member["smart_500_missed_reference_findings"]) for member in full)
    tail_pages = sum(int(member["blind_tail_pages"]) for member in full)
    tail_findings = sum(int(member["blind_tail_new_findings"]) for member in full)
    site_coverages = [
        float(member["smart_500_reference_finding_coverage"])
        for member in full
        if member.get("smart_500_reference_finding_coverage") is not None
    ]
    site_tail_yields = [
        float(member["blind_tail_new_finding_yield_per_100"])
        for member in full
        if member.get("blind_tail_new_finding_yield_per_100") is not None
    ]
    exact_counts = {
        "full_reference_finding_fingerprints": reference,
        "full_smart_500_reference_findings_covered": covered,
        "full_smart_500_missed_reference_findings": missed,
        "full_blind_tail_pages": tail_pages,
        "full_blind_tail_new_findings": tail_findings,
    }
    for field, expected in exact_counts.items():
        if corpus.get(field) != expected:
            return _invalid(f"aggregate_count_mismatch:{field}")
    expected_floats = {
        "full_smart_500_reference_finding_coverage": _ratio(covered, reference),
        "median_full_site_reference_finding_coverage": _median(site_coverages),
        "full_blind_tail_new_finding_yield_per_100": _per_100(tail_findings, tail_pages),
        "median_full_site_blind_tail_finding_yield_per_100": _median(site_tail_yields),
    }
    for field, expected in expected_floats.items():
        if not _same_optional_float(corpus.get(field), expected):
            return _invalid(f"aggregate_metric_mismatch:{field}")

    observed_full = [member for member in full if member.get("high_impact_evidence_state") == "observed"]
    if corpus.get("full_high_impact_observed_sites") != len(observed_full):
        return _invalid("high_impact_observed_site_count_mismatch")
    if not full:
        expected_high_state = "not_applicable"
    elif len(observed_full) == len(full):
        expected_high_state = "observed"
    elif observed_full:
        expected_high_state = "partially_observed"
    else:
        expected_high_state = "not_observed"
    if corpus.get("high_impact_evidence_state") != expected_high_state:
        return _invalid("aggregate_high_impact_state_mismatch")

    aggregate_high_fields = (
        "full_reference_high_impact_finding_fingerprints",
        "full_smart_500_reference_high_impact_findings_covered",
        "full_smart_500_missed_reference_high_impact_findings",
        "full_smart_500_reference_high_impact_coverage",
        "full_blind_tail_new_high_impact_findings",
        "full_blind_tail_new_high_impact_yield_per_100",
    )
    if expected_high_state == "observed":
        reference_high = sum(int(member["reference_high_impact_finding_fingerprints"]) for member in full)
        covered_high = sum(int(member["smart_500_reference_high_impact_findings_covered"]) for member in full)
        missed_high = sum(int(member["smart_500_missed_reference_high_impact_findings"]) for member in full)
        tail_high = sum(int(member["blind_tail_new_high_impact_findings"]) for member in full)
        expected_high_values = (
            reference_high,
            covered_high,
            missed_high,
            _ratio(covered_high, reference_high),
            tail_high,
            _per_100(tail_high, tail_pages),
        )
        for field, expected in zip(aggregate_high_fields, expected_high_values):
            if isinstance(expected, float) or expected is None:
                if not _same_optional_float(corpus.get(field), expected):
                    return _invalid(f"aggregate_high_impact_mismatch:{field}")
            elif corpus.get(field) != expected:
                return _invalid(f"aggregate_high_impact_mismatch:{field}")
    elif any(corpus.get(field) is not None for field in aggregate_high_fields):
        return _invalid("aggregate_high_impact_must_remain_unknown")

    return {
        "version": ADAPTIVE_MARGINAL_CORPUS_VERSION,
        "valid": True,
        "reason": "ok",
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }
