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

from .connected_evidence_record_identity_contract import (
    validate_connected_evidence_record_identity_semantics,
)

SNAPSHOT_BUNDLE_VERSION = "connected_evidence_snapshot_bundle_v1"
MAX_SNAPSHOT_ITEMS = 64

_UNAVAILABLE_STATES = frozenset(
    {"not_connected", "not_supported", "not_verified", "provider_error"}
)


def _text(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _profile_snapshot_identity(evidence: Mapping[str, Any]) -> tuple[Any, ...]:
    """Return a deterministic identity for one already-validated snapshot.

    The identity deliberately excludes transport-only metadata such as import
    filenames so re-importing the same observation window under a different
    local filename cannot silently double-count it.
    """

    provider = evidence["provider"]
    source_kind = evidence["source_kind"]
    state = evidence["state"]
    provenance = evidence["provenance"]
    coverage = evidence["coverage"]

    if (provider, source_kind) == ("google_search_console", "search_analytics"):
        property_uri = _text(provenance.get("property_uri"), field="provenance.property_uri")
        if state in _UNAVAILABLE_STATES:
            return (provider, source_kind, property_uri, "unavailable")
        dimensions = coverage.get("dimensions")
        if not isinstance(dimensions, list) or not dimensions:
            raise ValueError("coverage.dimensions must be a non-empty list")
        return (
            provider,
            source_kind,
            property_uri,
            tuple(dimensions),
            coverage.get("period_start"),
            coverage.get("period_end"),
            evidence.get("observed_at"),
        )

    if (provider, source_kind) == ("google_search_console", "url_inspection"):
        return (
            provider,
            source_kind,
            _text(provenance.get("property_uri"), field="provenance.property_uri"),
            _text(provenance.get("inspection_url"), field="provenance.inspection_url"),
        )

    if (provider, source_kind) == (
        "microsoft_bing_webmaster_tools",
        "ai_performance_export",
    ):
        site_url = _text(provenance.get("site_url"), field="provenance.site_url")
        if state in _UNAVAILABLE_STATES:
            return (provider, source_kind, site_url, "unavailable")
        return (
            provider,
            source_kind,
            site_url,
            coverage.get("period_start"),
            coverage.get("period_end"),
            evidence.get("observed_at"),
        )

    if (provider, source_kind) == ("google_analytics_4", "ai_assistant_referrals"):
        property_id = _text(provenance.get("property_id"), field="provenance.property_id")
        if state in _UNAVAILABLE_STATES:
            return (provider, source_kind, property_id, "unavailable")
        return (
            provider,
            source_kind,
            property_id,
            coverage.get("period_start"),
            coverage.get("period_end"),
            evidence.get("observed_at"),
        )

    raise ValueError("unsupported connected-evidence provider/source_kind profile")


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
    allowing caller order to choose which observation wins.
    """

    if isinstance(evidence_items, (str, bytes, bytearray)) or not isinstance(
        evidence_items, Sequence
    ):
        raise ValueError("connected-evidence snapshot bundle must be a sequence")
    if len(evidence_items) > MAX_SNAPSHOT_ITEMS:
        raise ValueError("connected-evidence snapshot bundle exceeds item bound")

    seen: dict[str, int] = {}
    for index, evidence in enumerate(evidence_items):
        if not isinstance(evidence, Mapping):
            raise ValueError(f"evidence_items[{index}] must be an object")
        identity = connected_evidence_snapshot_identity(evidence)
        previous = seen.get(identity)
        if previous is not None:
            raise ValueError(
                "duplicate connected-evidence snapshot identity at "
                f"evidence_items[{previous}] and evidence_items[{index}]"
            )
        seen[identity] = index

    return evidence_items
