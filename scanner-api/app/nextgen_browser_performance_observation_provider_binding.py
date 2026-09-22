"""Bind sampled Lane-C performance observations to validated provider evidence.

This module is pure. It performs no provider/network/browser work, creates no
credentials, grants no execution budget, and does not write persistence, authority,
repair priority or customer state. It closes a transport gap between the existing
sample/source-binding helpers and the provider-specific CrUX/PSI/Lighthouse bound
contracts: a field or lab component is trusted only when an already-valid bound
provider envelope for the same sampled request contains the exact component.

Field (CrUX) and lab (Lighthouse) evidence remain separate. A Lighthouse binding can
never satisfy a field component and a CrUX binding can never satisfy a lab component.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.nextgen_browser_performance_contract import (
    validate_field_performance_contract,
    validate_lighthouse_contract,
    validate_representative_sample_contract,
)
from app.nextgen_browser_performance_crux_provenance import validate_bound_crux_contract
from app.nextgen_browser_performance_lighthouse_provenance import (
    validate_bound_lighthouse_contract,
)
from app.nextgen_browser_performance_psi_integrity import validate_bound_pagespeed_contract

OBSERVATION_PROVIDER_BINDING_VERSION = (
    "nextgen_performance_observation_provider_binding_v1"
)
_PROVIDER_KINDS = {"crux", "psi", "lighthouse"}
_FIELD_COMPONENT_FIELDS = (
    "version",
    "evidence_kind",
    "provider",
    "state",
    "reason",
    "scope",
    "observed_at",
    "source_url",
    "metrics",
)
_LAB_COMPONENT_FIELDS = (
    "version",
    "evidence_kind",
    "provider",
    "state",
    "reason",
    "observed_at",
    "source_url",
    "performance_score",
    "metrics",
    "opportunities",
)


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
        or not parsed.hostname
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


def _origin(identity: str | None) -> str | None:
    normalized = _http_identity(identity) if identity is not None else None
    if normalized is None:
        return None
    parsed = urlsplit(normalized)
    return urlunsplit((parsed.scheme, parsed.netloc, "/", "", ""))


def _projection(value: Any, fields: tuple[str, ...]) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {field: value.get(field) for field in fields}


def _component_matches(actual: Any, expected: Any, fields: tuple[str, ...]) -> bool:
    actual_projection = _projection(actual, fields)
    expected_projection = _projection(expected, fields)
    return actual_projection is not None and actual_projection == expected_projection


def _provider_contract(kind: str, evidence: Any) -> dict[str, Any]:
    if kind == "crux":
        return validate_bound_crux_contract(evidence)
    if kind == "psi":
        return validate_bound_pagespeed_contract(evidence)
    if kind == "lighthouse":
        return validate_bound_lighthouse_contract(evidence)
    return {"valid": False, "reasons": ["provider_kind_unsupported"]}


def _binding_identity_matches(kind: str, evidence: Any, requested_url: str) -> bool:
    if not isinstance(evidence, dict):
        return False
    provenance = evidence.get("provenance")
    if not isinstance(provenance, dict):
        return False

    if kind == "psi":
        return _http_identity(provenance.get("requested_url")) == requested_url

    if kind == "lighthouse":
        return _http_identity(provenance.get("requested_url")) == requested_url

    if kind == "crux":
        scope = evidence.get("scope") or provenance.get("record_scope")
        source = _http_identity(evidence.get("source_url"))
        if evidence.get("state") != "connected":
            source = _http_identity(provenance.get("requested_source_url")) or source
            scope = provenance.get("requested_scope") or scope
        if scope == "url":
            return source == requested_url
        if scope == "origin":
            source_origin = _origin(source)
            return source_origin is not None and source_origin == _origin(requested_url)
        return False

    return False


def _provider_components(kind: str, evidence: Any) -> dict[str, Any]:
    if not isinstance(evidence, dict):
        return {}
    if kind == "crux":
        return {"field": evidence}
    if kind == "lighthouse":
        return {"lab": evidence}
    if kind == "psi":
        return {
            "field": evidence.get("field"),
            "lab": evidence.get("lab"),
        }
    return {}


def _result(
    *,
    selected_pages: int | None,
    checked_observations: int | None,
    bound_observations: int | None,
    bound_field_components: int | None,
    bound_lab_components: int | None,
    observation_errors: list[dict[str, Any]],
    reasons: list[str] | None = None,
) -> dict[str, Any]:
    aggregate_reasons = sorted(set(reasons or []))
    if observation_errors:
        aggregate_reasons.append("performance_observation_provider_binding_invalid")
    aggregate_reasons = sorted(set(aggregate_reasons))
    return {
        "version": OBSERVATION_PROVIDER_BINDING_VERSION,
        "valid": not aggregate_reasons,
        "selected_pages": selected_pages,
        "checked_observations": checked_observations,
        "bound_observations": bound_observations,
        "bound_field_components": bound_field_components,
        "bound_lab_components": bound_lab_components,
        "reasons": aggregate_reasons,
        "observation_errors": observation_errors,
    }


def validate_performance_observation_provider_binding(
    sample: Any,
    observations: Any,
) -> dict[str, Any]:
    """Prove each transported field/lab component comes from bound provider evidence.

    Each observation must identify one selected ``requested_url`` and include one or
    both ``field``/``lab`` components plus ``provider_bindings``. A provider binding is
    ``{"kind": "crux"|"psi"|"lighthouse", "evidence": <bound envelope>}``.

    The provider-specific bound contract must validate, its requested identity must
    belong to the sampled request, and the exact base field/lab component must match.
    Extra provider provenance metadata is not copied into the comparison. Empty
    ``observations`` is valid: coverage accounting decides whether pages are unassessed.
    """
    sample_contract = validate_representative_sample_contract(sample)
    if not sample_contract.get("valid"):
        return _result(
            selected_pages=None,
            checked_observations=None,
            bound_observations=None,
            bound_field_components=None,
            bound_lab_components=None,
            observation_errors=[],
            reasons=["sample_contract_invalid"],
        )

    pages = sample.get("pages") if isinstance(sample, dict) else None
    if not isinstance(pages, list):
        return _result(
            selected_pages=None,
            checked_observations=None,
            bound_observations=None,
            bound_field_components=None,
            bound_lab_components=None,
            observation_errors=[],
            reasons=["sample_pages_invalid"],
        )

    selected_urls: list[str] = []
    for row in pages:
        identity = _http_identity(row.get("url") if isinstance(row, dict) else None)
        if identity is None:
            return _result(
                selected_pages=None,
                checked_observations=None,
                bound_observations=None,
                bound_field_components=None,
                bound_lab_components=None,
                observation_errors=[],
                reasons=["sample_page_identity_invalid"],
            )
        selected_urls.append(identity)
    if len(selected_urls) != len(set(selected_urls)):
        return _result(
            selected_pages=None,
            checked_observations=None,
            bound_observations=None,
            bound_field_components=None,
            bound_lab_components=None,
            observation_errors=[],
            reasons=["sample_selected_identity_duplicate"],
        )

    if not isinstance(observations, list):
        return _result(
            selected_pages=len(selected_urls),
            checked_observations=None,
            bound_observations=None,
            bound_field_components=None,
            bound_lab_components=None,
            observation_errors=[],
            reasons=["observations_not_list"],
        )

    selected_set = set(selected_urls)
    seen: set[str] = set()
    errors: list[dict[str, Any]] = []
    bound_observations = 0
    bound_field_components = 0
    bound_lab_components = 0

    for index, observation in enumerate(observations):
        reasons: list[str] = []
        if not isinstance(observation, dict):
            errors.append({
                "index": index,
                "requested_url": None,
                "reasons": ["observation_not_object"],
            })
            continue

        requested_url = _http_identity(observation.get("requested_url"))
        if requested_url is None:
            errors.append({
                "index": index,
                "requested_url": None,
                "reasons": ["requested_identity_invalid"],
            })
            continue
        if requested_url not in selected_set:
            errors.append({
                "index": index,
                "requested_url": requested_url,
                "reasons": ["requested_identity_not_selected"],
            })
            continue
        if requested_url in seen:
            errors.append({
                "index": index,
                "requested_url": requested_url,
                "reasons": ["requested_identity_duplicate"],
            })
            continue
        seen.add(requested_url)

        field = observation.get("field") if "field" in observation else None
        lab = observation.get("lab") if "lab" in observation else None
        has_field = field is not None
        has_lab = lab is not None
        if not has_field and not has_lab:
            reasons.append("observation_without_components")

        if has_field:
            field_contract = validate_field_performance_contract(field)
            if not field_contract.get("valid"):
                reasons.extend(
                    f"field:{reason}" for reason in field_contract.get("reasons", [])
                )
        if has_lab:
            lab_contract = validate_lighthouse_contract(lab)
            if not lab_contract.get("valid"):
                reasons.extend(
                    f"lab:{reason}" for reason in lab_contract.get("reasons", [])
                )

        raw_bindings = observation.get("provider_bindings")
        if not isinstance(raw_bindings, list) or not raw_bindings:
            reasons.append("provider_bindings_missing")
            raw_bindings = []

        candidates: dict[str, list[tuple[int, Any]]] = {"field": [], "lab": []}
        binding_validity: dict[int, bool] = {}
        used_bindings: set[int] = set()
        seen_kinds: set[str] = set()

        for binding_index, binding in enumerate(raw_bindings):
            if not isinstance(binding, dict):
                reasons.append(f"provider_binding_{binding_index}:not_object")
                binding_validity[binding_index] = False
                continue
            kind = binding.get("kind")
            if kind not in _PROVIDER_KINDS:
                reasons.append(f"provider_binding_{binding_index}:kind_unsupported")
                binding_validity[binding_index] = False
                continue
            if kind in seen_kinds:
                reasons.append(f"provider_binding_{binding_index}:kind_duplicate")
                binding_validity[binding_index] = False
                continue
            seen_kinds.add(kind)

            evidence = binding.get("evidence")
            provider_contract = _provider_contract(kind, evidence)
            if not provider_contract.get("valid"):
                for reason in provider_contract.get("reasons", []):
                    reasons.append(
                        f"provider_binding_{binding_index}:{kind}:{reason}"
                    )
                binding_validity[binding_index] = False
                continue
            if not _binding_identity_matches(kind, evidence, requested_url):
                reasons.append(
                    f"provider_binding_{binding_index}:{kind}:requested_identity_mismatch"
                )
                binding_validity[binding_index] = False
                continue

            binding_validity[binding_index] = True
            for component_name, component in _provider_components(kind, evidence).items():
                if component is not None:
                    candidates[component_name].append((binding_index, component))

        field_matched = False
        if has_field:
            capable = candidates["field"]
            for binding_index, expected in capable:
                if _component_matches(field, expected, _FIELD_COMPONENT_FIELDS):
                    field_matched = True
                    used_bindings.add(binding_index)
                    break
            if not capable:
                reasons.append("field_provider_binding_missing")
            elif not field_matched:
                reasons.append("field_component_provider_mismatch")

        lab_matched = False
        if has_lab:
            capable = candidates["lab"]
            for binding_index, expected in capable:
                if _component_matches(lab, expected, _LAB_COMPONENT_FIELDS):
                    lab_matched = True
                    used_bindings.add(binding_index)
                    break
            if not capable:
                reasons.append("lab_provider_binding_missing")
            elif not lab_matched:
                reasons.append("lab_component_provider_mismatch")

        for binding_index, is_valid in binding_validity.items():
            if is_valid and binding_index not in used_bindings:
                reasons.append(f"provider_binding_{binding_index}:unused")

        if reasons:
            errors.append({
                "index": index,
                "requested_url": requested_url,
                "reasons": sorted(set(reasons)),
            })
            continue

        bound_observations += 1
        if field_matched:
            bound_field_components += 1
        if lab_matched:
            bound_lab_components += 1

    return _result(
        selected_pages=len(selected_urls),
        checked_observations=len(observations),
        bound_observations=bound_observations,
        bound_field_components=bound_field_components,
        bound_lab_components=bound_lab_components,
        observation_errors=errors,
    )
