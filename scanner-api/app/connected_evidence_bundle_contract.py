"""Snapshot-bundle integrity for FixList NextGen connected evidence.

This lane-local pure contract composes after envelope, source, record, coverage,
source-scope, and logical-record-identity validation. It prevents one
scan/enrichment snapshot from silently carrying duplicate or contradictory
observations for the same provider/source scope. It performs no network I/O,
authentication, persistence, scoring, customer projection, release, deployment,
or production mutation.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse, urlunparse

from .connected_evidence_record_identity_contract import (
    validate_connected_evidence_record_identity_semantics,
)

SNAPSHOT_BUNDLE_VERSION = "connected_evidence_snapshot_bundle_v1"
SNAPSHOT_SOURCE_IDENTITY_VERSION = "connected_evidence_snapshot_source_identity_v1"
MAX_SNAPSHOT_ITEMS = 64

_UNAVAILABLE_STATES = frozenset(
    {"not_connected", "not_supported", "not_verified", "provider_error"}
)
_OBSERVED_STATES = frozenset({"verified", "stale"})


def _text(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _canonical_http_identity(value: Any, *, field: str) -> str:
    """Canonicalize an already-valid HTTP(S) source identity defensively."""

    text = _text(value, field=field)
    try:
        parsed = urlparse(text)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            raise ValueError
        if parsed.username is not None or parsed.password is not None or parsed.fragment:
            raise ValueError
        port = parsed.port
        host = parsed.hostname.encode("idna").decode("ascii").lower().rstrip(".")
    except (UnicodeError, ValueError):
        raise ValueError(f"{field} must be a canonicalizable absolute HTTP(S) URL") from None

    default_port = (parsed.scheme.lower() == "http" and port == 80) or (
        parsed.scheme.lower() == "https" and port == 443
    )
    rendered_host = f"[{host}]" if ":" in host else host
    netloc = rendered_host if port is None or default_port else f"{rendered_host}:{port}"
    return urlunparse(
        (
            parsed.scheme.lower(),
            netloc,
            parsed.path or "/",
            "",
            parsed.query,
            "",
        )
    )


def _canonical_gsc_property_identity(value: Any) -> str:
    text = _text(value, field="provenance.property_uri")
    prefix = "sc-domain:"
    if text.lower().startswith(prefix):
        domain = text[len(prefix) :].strip().rstrip(".")
        if not domain or any(token in domain for token in ("/", "?", "#", "@", ":")):
            raise ValueError("provenance.property_uri contained an invalid sc-domain property")
        try:
            canonical_domain = domain.encode("idna").decode("ascii").lower()
        except UnicodeError:
            raise ValueError("provenance.property_uri contained an invalid sc-domain property") from None
        return f"sc-domain:{canonical_domain}"
    return _canonical_http_identity(text, field="provenance.property_uri")


def _canonical_ga4_property_identity(value: Any) -> str:
    text = _text(value, field="provenance.property_id")
    numeric = text[len("properties/") :] if text.startswith("properties/") else text
    if not numeric.isdigit() or numeric.startswith("0"):
        raise ValueError("provenance.property_id was not a canonicalizable GA4 property identifier")
    return numeric


def _profile_source_scope_identity(evidence: Mapping[str, Any]) -> tuple[Any, ...]:
    provider = evidence["provider"]
    source_kind = evidence["source_kind"]
    provenance = evidence["provenance"]

    if (provider, source_kind) == ("google_search_console", "search_analytics"):
        return (
            provider,
            source_kind,
            _canonical_gsc_property_identity(provenance.get("property_uri")),
        )

    if (provider, source_kind) == ("google_search_console", "url_inspection"):
        return (
            provider,
            source_kind,
            _canonical_gsc_property_identity(provenance.get("property_uri")),
            _canonical_http_identity(
                provenance.get("inspection_url"), field="provenance.inspection_url"
            ),
        )

    if (provider, source_kind) == (
        "microsoft_bing_webmaster_tools",
        "ai_performance_export",
    ):
        return (
            provider,
            source_kind,
            _canonical_http_identity(provenance.get("site_url"), field="provenance.site_url"),
        )

    if (provider, source_kind) == ("google_analytics_4", "ai_assistant_referrals"):
        return (
            provider,
            source_kind,
            _canonical_ga4_property_identity(provenance.get("property_id")),
        )

    raise ValueError("unsupported connected-evidence provider/source_kind profile")


def _profile_snapshot_identity(evidence: Mapping[str, Any]) -> tuple[Any, ...]:
    """Return a deterministic identity for one already-validated snapshot.

    The identity deliberately excludes transport-only metadata such as import
    filenames so re-importing the same observation window under a different
    local filename cannot silently double-count it. Provider source identifiers
    are canonicalized so spelling/default-port aliases cannot evade duplicate
    detection.
    """

    provider = evidence["provider"]
    source_kind = evidence["source_kind"]
    state = evidence["state"]
    coverage = evidence["coverage"]
    source_scope = _profile_source_scope_identity(evidence)

    if (provider, source_kind) == ("google_search_console", "search_analytics"):
        if state in _UNAVAILABLE_STATES:
            return source_scope + ("unavailable",)
        dimensions = coverage.get("dimensions")
        if not isinstance(dimensions, list) or not dimensions:
            raise ValueError("coverage.dimensions must be a non-empty list")
        return source_scope + (
            tuple(dimensions),
            coverage.get("period_start"),
            coverage.get("period_end"),
            evidence.get("observed_at"),
        )

    if (provider, source_kind) == ("google_search_console", "url_inspection"):
        return source_scope

    if (provider, source_kind) == (
        "microsoft_bing_webmaster_tools",
        "ai_performance_export",
    ):
        if state in _UNAVAILABLE_STATES:
            return source_scope + ("unavailable",)
        return source_scope + (
            coverage.get("period_start"),
            coverage.get("period_end"),
            evidence.get("observed_at"),
        )

    if (provider, source_kind) == ("google_analytics_4", "ai_assistant_referrals"):
        if state in _UNAVAILABLE_STATES:
            return source_scope + ("unavailable",)
        return source_scope + (
            coverage.get("period_start"),
            coverage.get("period_end"),
            evidence.get("observed_at"),
        )

    raise ValueError("unsupported connected-evidence provider/source_kind profile")


def _state_class(state: Any) -> str:
    if state in _OBSERVED_STATES:
        return "observed"
    if state in _UNAVAILABLE_STATES:
        return "unavailable"
    raise ValueError("unsupported connected-evidence state")


def connected_evidence_source_scope_identity(evidence: Mapping[str, Any]) -> str:
    """Validate one envelope fully and return its canonical provider source scope."""

    validate_connected_evidence_record_identity_semantics(evidence)
    identity = _profile_source_scope_identity(evidence)
    return json.dumps(identity, separators=(",", ":"), ensure_ascii=False)


def connected_evidence_snapshot_identity(evidence: Mapping[str, Any]) -> str:
    """Validate one envelope fully and return a deterministic snapshot identity."""

    validate_connected_evidence_record_identity_semantics(evidence)
    identity = _profile_snapshot_identity(evidence)
    return json.dumps(identity, separators=(",", ":"), ensure_ascii=False)


def validate_connected_evidence_snapshot_bundle(
    evidence_items: Sequence[Mapping[str, Any]],
) -> Sequence[Mapping[str, Any]]:
    """Validate one bounded connected-evidence snapshot and return it unchanged.

    A bundle represents the optional connected evidence attached to one logical
    scan/enrichment snapshot, not historical time-series storage. Duplicate
    source/window identities fail closed instead of being silently summed or
    allowing caller order to choose which observation wins. A source scope also
    cannot be both observed and unavailable inside one logical snapshot.
    """

    if isinstance(evidence_items, (str, bytes, bytearray)) or not isinstance(
        evidence_items, Sequence
    ):
        raise ValueError("connected-evidence snapshot bundle must be a sequence")
    if len(evidence_items) > MAX_SNAPSHOT_ITEMS:
        raise ValueError("connected-evidence snapshot bundle exceeds item bound")

    seen: dict[str, int] = {}
    source_states: dict[str, tuple[str, int]] = {}
    for index, evidence in enumerate(evidence_items):
        if not isinstance(evidence, Mapping):
            raise ValueError(f"evidence_items[{index}] must be an object")
        validate_connected_evidence_record_identity_semantics(evidence)
        identity = json.dumps(
            _profile_snapshot_identity(evidence), separators=(",", ":"), ensure_ascii=False
        )
        previous = seen.get(identity)
        if previous is not None:
            raise ValueError(
                "duplicate connected-evidence snapshot identity at "
                f"evidence_items[{previous}] and evidence_items[{index}]"
            )
        seen[identity] = index

        source_scope = json.dumps(
            _profile_source_scope_identity(evidence),
            separators=(",", ":"),
            ensure_ascii=False,
        )
        state_class = _state_class(evidence["state"])
        previous_state = source_states.get(source_scope)
        if previous_state is not None and previous_state[0] != state_class:
            raise ValueError(
                "contradictory connected-evidence availability states for one source scope at "
                f"evidence_items[{previous_state[1]}] and evidence_items[{index}]"
            )
        source_states[source_scope] = (state_class, index)

    return evidence_items
