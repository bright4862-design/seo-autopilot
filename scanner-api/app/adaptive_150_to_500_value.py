"""Shadow corpus evidence for whether Smart 500 adds value over Standard 150.

Lane A already measures whether Smart 500 approximates blind 1000. This module measures
the other half of the rollout question: whether the adaptive 150->500 tranche itself
adds enough new evidence to justify further experimentation. It is pure, deterministic,
and never authorizes a production crawl budget.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from statistics import median
from typing import Any

from .adaptive_marginal_integrity import validate_marginal_population_integrity

ADAPTIVE_150_TO_500_CORPUS_VERSION = "adaptive_150_to_500_value_corpus_v1"
_SHA256_HEX = re.compile(r"[0-9a-f]{64}")


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _per_100(value: int, pages: int) -> float | None:
    return None if pages <= 0 else round(value * 100.0 / pages, 4)


def _ratio(value: int, total: int) -> float | None:
    return None if total <= 0 else round(value / total, 4)


def _median(values: Sequence[float]) -> float | None:
    return None if not values else round(float(median(values)), 4)


def _valid_site_id(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and value.strip() == value


def _fingerprint(value: Any) -> str | None:
    return value if isinstance(value, str) and _SHA256_HEX.fullmatch(value) else None


def _invalid(reason: str) -> dict[str, Any]:
    return {
        "version": ADAPTIVE_150_TO_500_CORPUS_VERSION,
        "valid": False,
        "state": "insufficient_evidence",
        "reason": reason,
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }


def _member(site_id: str, result: Mapping[str, Any]) -> dict[str, Any]:
    integrity = validate_marginal_population_integrity(result)
    if integrity.get("valid") is not True:
        raise ValueError(
            f"member_invalid:{site_id}:{integrity.get('reason') or 'invalid'}"
        )

    candidate_count = int(result["candidate_count"])
    smart150 = result["smart"][0]
    smart500 = result["smart"][1]
    pages150 = int(smart150["pages_assessed"])
    pages500 = int(smart500["pages_assessed"])
    pages_added = pages500 - pages150
    reference_findings = int(result["reference_finding_fingerprints"])
    covered150 = int(smart150["reference_findings_covered"])
    covered500 = int(smart500["reference_findings_covered"])
    new_findings = int(smart500["new_finding_fingerprints"])

    high_state = result["high_impact_evidence_state"]
    if high_state == "observed":
        reference_high: int | None = int(
            result["reference_high_impact_finding_fingerprints"]
        )
        covered_high150: int | None = int(
            smart150["reference_high_impact_findings_covered"]
        )
        covered_high500: int | None = int(
            smart500["reference_high_impact_findings_covered"]
        )
        new_high: int | None = int(
            smart500["new_high_impact_finding_fingerprints"]
        )
    else:
        reference_high = None
        covered_high150 = None
        covered_high500 = None
        new_high = None

    return {
        "site_id": site_id,
        "state": "full_150_to_500" if candidate_count >= 500 else "inventory_limited",
        "candidate_count": candidate_count,
        "smart_150_pages_assessed": pages150,
        "smart_500_pages_assessed": pages500,
        "smart_150_to_500_pages_added": pages_added,
        "smart_150_population_fingerprint": smart150["population_fingerprint"],
        "smart_500_population_fingerprint": smart500["population_fingerprint"],
        "reference_finding_fingerprints": reference_findings,
        "smart_150_reference_findings_covered": covered150,
        "smart_500_reference_findings_covered": covered500,
        "smart_150_to_500_new_findings": new_findings,
        "smart_150_to_500_new_finding_yield_per_100": _per_100(
            new_findings, pages_added
        ),
        "smart_150_to_500_new_template_keys": int(smart500["new_template_keys"]),
        "smart_150_to_500_new_families": int(smart500["new_families"]),
        "smart_150_to_500_new_route_signatures": int(
            smart500["new_route_signatures"]
        ),
        "high_impact_evidence_state": high_state,
        "reference_high_impact_finding_fingerprints": reference_high,
        "smart_150_reference_high_impact_findings_covered": covered_high150,
        "smart_500_reference_high_impact_findings_covered": covered_high500,
        "smart_150_to_500_new_high_impact_findings": new_high,
        "smart_150_to_500_new_high_impact_yield_per_100": (
            _per_100(new_high, pages_added) if new_high is not None else None
        ),
    }


def summarize_150_to_500_value_corpus(
    results_by_site: Mapping[str, Mapping[str, Any]] | Any,
) -> dict[str, Any]:
    """Aggregate only integrity-valid Smart 150->500 marginal evidence."""
    if not isinstance(results_by_site, Mapping):
        return _invalid("results_not_mapping")

    raw_site_ids = tuple(results_by_site)
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
    except (KeyError, TypeError, ValueError) as exc:
        return _invalid(str(exc))

    full = [member for member in members if member["state"] == "full_150_to_500"]
    limited = [member for member in members if member["state"] == "inventory_limited"]

    pages_added = sum(member["smart_150_to_500_pages_added"] for member in full)
    new_findings = sum(member["smart_150_to_500_new_findings"] for member in full)
    reference_findings = sum(member["reference_finding_fingerprints"] for member in full)
    covered150 = sum(member["smart_150_reference_findings_covered"] for member in full)
    covered500 = sum(member["smart_500_reference_findings_covered"] for member in full)
    site_yields = [
        member["smart_150_to_500_new_finding_yield_per_100"]
        for member in full
        if member["smart_150_to_500_new_finding_yield_per_100"] is not None
    ]

    high_observed = [
        member for member in full if member["high_impact_evidence_state"] == "observed"
    ]
    if not full:
        high_state = "not_applicable"
    elif len(high_observed) == len(full):
        high_state = "observed"
    elif high_observed:
        high_state = "partially_observed"
    else:
        high_state = "not_observed"

    if high_state == "observed":
        reference_high = sum(
            member["reference_high_impact_finding_fingerprints"] for member in full
        )
        covered_high150 = sum(
            member["smart_150_reference_high_impact_findings_covered"] for member in full
        )
        covered_high500 = sum(
            member["smart_500_reference_high_impact_findings_covered"] for member in full
        )
        new_high = sum(
            member["smart_150_to_500_new_high_impact_findings"] for member in full
        )
        site_high_yields = [
            member["smart_150_to_500_new_high_impact_yield_per_100"]
            for member in full
            if member["smart_150_to_500_new_high_impact_yield_per_100"] is not None
        ]
    else:
        reference_high = None
        covered_high150 = None
        covered_high500 = None
        new_high = None
        site_high_yields = []

    corpus = {
        "version": ADAPTIVE_150_TO_500_CORPUS_VERSION,
        "valid": True,
        "state": "observed" if full else "insufficient_evidence",
        "reason": "ok" if full else "no_full_150_to_500_sites",
        "site_count": len(members),
        "full_150_to_500_sites": len(full),
        "inventory_limited_sites": len(limited),
        "site_ids": site_ids,
        "sites": tuple(members),
        "full_smart_150_to_500_pages_added": pages_added,
        "full_smart_150_to_500_new_findings": new_findings,
        "full_smart_150_to_500_new_finding_yield_per_100": _per_100(
            new_findings, pages_added
        ),
        "median_full_site_smart_150_to_500_new_finding_yield_per_100": _median(
            site_yields
        ),
        "full_smart_150_to_500_new_template_keys": sum(
            member["smart_150_to_500_new_template_keys"] for member in full
        ),
        "full_smart_150_to_500_new_families": sum(
            member["smart_150_to_500_new_families"] for member in full
        ),
        "full_smart_150_to_500_new_route_signatures": sum(
            member["smart_150_to_500_new_route_signatures"] for member in full
        ),
        "full_reference_finding_fingerprints": reference_findings,
        "full_smart_150_reference_findings_covered": covered150,
        "full_smart_500_reference_findings_covered": covered500,
        "full_smart_150_reference_finding_coverage": _ratio(
            covered150, reference_findings
        ),
        "full_smart_500_reference_finding_coverage": _ratio(
            covered500, reference_findings
        ),
        "full_high_impact_observed_sites": len(high_observed),
        "high_impact_evidence_state": high_state,
        "full_reference_high_impact_finding_fingerprints": reference_high,
        "full_smart_150_reference_high_impact_findings_covered": covered_high150,
        "full_smart_500_reference_high_impact_findings_covered": covered_high500,
        "full_smart_150_to_500_new_high_impact_findings": new_high,
        "full_smart_150_to_500_new_high_impact_yield_per_100": (
            _per_100(new_high, pages_added) if new_high is not None else None
        ),
        "median_full_site_smart_150_to_500_new_high_impact_yield_per_100": _median(
            site_high_yields
        ),
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }
    validation = validate_150_to_500_value_corpus(corpus)
    if validation.get("valid") is not True:
        return _invalid(
            f"internal_corpus_invalid:{validation.get('reason') or 'invalid'}"
        )
    return corpus


def _same_optional_float(actual: Any, expected: float | None) -> bool:
    if expected is None:
        return actual is None
    if isinstance(actual, bool) or not isinstance(actual, (int, float)):
        return False
    return math.isfinite(float(actual)) and float(actual) == expected


def validate_150_to_500_value_corpus(corpus: Mapping[str, Any] | Any) -> dict[str, Any]:
    """Validate transported corpus arithmetic and fail closed on false claims."""
    if not isinstance(corpus, Mapping):
        return _invalid("corpus_not_mapping")
    if corpus.get("version") != ADAPTIVE_150_TO_500_CORPUS_VERSION:
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
    full_count = _nonnegative_int(corpus.get("full_150_to_500_sites"))
    limited_count = _nonnegative_int(corpus.get("inventory_limited_sites"))
    site_ids = corpus.get("site_ids")
    members = corpus.get("sites")
    if None in (site_count, full_count, limited_count):
        return _invalid("site_count_invalid")
    if (
        isinstance(site_ids, (str, bytes, Mapping))
        or not isinstance(site_ids, Sequence)
        or isinstance(members, (str, bytes, Mapping))
        or not isinstance(members, Sequence)
    ):
        return _invalid("site_population_invalid")
    site_ids = tuple(site_ids)
    members = tuple(members)
    if (
        len(site_ids) != site_count
        or len(members) != site_count
        or full_count + limited_count != site_count
        or site_ids != tuple(sorted(site_ids))
        or len(set(site_ids)) != len(site_ids)
        or any(not _valid_site_id(site_id) for site_id in site_ids)
    ):
        return _invalid("site_population_mismatch")

    full: list[Mapping[str, Any]] = []
    limited: list[Mapping[str, Any]] = []
    for site_id, member in zip(site_ids, members):
        if not isinstance(member, Mapping) or member.get("site_id") != site_id:
            return _invalid("member_site_identity_mismatch")
        candidate_count = _nonnegative_int(member.get("candidate_count"))
        pages150 = _nonnegative_int(member.get("smart_150_pages_assessed"))
        pages500 = _nonnegative_int(member.get("smart_500_pages_assessed"))
        pages_added = _nonnegative_int(member.get("smart_150_to_500_pages_added"))
        reference = _nonnegative_int(member.get("reference_finding_fingerprints"))
        covered150 = _nonnegative_int(member.get("smart_150_reference_findings_covered"))
        covered500 = _nonnegative_int(member.get("smart_500_reference_findings_covered"))
        new_findings = _nonnegative_int(member.get("smart_150_to_500_new_findings"))
        if None in (
            candidate_count, pages150, pages500, pages_added,
            reference, covered150, covered500, new_findings,
        ):
            return _invalid("member_count_invalid")
        expected_state = (
            "full_150_to_500" if candidate_count >= 500 else "inventory_limited"
        )
        if (
            member.get("state") != expected_state
            or pages150 != min(150, candidate_count)
            or pages500 != min(500, candidate_count)
            or pages_added != pages500 - pages150
            or covered150 > covered500
            or covered500 > reference
        ):
            return _invalid("member_arithmetic_invalid")
        fp150 = _fingerprint(member.get("smart_150_population_fingerprint"))
        fp500 = _fingerprint(member.get("smart_500_population_fingerprint"))
        if (
            fp150 is None
            or fp500 is None
            or (pages_added == 0 and fp150 != fp500)
            or (pages_added > 0 and fp150 == fp500)
        ):
            return _invalid("member_population_fingerprint_invalid")
        if not _same_optional_float(
            member.get("smart_150_to_500_new_finding_yield_per_100"),
            _per_100(new_findings, pages_added),
        ):
            return _invalid("member_finding_yield_mismatch")
        for field in (
            "smart_150_to_500_new_template_keys",
            "smart_150_to_500_new_families",
            "smart_150_to_500_new_route_signatures",
        ):
            if _nonnegative_int(member.get(field)) is None:
                return _invalid(f"member_{field}_invalid")

        high_state = member.get("high_impact_evidence_state")
        if high_state == "observed":
            reference_high = _nonnegative_int(
                member.get("reference_high_impact_finding_fingerprints")
            )
            covered_high150 = _nonnegative_int(
                member.get("smart_150_reference_high_impact_findings_covered")
            )
            covered_high500 = _nonnegative_int(
                member.get("smart_500_reference_high_impact_findings_covered")
            )
            new_high = _nonnegative_int(
                member.get("smart_150_to_500_new_high_impact_findings")
            )
            if None in (reference_high, covered_high150, covered_high500, new_high):
                return _invalid("member_high_impact_count_invalid")
            if (
                covered_high150 > covered_high500
                or covered_high500 > reference_high
                or new_high < covered_high500 - covered_high150
            ):
                return _invalid("member_high_impact_partition_invalid")
            if not _same_optional_float(
                member.get("smart_150_to_500_new_high_impact_yield_per_100"),
                _per_100(new_high, pages_added),
            ):
                return _invalid("member_high_impact_yield_mismatch")
        elif high_state == "not_observed":
            for field in (
                "reference_high_impact_finding_fingerprints",
                "smart_150_reference_high_impact_findings_covered",
                "smart_500_reference_high_impact_findings_covered",
                "smart_150_to_500_new_high_impact_findings",
                "smart_150_to_500_new_high_impact_yield_per_100",
            ):
                if member.get(field) is not None:
                    return _invalid("member_unobserved_high_impact_value_present")
        else:
            return _invalid("member_high_impact_state_invalid")
        (full if expected_state == "full_150_to_500" else limited).append(member)

    if len(full) != full_count or len(limited) != limited_count:
        return _invalid("site_state_count_mismatch")
    if corpus.get("state") != ("observed" if full else "insufficient_evidence"):
        return _invalid("corpus_state_mismatch")

    pages_added = sum(int(member["smart_150_to_500_pages_added"]) for member in full)
    new_findings = sum(int(member["smart_150_to_500_new_findings"]) for member in full)
    reference = sum(int(member["reference_finding_fingerprints"]) for member in full)
    covered150 = sum(int(member["smart_150_reference_findings_covered"]) for member in full)
    covered500 = sum(int(member["smart_500_reference_findings_covered"]) for member in full)
    site_yields = [
        float(member["smart_150_to_500_new_finding_yield_per_100"])
        for member in full
        if member["smart_150_to_500_new_finding_yield_per_100"] is not None
    ]
    expected = {
        "full_smart_150_to_500_pages_added": pages_added,
        "full_smart_150_to_500_new_findings": new_findings,
        "full_smart_150_to_500_new_template_keys": sum(
            int(member["smart_150_to_500_new_template_keys"]) for member in full
        ),
        "full_smart_150_to_500_new_families": sum(
            int(member["smart_150_to_500_new_families"]) for member in full
        ),
        "full_smart_150_to_500_new_route_signatures": sum(
            int(member["smart_150_to_500_new_route_signatures"]) for member in full
        ),
        "full_reference_finding_fingerprints": reference,
        "full_smart_150_reference_findings_covered": covered150,
        "full_smart_500_reference_findings_covered": covered500,
    }
    for field, value in expected.items():
        if corpus.get(field) != value:
            return _invalid(f"{field}_mismatch")
    expected_float = {
        "full_smart_150_to_500_new_finding_yield_per_100": _per_100(
            new_findings, pages_added
        ),
        "median_full_site_smart_150_to_500_new_finding_yield_per_100": _median(
            site_yields
        ),
        "full_smart_150_reference_finding_coverage": _ratio(covered150, reference),
        "full_smart_500_reference_finding_coverage": _ratio(covered500, reference),
    }
    for field, value in expected_float.items():
        if not _same_optional_float(corpus.get(field), value):
            return _invalid(f"{field}_mismatch")

    high_observed = [
        member for member in full if member.get("high_impact_evidence_state") == "observed"
    ]
    if not full:
        high_state = "not_applicable"
    elif len(high_observed) == len(full):
        high_state = "observed"
    elif high_observed:
        high_state = "partially_observed"
    else:
        high_state = "not_observed"
    if (
        corpus.get("high_impact_evidence_state") != high_state
        or corpus.get("full_high_impact_observed_sites") != len(high_observed)
    ):
        return _invalid("high_impact_state_mismatch")

    if high_state == "observed":
        reference_high = sum(
            int(member["reference_high_impact_finding_fingerprints"]) for member in full
        )
        covered_high150 = sum(
            int(member["smart_150_reference_high_impact_findings_covered"]) for member in full
        )
        covered_high500 = sum(
            int(member["smart_500_reference_high_impact_findings_covered"]) for member in full
        )
        new_high = sum(
            int(member["smart_150_to_500_new_high_impact_findings"]) for member in full
        )
        high_site_yields = [
            float(member["smart_150_to_500_new_high_impact_yield_per_100"])
            for member in full
            if member["smart_150_to_500_new_high_impact_yield_per_100"] is not None
        ]
        high_expected = {
            "full_reference_high_impact_finding_fingerprints": reference_high,
            "full_smart_150_reference_high_impact_findings_covered": covered_high150,
            "full_smart_500_reference_high_impact_findings_covered": covered_high500,
            "full_smart_150_to_500_new_high_impact_findings": new_high,
        }
        for field, value in high_expected.items():
            if corpus.get(field) != value:
                return _invalid(f"{field}_mismatch")
        high_float = {
            "full_smart_150_to_500_new_high_impact_yield_per_100": _per_100(
                new_high, pages_added
            ),
            "median_full_site_smart_150_to_500_new_high_impact_yield_per_100": _median(
                high_site_yields
            ),
        }
        for field, value in high_float.items():
            if not _same_optional_float(corpus.get(field), value):
                return _invalid(f"{field}_mismatch")
    else:
        for field in (
            "full_reference_high_impact_finding_fingerprints",
            "full_smart_150_reference_high_impact_findings_covered",
            "full_smart_500_reference_high_impact_findings_covered",
            "full_smart_150_to_500_new_high_impact_findings",
            "full_smart_150_to_500_new_high_impact_yield_per_100",
            "median_full_site_smart_150_to_500_new_high_impact_yield_per_100",
        ):
            if corpus.get(field) is not None:
                return _invalid(f"unexpected_{field}")

    return {
        "version": ADAPTIVE_150_TO_500_CORPUS_VERSION,
        "valid": True,
        "state": corpus["state"],
        "reason": "ok",
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }
