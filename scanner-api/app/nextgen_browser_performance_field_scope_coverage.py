"""Scope-aware coverage accounting for provider-bound Lane-C field evidence.

This helper is additive and pure. It performs no provider/browser/network work,
creates no credentials, grants no execution budget, and does not write authority,
persistence, repair priority, customer scoring, or projection state.

Its purpose is narrow: connected CrUX field evidence can be URL-scoped or
origin-scoped. Origin-level evidence is useful context for sampled pages, but it must
not be counted as page-level field coverage. URL-scoped evidence whose provider subject
redirected away from the sampled request is likewise kept distinct from exact page-level
coverage. Lab/Lighthouse evidence is ignored by this field-only aggregate.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.nextgen_browser_performance_contract import validate_representative_sample_contract
from app.nextgen_browser_performance_observation_provider_binding import (
    validate_performance_observation_provider_binding,
)

FIELD_SCOPE_COVERAGE_VERSION = "nextgen_field_scope_coverage_v1"
FIELD_SCOPE_COVERAGE_INTEGRITY_VERSION = "nextgen_field_scope_coverage_integrity_v1"
_PROVIDER_STATES = {"connected", "disconnected", "unavailable", "rate_limited", "provider_error"}


def _http_identity(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except (TypeError, ValueError):
        return None
    scheme = parsed.scheme.lower()
    if (
        scheme not in {"http", "https"}
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    host = parsed.hostname.rstrip(".").lower()
    if not host:
        return None
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    default_port = 80 if scheme == "http" else 443
    netloc = host if port in {None, default_port} else f"{host}:{port}"
    return urlunsplit((scheme, netloc, parsed.path or "/", parsed.query, ""))


def _origin(value: Any) -> str | None:
    identity = _http_identity(value)
    if identity is None:
        return None
    parsed = urlsplit(identity)
    return urlunsplit((parsed.scheme, parsed.netloc, "/", "", ""))


def _field_blank() -> dict[str, Any]:
    return {
        "attempted_pages": None,
        "connected_observations": None,
        "non_connected_pages": None,
        "unassessed_pages": None,
        "url_scoped_exact_pages": None,
        "url_scoped_redirected_pages": None,
        "origin_scoped_selected_pages": None,
        "unique_origin_sources": None,
        "page_level_connected_pages": None,
        "page_level_connected_ratio": None,
        "connected_observation_ratio": None,
        "state_counts": {state: None for state in sorted(_PROVIDER_STATES)},
        "page_level_connected_urls": [],
        "redirected_url_scoped_requests": [],
        "origin_scoped_requests": [],
        "origin_groups": [],
        "non_connected_urls": [],
        "unassessed_urls": [],
    }


def _blank(reason: str, *, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "version": FIELD_SCOPE_COVERAGE_VERSION,
        "state": "not_verified",
        "reason": reason,
        "selected_pages": None,
        "selected_urls": [],
        "field": _field_blank(),
        "details": details or {},
    }


def summarize_field_scope_coverage(sample: Any, observations: Any) -> dict[str, Any]:
    """Account connected field evidence without inflating origin data to page coverage."""
    sample_contract = validate_representative_sample_contract(sample)
    if not sample_contract.get("valid"):
        return _blank(
            "sample_contract_invalid",
            details={"sample_reasons": sample_contract.get("reasons", [])},
        )

    provider_binding = validate_performance_observation_provider_binding(sample, observations)
    if not provider_binding.get("valid"):
        return _blank(
            "performance_observation_provider_binding_invalid",
            details={
                "binding_reasons": provider_binding.get("reasons", []),
                "observation_errors": provider_binding.get("observation_errors", []),
            },
        )

    pages = sample.get("pages") if isinstance(sample, dict) else None
    if not isinstance(pages, list):
        return _blank("sample_pages_invalid")
    if not isinstance(observations, list):
        return _blank("observations_not_list")

    selected_urls: list[str] = []
    for row in pages:
        identity = _http_identity(row.get("url") if isinstance(row, dict) else None)
        if identity is None:
            return _blank("sample_page_identity_invalid")
        selected_urls.append(identity)
    if len(selected_urls) != len(set(selected_urls)):
        return _blank("sample_selected_identity_duplicate")

    by_requested: dict[str, dict[str, Any]] = {}
    for observation in observations:
        if not isinstance(observation, dict):
            return _blank("observation_not_object")
        requested = _http_identity(observation.get("requested_url"))
        if requested is None:
            return _blank("requested_identity_invalid")
        if requested in by_requested:
            return _blank("requested_identity_duplicate")
        by_requested[requested] = observation

    attempted_urls: list[str] = []
    connected_urls: list[str] = []
    non_connected_urls: list[str] = []
    unassessed_urls: list[str] = []
    exact_urls: list[str] = []
    redirected_rows: list[dict[str, str]] = []
    origin_rows: list[dict[str, str]] = []
    origin_members: dict[str, list[str]] = {}
    state_counts = {state: 0 for state in sorted(_PROVIDER_STATES)}

    for requested in selected_urls:
        observation = by_requested.get(requested)
        field = observation.get("field") if isinstance(observation, dict) else None
        if field is None:
            unassessed_urls.append(requested)
            continue
        if not isinstance(field, dict):
            return _blank("field_component_invalid")

        attempted_urls.append(requested)
        state = field.get("state")
        if state not in _PROVIDER_STATES:
            return _blank("field_state_invalid")
        state_counts[state] += 1
        if state != "connected":
            non_connected_urls.append(requested)
            continue

        connected_urls.append(requested)
        scope = field.get("scope")
        source = _http_identity(field.get("source_url"))
        if source is None:
            return _blank(
                "connected_field_source_identity_invalid",
                details={"requested_url": requested},
            )

        if scope == "url":
            if source == requested:
                exact_urls.append(requested)
            else:
                redirected_rows.append({
                    "requested_url": requested,
                    "field_source_url": source,
                })
            continue

        if scope == "origin":
            source_origin = _origin(source)
            requested_origin = _origin(requested)
            if source_origin is None or requested_origin != source_origin:
                return _blank(
                    "connected_origin_scope_identity_mismatch",
                    details={
                        "requested_url": requested,
                        "field_source_url": source,
                    },
                )
            origin_rows.append({
                "requested_url": requested,
                "field_source_origin": source_origin,
            })
            origin_members.setdefault(source_origin, []).append(requested)
            continue

        return _blank(
            "connected_field_scope_invalid",
            details={"requested_url": requested, "scope": scope},
        )

    selected_count = len(selected_urls)
    connected_count = len(connected_urls)
    origin_groups = [
        {"origin": origin, "requested_urls": sorted(urls)}
        for origin, urls in sorted(origin_members.items())
    ]

    return {
        "version": FIELD_SCOPE_COVERAGE_VERSION,
        "state": "not_applicable" if selected_count == 0 else "available",
        "reason": "no_selected_pages" if selected_count == 0 else "field_scope_coverage_accounted",
        "selected_pages": selected_count,
        "selected_urls": selected_urls,
        "field": {
            "attempted_pages": len(attempted_urls),
            "connected_observations": connected_count,
            "non_connected_pages": len(non_connected_urls),
            "unassessed_pages": len(unassessed_urls),
            "url_scoped_exact_pages": len(exact_urls),
            "url_scoped_redirected_pages": len(redirected_rows),
            "origin_scoped_selected_pages": len(origin_rows),
            "unique_origin_sources": len(origin_groups),
            "page_level_connected_pages": len(exact_urls),
            "page_level_connected_ratio": (
                len(exact_urls) / selected_count if selected_count else None
            ),
            "connected_observation_ratio": (
                connected_count / selected_count if selected_count else None
            ),
            "state_counts": state_counts,
            "page_level_connected_urls": exact_urls,
            "redirected_url_scoped_requests": redirected_rows,
            "origin_scoped_requests": origin_rows,
            "origin_groups": origin_groups,
            "non_connected_urls": non_connected_urls,
            "unassessed_urls": unassessed_urls,
        },
        "details": {},
    }


def validate_field_scope_coverage_contract(
    sample: Any,
    observations: Any,
    evidence: Any,
) -> dict[str, Any]:
    """Recompute scope coverage from authoritative inputs and reject transported drift."""
    reasons: list[str] = []
    if not isinstance(evidence, dict):
        return {
            "version": FIELD_SCOPE_COVERAGE_INTEGRITY_VERSION,
            "valid": False,
            "reasons": ["evidence_not_object"],
        }
    if evidence.get("version") != FIELD_SCOPE_COVERAGE_VERSION:
        reasons.append("version_mismatch")

    expected = summarize_field_scope_coverage(sample, observations)
    if evidence != expected:
        reasons.append("field_scope_coverage_mismatch")

    return {
        "version": FIELD_SCOPE_COVERAGE_INTEGRITY_VERSION,
        "valid": not reasons,
        "reasons": sorted(set(reasons)),
    }
