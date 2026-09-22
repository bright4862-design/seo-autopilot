"""Truthful representativeness coverage for Lane-C performance samples.

This module does not choose browser/provider execution, call a provider, or grant an
execution budget. It first requires the deterministic sample/population binding and
then describes how much of the bound template and positive sampler-weight population
is represented by the bounded sample.

The sampler weight is selection metadata only. It is not repair priority, customer
scoring, or a performance result.
"""
from __future__ import annotations

from typing import Any, Iterable

from app.nextgen_browser_performance import (
    REPRESENTATIVE_SAMPLE_VERSION,
    _candidate_rank,
    _eligible,
    _family,
    _url,
    _weight,
)
from app.nextgen_browser_performance_sample_binding import (
    SAMPLE_BINDING_VERSION,
    validate_representative_sample_binding,
)

SAMPLE_COVERAGE_VERSION = "nextgen_performance_sample_coverage_v1"
SAMPLE_COVERAGE_INTEGRITY_VERSION = "nextgen_performance_sample_coverage_integrity_v1"

_COVERAGE_FIELDS = (
    "version",
    "sample_contract",
    "binding_contract",
    "state",
    "reason",
    "binding_valid",
    "binding_reasons",
    "eligible_pages",
    "selected_pages",
    "template_families",
    "covered_template_families",
    "template_family_coverage_ratio",
    "weighted_pages",
    "selected_weighted_pages",
    "weighted_page_coverage_ratio",
    "population_weight",
    "selected_weight",
    "weight_coverage_ratio",
    "highest_unselected_weight",
    "omitted_template_families",
    "unselected_weighted_families",
)


def _rounded(value: float) -> float:
    return round(float(value), 6)


def _base(*, state: str, reason: str, binding: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": SAMPLE_COVERAGE_VERSION,
        "sample_contract": REPRESENTATIVE_SAMPLE_VERSION,
        "binding_contract": SAMPLE_BINDING_VERSION,
        "state": state,
        "reason": reason,
        "binding_valid": binding.get("valid") is True,
        "binding_reasons": list(binding.get("reasons") or []),
        "eligible_pages": None,
        "selected_pages": None,
        "template_families": None,
        "covered_template_families": None,
        "template_family_coverage_ratio": None,
        "weighted_pages": None,
        "selected_weighted_pages": None,
        "weighted_page_coverage_ratio": None,
        "population_weight": None,
        "selected_weight": None,
        "weight_coverage_ratio": None,
        "highest_unselected_weight": None,
        "omitted_template_families": [],
        "unselected_weighted_families": [],
    }


def _deduped_eligible_population(pages: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for page in pages:
        if not _eligible(page):
            continue
        key = _url(page)
        current = unique.get(key)
        if current is None or _candidate_rank(page) < _candidate_rank(current):
            unique[key] = page
    return unique


def build_representative_sample_coverage(
    pages: Iterable[dict[str, Any]],
    sample: Any,
) -> dict[str, Any]:
    """Describe representation of the exact population bound to ``sample``.

    Positive sampler weights are reported separately from template-family coverage.
    A bounded sample can therefore truthfully show complete template coverage while
    still showing incomplete weighted-page coverage. No result authorizes execution.
    """
    try:
        authoritative_pages = list(pages)
    except Exception:
        binding = {
            "valid": False,
            "reasons": ["candidate_population_unreadable"],
        }
        return _base(state="not_verified", reason="sample_binding_invalid", binding=binding)

    binding = validate_representative_sample_binding(authoritative_pages, sample)
    if binding.get("valid") is not True:
        return _base(state="not_verified", reason="sample_binding_invalid", binding=binding)

    population = _deduped_eligible_population(authoritative_pages)
    if not population:
        return _base(
            state="not_verified",
            reason="eligible_sample_population_empty",
            binding=binding,
        )

    selected_rows = sample.get("pages") if isinstance(sample, dict) else []
    selected_rows = selected_rows if isinstance(selected_rows, list) else []
    selected_urls = {
        row.get("url")
        for row in selected_rows
        if isinstance(row, dict) and isinstance(row.get("url"), str)
    }

    population_families = {_family(page) for page in population.values()}
    selected_families = {
        row.get("template_family")
        for row in selected_rows
        if isinstance(row, dict) and isinstance(row.get("template_family"), str)
    }
    selected_families &= population_families

    weights = {url: _weight(page) for url, page in population.items()}
    weighted_urls = {url for url, weight in weights.items() if weight > 0.0}
    selected_weighted_urls = weighted_urls & selected_urls
    unselected_weighted_urls = weighted_urls - selected_urls

    population_weight = sum(weights.values())
    selected_weight = sum(weights[url] for url in selected_urls if url in weights)

    omitted_families = list(sample.get("omitted_template_families") or [])
    unselected_weighted_families = sorted(
        {_family(population[url]) for url in unselected_weighted_urls}
    )

    coverage = _base(state="verified", reason="sample_population_bound", binding=binding)
    coverage.update({
        "eligible_pages": len(population),
        "selected_pages": len(selected_urls),
        "template_families": len(population_families),
        "covered_template_families": len(selected_families),
        "template_family_coverage_ratio": _rounded(
            len(selected_families) / len(population_families)
        ),
        "weighted_pages": len(weighted_urls),
        "selected_weighted_pages": len(selected_weighted_urls),
        "weighted_page_coverage_ratio": (
            _rounded(len(selected_weighted_urls) / len(weighted_urls))
            if weighted_urls else None
        ),
        "population_weight": _rounded(population_weight),
        "selected_weight": _rounded(selected_weight),
        "weight_coverage_ratio": (
            _rounded(selected_weight / population_weight)
            if population_weight > 0.0 else None
        ),
        "highest_unselected_weight": (
            _rounded(max(weights[url] for url in unselected_weighted_urls))
            if unselected_weighted_urls else None
        ),
        "omitted_template_families": omitted_families,
        "unselected_weighted_families": unselected_weighted_families,
    })
    return coverage


def validate_representative_sample_coverage_contract(
    pages: Iterable[dict[str, Any]],
    sample: Any,
    coverage: Any,
) -> dict[str, Any]:
    """Recompute and integrity-check a transported sample coverage artifact."""
    if not isinstance(coverage, dict):
        return {
            "version": SAMPLE_COVERAGE_INTEGRITY_VERSION,
            "contract": SAMPLE_COVERAGE_VERSION,
            "valid": False,
            "reasons": ["coverage_not_object"],
        }
    try:
        authoritative_pages = list(pages)
    except Exception:
        return {
            "version": SAMPLE_COVERAGE_INTEGRITY_VERSION,
            "contract": SAMPLE_COVERAGE_VERSION,
            "valid": False,
            "reasons": ["candidate_population_unreadable"],
        }

    expected = build_representative_sample_coverage(authoritative_pages, sample)
    reasons = [
        f"{field}_mismatch"
        for field in _COVERAGE_FIELDS
        if coverage.get(field) != expected.get(field)
    ]
    return {
        "version": SAMPLE_COVERAGE_INTEGRITY_VERSION,
        "contract": SAMPLE_COVERAGE_VERSION,
        "valid": not reasons,
        "reasons": sorted(set(reasons)),
    }
