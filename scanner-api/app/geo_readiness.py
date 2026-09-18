"""Experimental, pure GEO aggregation; no extraction, fetching or authority sealing.

Inputs are classified observations from a future trusted adapter. This module
does not establish their truth and is deliberately not wired into scan results.
"""
from dataclasses import dataclass
from fractions import Fraction
from types import MappingProxyType

VERSION = "geo_readiness_v1_experimental"
CHECKS = MappingProxyType({
    "search_policy": "access", "indexability": "access", "discovery": "access",
    "main_text": "clarity", "page_identity": "clarity", "template_integrity": "clarity",
    "subject_identity": "entity", "entity_details": "entity", "schema_agreement": "entity",
    "accountability": "support", "date_context": "support", "source_attribution": "support",
})
DIMENSIONS = ("access", "clarity", "entity", "support")
STATES = frozenset({"pass", "fail", "not_applicable", "not_verified"})


@dataclass(frozen=True)
class Observation:
    page_id: str
    check_id: str
    state: str
    evidence_ref: str = ""
    reason: str = ""


def _bounded_text(value, maximum=200):
    return isinstance(value, str) and len(value) <= maximum and bool(value.strip())


def _display(value):
    return round(float(value), 6)


def evaluate_geo(page_ids, observations, *, parent_authoritative=False,
                 entry_verified=False, access_limited=False):
    """Aggregate a complete page/check matrix, filling omitted cells as unknown.

    Equal dimension weights; equal applicable check weights within a dimension;
    equal applicable/unknown page weights within each check. Gates use exact
    rational values, never rounded display percentages.
    """
    if any(type(flag) is not bool for flag in
           (parent_authoritative, entry_verified, access_limited)):
        raise ValueError("Assessment gates require explicit booleans")
    if not isinstance(page_ids, (list, tuple)) or len(page_ids) > 150:
        raise ValueError("Expected at most 150 page IDs")
    if any(not _bounded_text(page) for page in page_ids) or len(set(page_ids)) != len(page_ids):
        raise ValueError("Page IDs must be unique bounded nonempty strings")
    if not isinstance(observations, (list, tuple)) or len(observations) > 150 * len(CHECKS):
        raise ValueError("Observation matrix exceeds Standard 150 bounds")
    pages = set(page_ids)
    matrix = {}
    for row in observations:
        if not isinstance(row, Observation):
            raise ValueError("Expected typed observation")
        if not all(isinstance(v, str) for v in
                   (row.page_id, row.check_id, row.state, row.evidence_ref, row.reason)):
            raise ValueError("Observation values must be strings")
        if row.page_id not in pages or row.check_id not in CHECKS or row.state not in STATES:
            raise ValueError("Unknown page, check or observation state")
        if len(row.reason) > 500 or len(row.evidence_ref) > 200:
            raise ValueError("Observation metadata exceeds bounds")
        if row.state in {"pass", "fail"} and not _bounded_text(row.evidence_ref):
            raise ValueError("Verified observations require an evidence reference")
        if row.state == "not_applicable" and not _bounded_text(row.reason, 500):
            raise ValueError("Not-applicable observations require a reason")
        key = (row.page_id, row.check_id)
        if key in matrix:
            raise ValueError("Duplicate page/check observation")
        matrix[key] = row

    dimensions, masses = {}, []
    for dimension in DIMENSIONS:
        checks, check_masses = {}, []
        for check, owner in CHECKS.items():
            if owner != dimension:
                continue
            counts = {state: 0 for state in sorted(STATES)}
            for page in sorted(pages):
                row = matrix.get((page, check))
                counts[row.state if row else "not_verified"] += 1
            applicable = len(pages) - counts["not_applicable"]
            verified = counts["pass"] + counts["fail"]
            checks[check] = {"counts": counts, "applicable_or_unknown": applicable}
            if applicable:
                check_masses.append((Fraction(counts["pass"], applicable),
                                     Fraction(verified, applicable)))
        passed_mass = sum((p for p, _ in check_masses), Fraction()) / len(check_masses) if check_masses else Fraction()
        verified_mass = sum((v for _, v in check_masses), Fraction()) / len(check_masses) if check_masses else Fraction()
        masses.append((passed_mass, verified_mass))
        dimensions[dimension] = {
            "coverage": _display(verified_mass), "checks": checks,
            "score": _display(100 * passed_mass / verified_mass) if verified_mass else None,
        }

    passed = sum((p for p, _ in masses), Fraction()) / 4
    verified = sum((v for _, v in masses), Fraction()) / 4
    reasons = []
    if not parent_authoritative:
        reasons.append("parent_not_authoritative")
    if not entry_verified:
        reasons.append("entry_not_verified")
    if verified < Fraction(4, 5):
        reasons.append("overall_coverage_below_80_percent")
    for dimension, (_, coverage) in zip(DIMENSIONS, masses):
        if coverage < Fraction(1, 2):
            reasons.append(f"{dimension}_coverage_below_50_percent")
    status = "access_limited" if access_limited else "insufficient_evidence" if reasons else "assessed"
    numeric = 100 * passed / verified if verified else Fraction()
    score = int(numeric + Fraction(1, 2)) if status == "assessed" else None
    # Never surface content diagnostics from a globally access-limited scan.
    if access_limited:
        dimensions = {}
    return {
        "geo_readiness_version": VERSION,
        "assessment_status": status, "score": score,
        "coverage": 0.0 if access_limited else _display(verified),
        "score_bounds": None if access_limited else {
            "lower": _display(100 * passed), "upper": _display(100 * (passed + 1 - verified)),
        },
        "bounds_kind": "unknown_outcome_range_not_statistical_confidence",
        "sample_pages": len(pages), "dimensions": dimensions,
        "reasons": ["access_limited"] if access_limited else reasons,
        "authority_verified": False,
    }
