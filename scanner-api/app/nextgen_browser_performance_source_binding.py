"""Strict source/provenance binding for Lane-C performance observations.

This module is pure: it performs no network I/O, creates no credentials and does
not authorize browser/Lighthouse executions. It validates that connected field
(CrUX) and lab (Lighthouse) evidence actually belongs to the sampled request
identity before aggregate coverage can be trusted.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.nextgen_browser_performance_contract import (
    validate_field_performance_contract,
    validate_lighthouse_contract,
    validate_representative_sample_contract,
)

SOURCE_BINDING_VERSION = "nextgen_performance_observation_source_binding_v1"
PSI_PROVENANCE_VERSION = "nextgen_pagespeed_provenance_v1"


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
        parsed.path or "/",
        parsed.query,
        "",
    ))


def _origin(identity: str | None) -> str | None:
    if identity is None:
        return None
    parsed = urlsplit(identity)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), "/", "", ""))


def _valid_provenance(
    observation: dict[str, Any],
    *,
    requested_url: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    if "provenance" not in observation or observation.get("provenance") is None:
        return None, []
    provenance = observation.get("provenance")
    if not isinstance(provenance, dict):
        return None, ["provenance_not_object"]
    reasons: list[str] = []
    if provenance.get("version") != PSI_PROVENANCE_VERSION:
        reasons.append("provenance_version_mismatch")

    identities: dict[str, str | None] = {}
    for key in (
        "requested_url",
        "response_final_url",
        "field_source_url",
        "field_initial_url",
        "lighthouse_requested_url",
        "lighthouse_final_url",
    ):
        value = provenance.get(key)
        if value is None:
            identities[key] = None
            continue
        normalized = _http_identity(value)
        identities[key] = normalized
        if normalized is None:
            reasons.append(f"provenance_{key}_invalid")

    provenance_requested = identities.get("requested_url")
    if provenance_requested is not None and provenance_requested != requested_url:
        reasons.append("provenance_requested_identity_mismatch")

    fallback = provenance.get("field_origin_fallback")
    if fallback is not None and not isinstance(fallback, bool):
        reasons.append("provenance_field_origin_fallback_invalid")

    strategy = provenance.get("strategy")
    if strategy is not None and strategy not in {"mobile", "desktop"}:
        reasons.append("provenance_strategy_invalid")

    normalized = dict(provenance)
    normalized.update(identities)
    return normalized, reasons


def _field_binding_reasons(
    requested_url: str,
    evidence: dict[str, Any],
    provenance: dict[str, Any] | None,
) -> list[str]:
    if evidence.get("state") != "connected":
        return []
    reasons: list[str] = []
    scope = evidence.get("scope")
    if scope not in {"url", "origin"}:
        reasons.append("field_connected_scope_invalid")

    source_url = _http_identity(evidence.get("source_url"))
    if source_url is None:
        return reasons + ["field_connected_source_identity_missing_or_invalid"]

    if scope == "origin":
        source_origin = _origin(source_url)
        if source_url != source_origin:
            reasons.append("field_origin_scope_source_not_origin")
        if source_origin == _origin(requested_url):
            return reasons
        if not provenance:
            return reasons + ["field_source_identity_mismatch"]
        if (
            provenance.get("field_initial_url") != requested_url
            or provenance.get("field_source_url") != source_url
        ):
            reasons.append("field_source_identity_mismatch")
        return reasons

    if scope == "url":
        if source_url == requested_url:
            return reasons
        if not provenance:
            return reasons + ["field_source_identity_mismatch"]
        if (
            provenance.get("field_initial_url") != requested_url
            or provenance.get("field_source_url") != source_url
        ):
            reasons.append("field_source_identity_mismatch")
    return reasons


def _lab_binding_reasons(
    requested_url: str,
    evidence: dict[str, Any],
    provenance: dict[str, Any] | None,
) -> list[str]:
    if evidence.get("state") != "connected":
        return []
    source_url = _http_identity(evidence.get("source_url"))
    if source_url is None:
        return ["lab_connected_source_identity_missing_or_invalid"]
    if source_url == requested_url:
        return []
    if not provenance:
        return ["lab_source_identity_mismatch"]
    if (
        provenance.get("lighthouse_requested_url") != requested_url
        or provenance.get("lighthouse_final_url") != source_url
    ):
        return ["lab_source_identity_mismatch"]
    return []


def validate_performance_observation_source_binding(sample: Any, observations: Any) -> dict[str, Any]:
    """Fail closed when connected evidence cannot be bound to sampled requests.

    Redirected final identities are accepted only when explicit PSI provenance
    proves the requested->final relationship. Origin-scoped field evidence is
    accepted directly only for the sampled request's own origin.
    """
    sample_contract = validate_representative_sample_contract(sample)
    if not sample_contract.get("valid"):
        return {
            "version": SOURCE_BINDING_VERSION,
            "valid": False,
            "selected_pages": None,
            "bound_observations": None,
            "reasons": ["sample_contract_invalid"],
            "observation_errors": [],
            "details": {"sample_reasons": sample_contract.get("reasons", [])},
        }

    pages = sample.get("pages") if isinstance(sample, dict) else None
    selected_urls: list[str] = []
    if not isinstance(pages, list):
        return {
            "version": SOURCE_BINDING_VERSION,
            "valid": False,
            "selected_pages": None,
            "bound_observations": None,
            "reasons": ["sample_pages_invalid"],
            "observation_errors": [],
            "details": {},
        }
    for row in pages:
        identity = _http_identity(row.get("url") if isinstance(row, dict) else None)
        if identity is None:
            return {
                "version": SOURCE_BINDING_VERSION,
                "valid": False,
                "selected_pages": None,
                "bound_observations": None,
                "reasons": ["sample_page_identity_invalid"],
                "observation_errors": [],
                "details": {},
            }
        selected_urls.append(identity)
    if len(selected_urls) != len(set(selected_urls)):
        return {
            "version": SOURCE_BINDING_VERSION,
            "valid": False,
            "selected_pages": None,
            "bound_observations": None,
            "reasons": ["sample_selected_identity_duplicate"],
            "observation_errors": [],
            "details": {},
        }
    if not isinstance(observations, list):
        return {
            "version": SOURCE_BINDING_VERSION,
            "valid": False,
            "selected_pages": len(selected_urls),
            "bound_observations": None,
            "reasons": ["observations_not_list"],
            "observation_errors": [],
            "details": {},
        }

    selected_set = set(selected_urls)
    seen: set[str] = set()
    errors: list[dict[str, Any]] = []
    bound = 0

    for index, observation in enumerate(observations):
        reasons: list[str] = []
        if not isinstance(observation, dict):
            errors.append({"index": index, "requested_url": None, "reasons": ["observation_not_object"]})
            continue

        requested_url = _http_identity(observation.get("requested_url"))
        if requested_url is None:
            errors.append({"index": index, "requested_url": None, "reasons": ["requested_identity_invalid"]})
            continue
        if requested_url not in selected_set:
            errors.append({"index": index, "requested_url": requested_url, "reasons": ["requested_identity_not_selected"]})
            continue
        if requested_url in seen:
            errors.append({"index": index, "requested_url": requested_url, "reasons": ["requested_identity_duplicate"]})
            continue
        seen.add(requested_url)

        has_field = "field" in observation and observation.get("field") is not None
        has_lab = "lab" in observation and observation.get("lab") is not None
        if not has_field and not has_lab:
            reasons.append("observation_without_components")

        provenance, provenance_reasons = _valid_provenance(
            observation,
            requested_url=requested_url,
        )
        reasons.extend(provenance_reasons)

        if has_field:
            field = observation.get("field")
            field_contract = validate_field_performance_contract(field)
            if not field_contract.get("valid"):
                reasons.extend(f"field:{reason}" for reason in field_contract.get("reasons", []))
            elif isinstance(field, dict):
                reasons.extend(_field_binding_reasons(requested_url, field, provenance))

        if has_lab:
            lab = observation.get("lab")
            lab_contract = validate_lighthouse_contract(lab)
            if not lab_contract.get("valid"):
                reasons.extend(f"lab:{reason}" for reason in lab_contract.get("reasons", []))
            elif isinstance(lab, dict):
                reasons.extend(_lab_binding_reasons(requested_url, lab, provenance))

        if reasons:
            errors.append({
                "index": index,
                "requested_url": requested_url,
                "reasons": sorted(set(reasons)),
            })
        else:
            bound += 1

    return {
        "version": SOURCE_BINDING_VERSION,
        "valid": not errors,
        "selected_pages": len(selected_urls),
        "bound_observations": bound,
        "reasons": [] if not errors else ["performance_observation_source_binding_invalid"],
        "observation_errors": errors,
        "details": {},
    }
