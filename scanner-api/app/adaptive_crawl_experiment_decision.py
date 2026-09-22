"""Shadow decision joining Smart 150->500 value with Smart-500 vs blind-1000 evidence.

This module answers the complete Lane-A experiment question without changing a crawl
budget: does going beyond the unchanged Standard 150 add material evidence, and if so,
is Smart 500 efficient enough relative to the blind 1,000-page reference? A positive
result is an engineering experiment candidate only. It never authorizes production.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from .adaptive_150_to_500_value import (
    ADAPTIVE_150_TO_500_CORPUS_VERSION,
    validate_150_to_500_value_corpus,
)
from .adaptive_smart_500_decision import evaluate_population_bound_smart_500

ADAPTIVE_CRAWL_EXPERIMENT_DECISION_VERSION = "adaptive_crawl_experiment_decision_v1"

DEFAULT_MIN_150_TO_500_FINDING_YIELD_PER_100 = 1.0
DEFAULT_MIN_MEDIAN_SITE_150_TO_500_FINDING_YIELD_PER_100 = 1.0
DEFAULT_MIN_150_TO_500_REFERENCE_COVERAGE_GAIN = 0.05


def _result(decision: str, reason: str, **extra: Any) -> dict[str, Any]:
    return {
        "version": ADAPTIVE_CRAWL_EXPERIMENT_DECISION_VERSION,
        "decision": decision,
        "reason": reason,
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
        **extra,
    }


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _finite_nonnegative(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number) or number < 0.0:
        return None
    return number


def _ratio(value: Any) -> float | None:
    number = _finite_nonnegative(value)
    if number is None or number > 1.0:
        return None
    return number


def _threshold(value: Any, *, field: str, ratio: bool = False) -> tuple[float | None, str | None]:
    number = _ratio(value) if ratio else _finite_nonnegative(value)
    if number is None:
        return None, f"invalid_threshold:{field}"
    return number, None


def _site_ids(value: Any) -> tuple[str, ...] | None:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        return None
    ids = tuple(value)
    if (
        any(not isinstance(site_id, str) or not site_id or site_id.strip() != site_id for site_id in ids)
        or len(set(ids)) != len(ids)
        or ids != tuple(sorted(ids))
    ):
        return None
    return ids


def _value_smart_500_fingerprints(
    value_corpus: Mapping[str, Any], expected_site_ids: tuple[str, ...]
) -> dict[str, str] | None:
    members = value_corpus.get("sites")
    if isinstance(members, (str, bytes, Mapping)) or not isinstance(members, Sequence):
        return None
    if len(members) != len(expected_site_ids):
        return None
    result: dict[str, str] = {}
    for member in members:
        if not isinstance(member, Mapping):
            return None
        site_id = member.get("site_id")
        fingerprint = member.get("smart_500_population_fingerprint")
        if (
            not isinstance(site_id, str)
            or not site_id
            or site_id.strip() != site_id
            or not isinstance(fingerprint, str)
            or not fingerprint
            or site_id in result
        ):
            return None
        result[site_id] = fingerprint
    if tuple(sorted(result)) != expected_site_ids:
        return None
    return result


def _decision_smart_500_fingerprints(
    smart_decision: Mapping[str, Any], expected_site_ids: tuple[str, ...]
) -> dict[str, str] | None:
    entries = smart_decision.get("population_fingerprints")
    if isinstance(entries, (str, bytes, Mapping)) or not isinstance(entries, Sequence):
        return None
    if len(entries) != len(expected_site_ids):
        return None
    result: dict[str, str] = {}
    for entry in entries:
        if isinstance(entry, (str, bytes, Mapping)) or not isinstance(entry, Sequence):
            return None
        parts = tuple(entry)
        if len(parts) != 3:
            return None
        site_id, smart_fingerprint, blind_fingerprint = parts
        if (
            not isinstance(site_id, str)
            or not site_id
            or site_id.strip() != site_id
            or not isinstance(smart_fingerprint, str)
            or not smart_fingerprint
            or not isinstance(blind_fingerprint, str)
            or not blind_fingerprint
            or site_id in result
        ):
            return None
        result[site_id] = smart_fingerprint
    if tuple(sorted(result)) != expected_site_ids:
        return None
    return result


def evaluate_adaptive_crawl_experiment(
    value_corpus: Mapping[str, Any] | Any,
    benchmark_corpus: Mapping[str, Any] | Any,
    marginal_corpus: Mapping[str, Any] | Any,
    *,
    min_150_to_500_finding_yield_per_100: float = DEFAULT_MIN_150_TO_500_FINDING_YIELD_PER_100,
    min_median_site_150_to_500_finding_yield_per_100: float = DEFAULT_MIN_MEDIAN_SITE_150_TO_500_FINDING_YIELD_PER_100,
    min_150_to_500_reference_coverage_gain: float = DEFAULT_MIN_150_TO_500_REFERENCE_COVERAGE_GAIN,
    require_150_to_500_high_impact_observed: bool = True,
    **smart_500_thresholds: Any,
) -> dict[str, Any]:
    """Return a fail-closed, shadow-only recommendation across both adaptive tranches.

    Decision order is deliberate. First prove that Smart 150->500 adds enough value to
    justify an experiment beyond the unchanged Standard 150. Only then evaluate whether
    Smart 500 is efficient enough versus blind 1,000. A Smart-500 candidate additionally
    requires exact site identity and Smart-500 population fingerprints to agree across
    the two evidence families.
    """
    if not isinstance(value_corpus, Mapping):
        return _result("insufficient_evidence", "value_corpus_not_mapping")
    if value_corpus.get("version") != ADAPTIVE_150_TO_500_CORPUS_VERSION:
        return _result("insufficient_evidence", "value_corpus_version_mismatch")

    value_integrity = validate_150_to_500_value_corpus(value_corpus)
    if value_integrity.get("valid") is not True:
        return _result(
            "insufficient_evidence",
            f"value_corpus_integrity_failed:{value_integrity.get('reason') or 'invalid'}",
        )
    if value_corpus.get("state") != "observed":
        return _result("insufficient_evidence", "no_full_150_to_500_evidence")

    min_yield, error = _threshold(
        min_150_to_500_finding_yield_per_100,
        field="min_150_to_500_finding_yield_per_100",
    )
    if error:
        return _result("insufficient_evidence", error)
    min_median_yield, error = _threshold(
        min_median_site_150_to_500_finding_yield_per_100,
        field="min_median_site_150_to_500_finding_yield_per_100",
    )
    if error:
        return _result("insufficient_evidence", error)
    min_coverage_gain, error = _threshold(
        min_150_to_500_reference_coverage_gain,
        field="min_150_to_500_reference_coverage_gain",
        ratio=True,
    )
    if error:
        return _result("insufficient_evidence", error)
    if not isinstance(require_150_to_500_high_impact_observed, bool):
        return _result(
            "insufficient_evidence",
            "invalid_threshold:require_150_to_500_high_impact_observed",
        )
    assert min_yield is not None and min_median_yield is not None and min_coverage_gain is not None

    full_sites = _nonnegative_int(value_corpus.get("full_150_to_500_sites"))
    aggregate_yield = _finite_nonnegative(
        value_corpus.get("full_smart_150_to_500_new_finding_yield_per_100")
    )
    median_yield = _finite_nonnegative(
        value_corpus.get("median_full_site_smart_150_to_500_new_finding_yield_per_100")
    )
    coverage150 = _ratio(value_corpus.get("full_smart_150_reference_finding_coverage"))
    coverage500 = _ratio(value_corpus.get("full_smart_500_reference_finding_coverage"))
    if (
        full_sites is None
        or full_sites <= 0
        or aggregate_yield is None
        or median_yield is None
        or coverage150 is None
        or coverage500 is None
        or coverage500 < coverage150
    ):
        return _result("insufficient_evidence", "value_metric_missing_or_invalid")
    coverage_gain = round(coverage500 - coverage150, 4)

    high_state = value_corpus.get("high_impact_evidence_state")
    high_observed_sites = _nonnegative_int(value_corpus.get("full_high_impact_observed_sites"))
    if require_150_to_500_high_impact_observed and (
        high_state != "observed" or high_observed_sites != full_sites
    ):
        return _result("insufficient_evidence", "150_to_500_high_impact_evidence_not_fully_observed")

    failed_150_to_500: list[str] = []
    if aggregate_yield < min_yield:
        failed_150_to_500.append("aggregate_150_to_500_finding_yield")
    if median_yield < min_median_yield:
        failed_150_to_500.append("median_site_150_to_500_finding_yield")
    if coverage_gain < min_coverage_gain:
        failed_150_to_500.append("150_to_500_reference_coverage_gain")

    value_evidence = {
        "full_150_to_500_sites": full_sites,
        "smart_150_to_500_new_finding_yield_per_100": aggregate_yield,
        "median_site_smart_150_to_500_new_finding_yield_per_100": median_yield,
        "smart_150_reference_finding_coverage": coverage150,
        "smart_500_reference_finding_coverage": coverage500,
        "smart_150_to_500_reference_finding_coverage_gain": coverage_gain,
        "high_impact_evidence_state": high_state,
        "value_thresholds": {
            "min_150_to_500_finding_yield_per_100": min_yield,
            "min_median_site_150_to_500_finding_yield_per_100": min_median_yield,
            "min_150_to_500_reference_coverage_gain": min_coverage_gain,
            "require_150_to_500_high_impact_observed": require_150_to_500_high_impact_observed,
        },
    }
    if failed_150_to_500:
        return _result(
            "standard_150_reference_retained",
            "150_to_500_value_thresholds_not_met",
            failed_thresholds=tuple(failed_150_to_500),
            **value_evidence,
        )

    smart_decision = evaluate_population_bound_smart_500(
        benchmark_corpus,
        marginal_corpus,
        **smart_500_thresholds,
    )
    downstream_decision = smart_decision.get("decision")
    if downstream_decision == "insufficient_evidence":
        return _result(
            "insufficient_evidence",
            "smart_500_evidence_insufficient",
            smart_500_decision=smart_decision,
            **value_evidence,
        )
    if downstream_decision != "smart_500_candidate":
        return _result(
            "blind_1000_reference_retained",
            "smart_500_acceptance_not_met",
            smart_500_decision=smart_decision,
            **value_evidence,
        )

    value_site_ids = _site_ids(value_corpus.get("site_ids"))
    decision_site_ids = _site_ids(smart_decision.get("site_ids"))
    if value_site_ids is None or decision_site_ids is None or value_site_ids != decision_site_ids:
        return _result("insufficient_evidence", "cross_stage_site_population_mismatch")

    value_fingerprints = _value_smart_500_fingerprints(value_corpus, value_site_ids)
    decision_fingerprints = _decision_smart_500_fingerprints(smart_decision, decision_site_ids)
    if value_fingerprints is None or decision_fingerprints is None:
        return _result("insufficient_evidence", "cross_stage_population_fingerprint_set_invalid")
    if value_fingerprints != decision_fingerprints:
        return _result("insufficient_evidence", "cross_stage_smart_500_population_mismatch")

    full_comparison_sites = _nonnegative_int(smart_decision.get("full_comparison_sites"))
    if full_comparison_sites is None or full_comparison_sites <= 0 or full_comparison_sites > full_sites:
        return _result("insufficient_evidence", "cross_stage_full_site_count_invalid")

    return _result(
        "smart_500_experiment_candidate",
        "150_to_500_value_and_500_to_1000_efficiency_met",
        failed_thresholds=(),
        site_ids=value_site_ids,
        smart_500_population_fingerprints=tuple(
            (site_id, value_fingerprints[site_id]) for site_id in value_site_ids
        ),
        full_comparison_sites=full_comparison_sites,
        smart_500_decision=smart_decision,
        **value_evidence,
    )
