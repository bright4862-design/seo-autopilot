"""Fail-closed site-origin binding for representative Lane-C samples.

This module is pure and performs no network or browser work. It does not grant an
execution budget. It only proves that already-selected representative page identities
belong to one caller-supplied authoritative HTTP(S) origin.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

REPRESENTATIVE_SAMPLE_VERSION = "nextgen_performance_sample_v1"
SAMPLE_ORIGIN_BINDING_VERSION = "nextgen_performance_sample_origin_binding_v1"
SAMPLE_ORIGIN_BINDING_INTEGRITY_VERSION = (
    "nextgen_performance_sample_origin_binding_integrity_v1"
)

_BINDING_FIELDS = (
    "version",
    "contract",
    "valid",
    "reasons",
    "site_origin",
    "selected_pages_checked",
    "selected_same_origin_pages",
    "foreign_origins",
)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _http_origin(value: Any) -> tuple[str | None, str | None]:
    """Return a canonical HTTP(S) origin or a stable rejection reason."""
    raw = _text(value)
    if not raw:
        return None, "identity_missing"
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except (TypeError, ValueError):
        return None, "identity_malformed"

    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.hostname:
        return None, "identity_not_absolute_http"
    if parsed.username is not None or parsed.password is not None:
        return None, "identity_contains_credentials"

    host = parsed.hostname.rstrip(".").lower()
    if not host:
        return None, "identity_not_absolute_http"

    default_port = 80 if scheme == "http" else 443
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = host if port in {None, default_port} else f"{host}:{port}"
    return urlunsplit((scheme, netloc, "", "", "")), None


def _binding_result(
    *,
    valid: bool,
    reasons: list[str],
    site_origin: str | None,
    selected_pages_checked: int = 0,
    selected_same_origin_pages: int = 0,
    foreign_origins: set[str] | None = None,
) -> dict[str, Any]:
    return {
        "version": SAMPLE_ORIGIN_BINDING_VERSION,
        "contract": REPRESENTATIVE_SAMPLE_VERSION,
        "valid": valid,
        "reasons": sorted(set(reasons)),
        "site_origin": site_origin,
        "selected_pages_checked": selected_pages_checked,
        "selected_same_origin_pages": selected_same_origin_pages,
        "foreign_origins": sorted(foreign_origins or set()),
    }


def bind_representative_sample_to_site_origin(
    sample: Any,
    *,
    site_url: Any,
) -> dict[str, Any]:
    """Bind selected sample identities to one authoritative site origin.

    The caller must first validate the deterministic representative-sample binding
    against the authoritative retained-page population. A valid result here proves
    same-origin identity only; it is not permission to execute browser/provider work.
    """
    site_origin, site_reason = _http_origin(site_url)
    if site_origin is None:
        return _binding_result(
            valid=False,
            reasons=[f"site_{site_reason or 'identity_invalid'}"],
            site_origin=None,
        )

    if not isinstance(sample, dict):
        return _binding_result(
            valid=False,
            reasons=["sample_not_object"],
            site_origin=site_origin,
        )
    if sample.get("version") != REPRESENTATIVE_SAMPLE_VERSION:
        return _binding_result(
            valid=False,
            reasons=["sample_version_mismatch"],
            site_origin=site_origin,
        )

    rows = sample.get("pages")
    if not isinstance(rows, list):
        return _binding_result(
            valid=False,
            reasons=["sample_pages_not_list"],
            site_origin=site_origin,
        )

    reasons: list[str] = []
    foreign_origins: set[str] = set()
    same_origin = 0
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            reasons.append(f"selected_row_{index}_not_object")
            continue
        selected_origin, selected_reason = _http_origin(row.get("url"))
        if selected_origin is None:
            reasons.append(
                f"selected_row_{index}_{selected_reason or 'identity_invalid'}"
            )
            continue
        if selected_origin != site_origin:
            reasons.append("selected_origin_mismatch")
            foreign_origins.add(selected_origin)
            continue
        same_origin += 1

    return _binding_result(
        valid=not reasons,
        reasons=reasons,
        site_origin=site_origin,
        selected_pages_checked=len(rows),
        selected_same_origin_pages=same_origin,
        foreign_origins=foreign_origins,
    )


def validate_representative_sample_origin_contract(
    sample: Any,
    *,
    site_url: Any,
    artifact: Any,
) -> dict[str, Any]:
    """Recompute and bind a transported origin artifact fail-closed.

    A faithfully transported *invalid* origin binding is itself integrity-valid. The
    returned ``expected_binding_valid`` reports whether the source binding was valid.
    """
    expected = bind_representative_sample_to_site_origin(sample, site_url=site_url)
    reasons: list[str] = []
    if not isinstance(artifact, dict):
        reasons.append("artifact_not_object")
    else:
        for field in _BINDING_FIELDS:
            if artifact.get(field) != expected.get(field):
                reasons.append(f"{field}_mismatch")

    return {
        "version": SAMPLE_ORIGIN_BINDING_INTEGRITY_VERSION,
        "contract": SAMPLE_ORIGIN_BINDING_VERSION,
        "valid": not reasons,
        "reasons": sorted(set(reasons)),
        "expected_binding_valid": expected["valid"],
    }
