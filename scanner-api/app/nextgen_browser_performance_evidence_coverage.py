"""Pure coverage accounting for Lane-C field/lab performance evidence.

The helper binds already-produced provider-neutral field/lab evidence to a
representative performance sample. It performs no provider calls, browser work,
persistence, scoring, or execution-budget decisions. Field (CrUX) and lab
(Lighthouse) evidence remain separate throughout the aggregate.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.nextgen_browser_performance_contract import (
    validate_field_performance_contract,
    validate_lighthouse_contract,
    validate_representative_sample_contract,
)

PERFORMANCE_EVIDENCE_COVERAGE_VERSION = "nextgen_performance_evidence_coverage_v1"
REPRESENTATIVE_SAMPLE_VERSION = "nextgen_performance_sample_v1"
PROVIDER_STATES = ("connected", "disconnected", "unavailable", "rate_limited", "provider_error")


def _http_identity(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        parsed = urlsplit(raw)
    except Exception:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    return urlunsplit((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        parsed.path,
        parsed.query,
        "",
    ))


def _component_blank() -> dict[str, Any]:
    return {
        "coverage_state": "not_verified",
        "attempted_pages": None,
        "connected_pages": None,
        "unassessed_pages": None,
        "attempted_ratio": None,
        "connected_ratio": None,
        "state_counts": {state: None for state in PROVIDER_STATES},
        "connected_urls": [],
        "non_connected_urls": [],
        "unassessed_urls": [],
    }


def _blank(reason: str, *, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "version": PERFORMANCE_EVIDENCE_COVERAGE_VERSION,
        "state": "not_verified",
        "reason": reason,
        "selected_pages": None,
        "selected_urls": [],
        "field": _component_blank(),
        "lab": _component_blank(),
        "details": details or {},
    }


def _component_summary(
    selected_urls: list[str],
    by_url: dict[str, dict[str, Any]],
    component: str,
) -> dict[str, Any]:
    attempted_urls: list[str] = []
    connected_urls: list[str] = []
    non_connected_urls: list[str] = []
    unassessed_urls: list[str] = []
    state_counts = {state: 0 for state in PROVIDER_STATES}

    for url in selected_urls:
        observation = by_url.get(url)
        evidence = observation.get(component) if isinstance(observation, dict) else None
        if evidence is None:
            unassessed_urls.append(url)
            continue
        attempted_urls.append(url)
        state = evidence["state"]
        state_counts[state] += 1
        if state == "connected":
            connected_urls.append(url)
        else:
            non_connected_urls.append(url)

    selected_count = len(selected_urls)
    if selected_count == 0:
        coverage_state = "not_applicable"
        attempted_ratio = None
        connected_ratio = None
    else:
        attempted_ratio = len(attempted_urls) / selected_count
        connected_ratio = len(connected_urls) / selected_count
        if not attempted_urls:
            coverage_state = "unassessed"
        elif len(attempted_urls) == selected_count:
            coverage_state = "complete"
        else:
            coverage_state = "partial"

    return {
        "coverage_state": coverage_state,
        "attempted_pages": len(attempted_urls),
        "connected_pages": len(connected_urls),
        "unassessed_pages": len(unassessed_urls),
        "attempted_ratio": attempted_ratio,
        "connected_ratio": connected_ratio,
        "state_counts": state_counts,
        "connected_urls": connected_urls,
        "non_connected_urls": non_connected_urls,
        "unassessed_urls": unassessed_urls,
    }


def summarize_performance_evidence_coverage(sample: Any, observations: Any) -> dict[str, Any]:
    """Bind field/lab observations to the selected page population.

    Each observation must identify the sampled request via ``requested_url`` and may
    carry a ``field`` component, a ``lab`` component, or both. Missing components are
    unassessed, while explicit non-connected provider states are attempted but not
    measured. Malformed/foreign/duplicate observations fail the aggregate closed.
    """
    sample_contract = validate_representative_sample_contract(sample)
    if not sample_contract.get("valid"):
        return _blank(
            "sample_contract_invalid",
            details={"sample_reasons": sample_contract.get("reasons", [])},
        )
    if not isinstance(sample, dict) or sample.get("version") != REPRESENTATIVE_SAMPLE_VERSION:
        return _blank("sample_version_mismatch")

    pages = sample.get("pages")
    selected_urls: list[str] = []
    for row in pages:
        identity = _http_identity(row.get("url") if isinstance(row, dict) else None)
        if identity is None:
            return _blank("sample_page_identity_invalid")
        selected_urls.append(identity)
    if len(selected_urls) != len(set(selected_urls)):
        return _blank("sample_selected_identity_duplicate")

    if not isinstance(observations, list):
        return _blank("observations_not_list")

    selected_set = set(selected_urls)
    by_url: dict[str, dict[str, Any]] = {}
    foreign_urls: list[str] = []
    duplicate_urls: list[str] = []
    malformed: list[dict[str, Any]] = []

    for index, observation in enumerate(observations):
        if not isinstance(observation, dict):
            malformed.append({"index": index, "reasons": ["observation_not_object"]})
            continue
        identity = _http_identity(observation.get("requested_url"))
        if identity is None:
            malformed.append({"index": index, "reasons": ["requested_identity_invalid"]})
            continue
        if identity not in selected_set:
            foreign_urls.append(identity)
            continue
        if identity in by_url:
            duplicate_urls.append(identity)
            continue

        has_field = "field" in observation and observation.get("field") is not None
        has_lab = "lab" in observation and observation.get("lab") is not None
        if not has_field and not has_lab:
            malformed.append({"index": index, "reasons": ["observation_without_components"]})
            continue

        component_reasons: list[str] = []
        if has_field:
            field_result = validate_field_performance_contract(observation.get("field"))
            if not field_result.get("valid"):
                component_reasons.extend(
                    f"field:{reason}" for reason in field_result.get("reasons", [])
                )
        if has_lab:
            lab_result = validate_lighthouse_contract(observation.get("lab"))
            if not lab_result.get("valid"):
                component_reasons.extend(
                    f"lab:{reason}" for reason in lab_result.get("reasons", [])
                )
        if component_reasons:
            malformed.append({"index": index, "reasons": sorted(set(component_reasons))})
            continue

        by_url[identity] = observation

    if malformed or foreign_urls or duplicate_urls:
        return _blank(
            "performance_observation_binding_invalid",
            details={
                "malformed_observations": malformed,
                "foreign_requested_urls": sorted(set(foreign_urls)),
                "duplicate_requested_urls": sorted(set(duplicate_urls)),
            },
        )

    field = _component_summary(selected_urls, by_url, "field")
    lab = _component_summary(selected_urls, by_url, "lab")
    return {
        "version": PERFORMANCE_EVIDENCE_COVERAGE_VERSION,
        "state": "not_applicable" if not selected_urls else "available",
        "reason": "no_selected_pages" if not selected_urls else "field_lab_coverage_accounted",
        "selected_pages": len(selected_urls),
        "selected_urls": selected_urls,
        "field": field,
        "lab": lab,
        "details": {},
    }
