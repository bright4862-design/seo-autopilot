"""Fail-closed integrity checks for Lane-C browser/performance evidence.

The Lane-C normalizers emit pure, versioned dictionaries.  This module validates
those dictionaries before a future serialized integrator treats them as trusted
evidence.  It performs no network I/O and does not create customer Fixes, scores,
or persistence writes.
"""
from __future__ import annotations

from math import isfinite
from typing import Any

from app.nextgen_browser_performance import (
    CRITICAL_PARITY_VERSION,
    FIELD_METRICS,
    FIELD_PERFORMANCE_VERSION,
    LIGHTHOUSE_AUDITS,
    LIGHTHOUSE_EVIDENCE_VERSION,
    LIGHTHOUSE_OPPORTUNITIES,
    MAX_PERFORMANCE_SAMPLE_PAGES,
    PERFORMANCE_EVIDENCE_VERSION,
    PROVIDER_STATES,
    REPRESENTATIVE_SAMPLE_VERSION,
)

INTEGRITY_VERSION = "nextgen_browser_performance_integrity_v1"
PARITY_STATES = {"not_verified", "matched", "material_delta"}
PARITY_FIELD_STATES = {
    "not_verified",
    "same",
    "changed",
    "raw_missing_rendered_present",
    "raw_present_rendered_missing",
}
PARITY_FIELDS = {
    "title",
    "h1",
    "canonical",
    "indexability",
    "main_content_present",
    "important_links",
    "structured_data",
    "business_facts",
}
SCALAR_PARITY_FIELDS = {
    "title",
    "h1",
    "canonical",
    "indexability",
    "main_content_present",
    "business_facts",
}
SET_PARITY_FIELDS = {"important_links", "structured_data"}
RATINGS = {"good", "needs_improvement", "poor"}
SELECTION_REASONS = {"template_representative", "high_value_fill"}
LIGHTHOUSE_METRIC_KEYS = set(LIGHTHOUSE_AUDITS.values())


def _result(contract: str, reasons: list[str]) -> dict[str, Any]:
    return {
        "version": INTEGRITY_VERSION,
        "contract": contract,
        "valid": not reasons,
        "reasons": sorted(set(reasons)),
    }


def _number(value: Any, *, minimum: float | None = None, maximum: float | None = None) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    number = float(value)
    if not isfinite(number):
        return False
    if minimum is not None and number < minimum:
        return False
    if maximum is not None and number > maximum:
        return False
    return True


def _integer(value: Any, *, minimum: int = 0) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and bool(item) for item in value)


def validate_field_performance_contract(evidence: Any) -> dict[str, Any]:
    reasons: list[str] = []
    if not isinstance(evidence, dict):
        return _result("field_performance", ["evidence_not_object"])
    if evidence.get("version") != FIELD_PERFORMANCE_VERSION:
        reasons.append("version_mismatch")
    if evidence.get("evidence_kind") != "field":
        reasons.append("evidence_kind_mismatch")
    if not isinstance(evidence.get("provider"), str) or not evidence.get("provider"):
        reasons.append("provider_missing")
    state = evidence.get("state")
    if state not in PROVIDER_STATES:
        reasons.append("state_invalid")
    metrics = evidence.get("metrics")
    if state == "connected":
        if not isinstance(metrics, dict) or not metrics:
            reasons.append("connected_metrics_missing")
        else:
            for name, metric in metrics.items():
                if name not in FIELD_METRICS:
                    reasons.append("metric_key_unsupported")
                    continue
                if not isinstance(metric, dict):
                    reasons.append("metric_not_object")
                    continue
                if not _number(metric.get("value"), minimum=0):
                    reasons.append("metric_value_invalid")
                expected_unit = FIELD_METRICS[name][0]
                if metric.get("unit") != expected_unit:
                    reasons.append("metric_unit_mismatch")
                rating = metric.get("rating")
                if rating is not None and rating not in RATINGS:
                    reasons.append("metric_rating_invalid")
    elif metrics is not None:
        reasons.append("unavailable_state_retained_metrics")
    return _result("field_performance", reasons)


def validate_lighthouse_contract(evidence: Any) -> dict[str, Any]:
    reasons: list[str] = []
    if not isinstance(evidence, dict):
        return _result("lighthouse", ["evidence_not_object"])
    if evidence.get("version") != LIGHTHOUSE_EVIDENCE_VERSION:
        reasons.append("version_mismatch")
    if evidence.get("evidence_kind") != "lab":
        reasons.append("evidence_kind_mismatch")
    if not isinstance(evidence.get("provider"), str) or not evidence.get("provider"):
        reasons.append("provider_missing")
    state = evidence.get("state")
    if state not in PROVIDER_STATES:
        reasons.append("state_invalid")

    performance_score = evidence.get("performance_score")
    metrics = evidence.get("metrics")
    opportunities = evidence.get("opportunities")
    if not isinstance(opportunities, list):
        reasons.append("opportunities_not_list")
        opportunities = []

    if state != "connected":
        if performance_score is not None:
            reasons.append("unavailable_state_retained_score")
        if metrics is not None:
            reasons.append("unavailable_state_retained_metrics")
        if opportunities:
            reasons.append("unavailable_state_retained_opportunities")
        return _result("lighthouse", reasons)

    if performance_score is not None and not _number(performance_score, minimum=0, maximum=100):
        reasons.append("performance_score_invalid")
    if metrics is not None and not isinstance(metrics, dict):
        reasons.append("metrics_not_object")
        metrics = {}
    for name, metric in (metrics or {}).items():
        if name not in LIGHTHOUSE_METRIC_KEYS:
            reasons.append("metric_key_unsupported")
            continue
        if not isinstance(metric, dict):
            reasons.append("metric_not_object")
            continue
        if not _number(metric.get("value"), minimum=0):
            reasons.append("metric_value_invalid")
        if metric.get("score") is not None and not _number(metric.get("score"), minimum=0, maximum=1):
            reasons.append("metric_score_invalid")
        if metric.get("unit") is not None and not isinstance(metric.get("unit"), str):
            reasons.append("metric_unit_invalid")

    seen_audits: set[str] = set()
    if len(opportunities) > len(LIGHTHOUSE_OPPORTUNITIES):
        reasons.append("opportunities_exceed_allowlist")
    for row in opportunities:
        if not isinstance(row, dict):
            reasons.append("opportunity_not_object")
            continue
        audit_id = row.get("audit_id")
        if audit_id not in LIGHTHOUSE_OPPORTUNITIES:
            reasons.append("opportunity_unsupported")
        elif audit_id in seen_audits:
            reasons.append("opportunity_duplicate")
        else:
            seen_audits.add(audit_id)
        if row.get("score") is not None and not _number(row.get("score"), minimum=0, maximum=1):
            reasons.append("opportunity_score_invalid")
        for key in ("estimated_savings_ms", "estimated_savings_bytes"):
            if row.get(key) is not None and not _number(row.get(key), minimum=0):
                reasons.append("opportunity_savings_invalid")
        if all(row.get(key) is None for key in ("score", "estimated_savings_ms", "estimated_savings_bytes")):
            reasons.append("opportunity_measurement_missing")

    if performance_score is None and not metrics and not opportunities:
        reasons.append("connected_measurements_missing")
    return _result("lighthouse", reasons)


def validate_pagespeed_contract(evidence: Any) -> dict[str, Any]:
    reasons: list[str] = []
    if not isinstance(evidence, dict):
        return _result("pagespeed_insights", ["evidence_not_object"])
    if evidence.get("version") != PERFORMANCE_EVIDENCE_VERSION:
        reasons.append("version_mismatch")
    if evidence.get("provider") != "PageSpeed Insights":
        reasons.append("provider_mismatch")
    field_result = validate_field_performance_contract(evidence.get("field"))
    lab_result = validate_lighthouse_contract(evidence.get("lab"))
    if not field_result["valid"]:
        reasons.extend(f"field:{reason}" for reason in field_result["reasons"])
    if not lab_result["valid"]:
        reasons.extend(f"lab:{reason}" for reason in lab_result["reasons"])
    return _result("pagespeed_insights", reasons)


def validate_representative_sample_contract(sample: Any) -> dict[str, Any]:
    reasons: list[str] = []
    if not isinstance(sample, dict):
        return _result("representative_sample", ["sample_not_object"])
    if sample.get("version") != REPRESENTATIVE_SAMPLE_VERSION:
        reasons.append("version_mismatch")
    requested = sample.get("requested_max_pages")
    maximum = sample.get("max_pages")
    hard_cap = sample.get("hard_cap")
    if not _integer(requested):
        reasons.append("requested_max_pages_invalid")
    if hard_cap != MAX_PERFORMANCE_SAMPLE_PAGES:
        reasons.append("hard_cap_mismatch")
    if not _integer(maximum) or (isinstance(maximum, int) and maximum > MAX_PERFORMANCE_SAMPLE_PAGES):
        reasons.append("max_pages_invalid")
    if _integer(requested) and _integer(maximum) and maximum != min(requested, MAX_PERFORMANCE_SAMPLE_PAGES):
        reasons.append("max_pages_not_bounded_request")

    for key in (
        "eligible_page_observations",
        "duplicate_page_observations_dropped",
        "eligible_pages",
        "template_families",
        "selected_pages",
    ):
        if not _integer(sample.get(key)):
            reasons.append(f"{key}_invalid")

    observations = sample.get("eligible_page_observations")
    duplicates = sample.get("duplicate_page_observations_dropped")
    eligible = sample.get("eligible_pages")
    selected_count = sample.get("selected_pages")
    template_count = sample.get("template_families")
    if all(_integer(value) for value in (observations, duplicates, eligible)):
        if observations - eligible != duplicates:
            reasons.append("duplicate_count_inconsistent")
    if all(_integer(value) for value in (eligible, selected_count)) and selected_count > eligible:
        reasons.append("selected_exceeds_eligible")
    if all(_integer(value) for value in (maximum, selected_count)) and selected_count > maximum:
        reasons.append("selected_exceeds_max_pages")

    pages = sample.get("pages")
    if not isinstance(pages, list):
        reasons.append("pages_not_list")
        pages = []
    if _integer(selected_count) and selected_count != len(pages):
        reasons.append("selected_count_mismatch")

    urls: list[str] = []
    families: list[str] = []
    for row in pages:
        if not isinstance(row, dict):
            reasons.append("page_not_object")
            continue
        url = row.get("url")
        family = row.get("template_family")
        if not isinstance(url, str) or not url:
            reasons.append("page_url_missing")
        else:
            urls.append(url)
        if not isinstance(family, str) or not family:
            reasons.append("page_family_missing")
        else:
            families.append(family)
        if not _number(row.get("high_value_weight"), minimum=0):
            reasons.append("page_weight_invalid")
        if row.get("selection_reason") not in SELECTION_REASONS:
            reasons.append("selection_reason_invalid")
    if len(urls) != len(set(urls)):
        reasons.append("duplicate_selected_url")

    omitted = sample.get("omitted_template_families")
    if not _string_list(omitted):
        reasons.append("omitted_template_families_invalid")
        omitted = []
    elif len(omitted) != len(set(omitted)):
        reasons.append("omitted_template_families_duplicate")
    covered = set(families)
    if covered & set(omitted):
        reasons.append("covered_family_also_omitted")
    if _integer(template_count) and len(covered | set(omitted)) != template_count:
        reasons.append("template_family_count_inconsistent")
    coverage_complete = sample.get("template_coverage_complete")
    if not isinstance(coverage_complete, bool):
        reasons.append("template_coverage_complete_invalid")
    elif coverage_complete != (not omitted):
        reasons.append("template_coverage_flag_inconsistent")
    return _result("representative_sample", reasons)


def validate_critical_parity_contract(evidence: Any) -> dict[str, Any]:
    reasons: list[str] = []
    if not isinstance(evidence, dict):
        return _result("critical_parity", ["evidence_not_object"])
    if evidence.get("version") != CRITICAL_PARITY_VERSION:
        reasons.append("version_mismatch")
    state = evidence.get("state")
    if state not in PARITY_STATES:
        reasons.append("state_invalid")

    fields = evidence.get("fields")
    if not isinstance(fields, dict):
        reasons.append("fields_not_object")
        fields = {}
    unexpected = set(fields) - PARITY_FIELDS
    if unexpected:
        reasons.append("field_key_unsupported")

    for name, row in fields.items():
        if name not in PARITY_FIELDS:
            continue
        if not isinstance(row, dict):
            reasons.append("field_not_object")
            continue
        field_state = row.get("state")
        if field_state not in PARITY_FIELD_STATES:
            reasons.append("field_state_invalid")
        if name in SCALAR_PARITY_FIELDS:
            if not isinstance(row.get("raw_observed"), bool) or not isinstance(row.get("rendered_observed"), bool):
                reasons.append("scalar_observation_flags_invalid")
            elif field_state != "not_verified" and not (row["raw_observed"] and row["rendered_observed"]):
                reasons.append("scalar_state_without_bilateral_observation")
        elif name in SET_PARITY_FIELDS:
            for key in ("raw_count", "rendered_count"):
                value = row.get(key)
                if value is not None and not _integer(value):
                    reasons.append("set_count_invalid")
            for key in ("rendered_only", "raw_only"):
                if not isinstance(row.get(key), list) or any(not isinstance(item, str) for item in row.get(key, [])):
                    reasons.append("set_delta_invalid")

    verified = evidence.get("verified_fields")
    changed = evidence.get("changed_fields")
    if not _string_list(verified):
        reasons.append("verified_fields_invalid")
        verified = []
    if not _string_list(changed):
        reasons.append("changed_fields_invalid")
        changed = []
    if len(verified) != len(set(verified)):
        reasons.append("verified_fields_duplicate")
    if len(changed) != len(set(changed)):
        reasons.append("changed_fields_duplicate")

    expected_verified = sorted(
        name for name, row in fields.items()
        if name in PARITY_FIELDS and isinstance(row, dict) and row.get("state") in PARITY_FIELD_STATES - {"not_verified"}
    )
    expected_changed = sorted(
        name for name, row in fields.items()
        if name in PARITY_FIELDS and isinstance(row, dict)
        and row.get("state") in PARITY_FIELD_STATES - {"not_verified", "same"}
    )
    if sorted(verified) != expected_verified:
        reasons.append("verified_fields_inconsistent")
    if sorted(changed) != expected_changed:
        reasons.append("changed_fields_inconsistent")

    material_delta = evidence.get("material_delta")
    if state == "matched":
        if material_delta is not False:
            reasons.append("matched_material_delta_invalid")
        if not verified:
            reasons.append("matched_without_verified_fields")
        if changed:
            reasons.append("matched_with_changed_fields")
    elif state == "material_delta":
        if material_delta is not True:
            reasons.append("material_delta_flag_invalid")
        if not verified:
            reasons.append("material_delta_without_verified_fields")
        if not changed:
            reasons.append("material_delta_without_changed_fields")
    elif state == "not_verified":
        if material_delta is not None:
            reasons.append("not_verified_material_delta_invalid")
        if verified or changed:
            reasons.append("not_verified_with_verified_fields")

    if state in {"matched", "material_delta"}:
        url = evidence.get("url")
        rendered_url = evidence.get("rendered_url")
        if not isinstance(url, str) or not url or not isinstance(rendered_url, str) or not rendered_url:
            reasons.append("paired_identity_missing")
        elif url != rendered_url:
            reasons.append("paired_identity_mismatch")
    return _result("critical_parity", reasons)
