"""Fail-closed integrity checks for Lane-A adaptive crawl telemetry.

This module is intentionally pure and shadow-only.  It does not perform network
work and does not authorize crawl budgets.  It validates that an adaptive
tranche-yield envelope is self-consistent before delegating to the existing
Lane-A continuation policy.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from .adaptive_crawl import (
    ADAPTIVE_CRAWL_VERSION,
    ADAPTIVE_TELEMETRY_VERSION,
    DEFAULT_TRANCHE_TARGETS,
    continuation_decision,
)

ADAPTIVE_TELEMETRY_INTEGRITY_VERSION = "adaptive_tranche_integrity_v1"

_DELTA_FIELDS = (
    "new_route_signatures",
    "new_template_keys",
    "new_graph_edges",
    "new_finding_fingerprints",
    "new_high_impact_findings",
    "new_high_value_families",
)


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _finite_nonnegative_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return number


def validate_tranche_telemetry(telemetry: Mapping[str, Any] | Any) -> dict[str, Any]:
    """Validate a telemetry envelope without inferring missing evidence.

    The builder in ``adaptive_crawl`` emits cumulative evidence.  A future
    integrator may persist/transport that envelope before asking whether another
    tranche should run.  This validator protects that boundary from malformed or
    caller-tampered counts/rates.  It does not change continuation thresholds.
    """
    if not isinstance(telemetry, Mapping):
        return {
            "version": ADAPTIVE_TELEMETRY_INTEGRITY_VERSION,
            "valid": False,
            "reason": "telemetry_not_mapping",
        }
    if telemetry.get("version") != ADAPTIVE_TELEMETRY_VERSION:
        return {
            "version": ADAPTIVE_TELEMETRY_INTEGRITY_VERSION,
            "valid": False,
            "reason": "telemetry_version_mismatch",
        }

    previous_assessed = _nonnegative_int(telemetry.get("previous_assessed_count"))
    assessed = _nonnegative_int(telemetry.get("assessed_count"))
    discovered = _nonnegative_int(telemetry.get("discovered_urls"))
    pages_added = _nonnegative_int(telemetry.get("pages_added"))
    if None in (previous_assessed, assessed, discovered, pages_added):
        return {
            "version": ADAPTIVE_TELEMETRY_INTEGRITY_VERSION,
            "valid": False,
            "reason": "invalid_count_type",
        }
    assert previous_assessed is not None
    assert assessed is not None
    assert discovered is not None
    assert pages_added is not None
    if not (previous_assessed <= assessed <= discovered):
        return {
            "version": ADAPTIVE_TELEMETRY_INTEGRITY_VERSION,
            "valid": False,
            "reason": "invalid_count_relationship",
        }
    if pages_added != assessed - previous_assessed:
        return {
            "version": ADAPTIVE_TELEMETRY_INTEGRITY_VERSION,
            "valid": False,
            "reason": "pages_added_mismatch",
        }
    if telemetry.get("counts_valid") is not True:
        return {
            "version": ADAPTIVE_TELEMETRY_INTEGRITY_VERSION,
            "valid": False,
            "reason": "counts_not_verified",
        }
    if telemetry.get("evidence_monotonic") is not True:
        return {
            "version": ADAPTIVE_TELEMETRY_INTEGRITY_VERSION,
            "valid": False,
            "reason": "evidence_not_monotonic",
        }

    regressed = telemetry.get("regressed_signal_keys")
    if regressed not in ((), []):
        return {
            "version": ADAPTIVE_TELEMETRY_INTEGRITY_VERSION,
            "valid": False,
            "reason": "regressed_signal_keys_present",
        }

    signal_state = telemetry.get("signal_state")
    if signal_state not in {"observed", "insufficient_evidence"}:
        return {
            "version": ADAPTIVE_TELEMETRY_INTEGRITY_VERSION,
            "valid": False,
            "reason": "unsupported_signal_state",
        }
    if signal_state == "observed" and pages_added <= 0:
        return {
            "version": ADAPTIVE_TELEMETRY_INTEGRITY_VERSION,
            "valid": False,
            "reason": "observed_without_pages_added",
        }

    for delta_field in _DELTA_FIELDS:
        delta = telemetry.get(delta_field)
        rate_field = f"{delta_field}_per_100"
        rate = telemetry.get(rate_field)
        if delta is None:
            if rate is not None:
                return {
                    "version": ADAPTIVE_TELEMETRY_INTEGRITY_VERSION,
                    "valid": False,
                    "reason": f"rate_without_delta:{rate_field}",
                }
            if signal_state == "observed":
                return {
                    "version": ADAPTIVE_TELEMETRY_INTEGRITY_VERSION,
                    "valid": False,
                    "reason": f"observed_missing_delta:{delta_field}",
                }
            continue

        normalized_delta = _nonnegative_int(delta)
        if normalized_delta is None:
            return {
                "version": ADAPTIVE_TELEMETRY_INTEGRITY_VERSION,
                "valid": False,
                "reason": f"invalid_delta:{delta_field}",
            }
        if pages_added <= 0:
            if rate is not None:
                return {
                    "version": ADAPTIVE_TELEMETRY_INTEGRITY_VERSION,
                    "valid": False,
                    "reason": f"rate_without_pages_added:{rate_field}",
                }
            continue

        normalized_rate = _finite_nonnegative_number(rate)
        if normalized_rate is None:
            return {
                "version": ADAPTIVE_TELEMETRY_INTEGRITY_VERSION,
                "valid": False,
                "reason": f"invalid_rate:{rate_field}",
            }
        expected_rate = round(normalized_delta * 100.0 / pages_added, 4)
        if abs(normalized_rate - expected_rate) > 1e-9:
            return {
                "version": ADAPTIVE_TELEMETRY_INTEGRITY_VERSION,
                "valid": False,
                "reason": f"rate_mismatch:{rate_field}",
            }

    return {
        "version": ADAPTIVE_TELEMETRY_INTEGRITY_VERSION,
        "valid": True,
        "reason": "telemetry_integrity_verified",
    }


def verified_continuation_decision(
    telemetry: Mapping[str, Any] | Any,
    *,
    tranche_targets: Sequence[int] = DEFAULT_TRANCHE_TARGETS,
) -> dict[str, Any]:
    """Fail closed on invalid telemetry, otherwise preserve Lane-A policy exactly."""
    integrity = validate_tranche_telemetry(telemetry)
    if integrity["valid"] is not True:
        return {
            "version": ADAPTIVE_CRAWL_VERSION,
            "decision": "insufficient_evidence",
            "next_target": None,
            "reason": f"telemetry_integrity_failed:{integrity['reason']}",
            "site_fully_understood": False,
            "integrity_version": ADAPTIVE_TELEMETRY_INTEGRITY_VERSION,
        }
    decision = continuation_decision(telemetry, tranche_targets=tranche_targets)
    return {
        **decision,
        "integrity_version": ADAPTIVE_TELEMETRY_INTEGRITY_VERSION,
    }
