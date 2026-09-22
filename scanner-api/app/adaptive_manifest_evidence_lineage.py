"""Cross-bind manifest-backed adaptive benchmark and marginal telemetry evidence.

This module is pure and shadow-only. It joins the two existing replay-manifest
binding artifacts into one deterministic lineage certificate so later Lane-A
experiment decisions cannot accidentally combine valid evidence from different
discovery populations. It performs no network I/O, persistence, crawl expansion,
or production authorization.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

ADAPTIVE_MANIFEST_MARGINAL_BINDING_VERSION = "adaptive_manifest_marginal_binding_v1"
ADAPTIVE_MANIFEST_BENCHMARK_BINDING_VERSION = "adaptive_manifest_benchmark_binding_v1"
ADAPTIVE_MANIFEST_EVIDENCE_LINEAGE_VERSION = "adaptive_manifest_evidence_lineage_v1"
ADAPTIVE_MANIFEST_EVIDENCE_LINEAGE_INTEGRITY_VERSION = (
    "adaptive_manifest_evidence_lineage_integrity_v1"
)
STANDARD_TARGET = 150
SMART_TARGET = 500
BLIND_TARGET = 1000
CHECKPOINTS = (STANDARD_TARGET, SMART_TARGET, BLIND_TARGET)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _fail(reason: str) -> dict[str, Any]:
    return {
        "version": ADAPTIVE_MANIFEST_EVIDENCE_LINEAGE_VERSION,
        "valid": False,
        "reason": reason,
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _sha256(value: Any) -> str | None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        return None
    return value


def _sequence(value: Any) -> Sequence[Any] | None:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        return None
    return value


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return tuple(
            (str(key), _canonical(item))
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        )
    if isinstance(value, (list, tuple)):
        return tuple(_canonical(item) for item in value)
    return value


def _checkpoint_rows(value: Any) -> tuple[dict[int, Mapping[str, Any]] | None, str | None]:
    rows = _sequence(value)
    if rows is None or len(rows) != len(CHECKPOINTS):
        return None, "marginal_binding_checkpoint_count_invalid"
    by_checkpoint: dict[int, Mapping[str, Any]] = {}
    for raw in rows:
        if not isinstance(raw, Mapping):
            return None, "marginal_binding_checkpoint_invalid"
        checkpoint = raw.get("checkpoint")
        if checkpoint not in CHECKPOINTS or checkpoint in by_checkpoint:
            return None, "marginal_binding_checkpoint_identity_invalid"
        pages = _nonnegative_int(raw.get("pages_assessed"))
        target = _nonnegative_int(raw.get("manifest_target"))
        fingerprint = _sha256(raw.get("population_fingerprint"))
        if pages is None or target is None or fingerprint is None:
            return None, f"marginal_binding_checkpoint_{checkpoint}_shape_invalid"
        if raw.get("inventory_limited") is not (pages < checkpoint):
            return None, f"marginal_binding_checkpoint_{checkpoint}_inventory_state_invalid"
        by_checkpoint[checkpoint] = raw
    if tuple(sorted(by_checkpoint)) != CHECKPOINTS:
        return None, "marginal_binding_checkpoint_set_invalid"
    return by_checkpoint, None


def _forbidden_authority_claim(source: Mapping[str, Any]) -> bool:
    return (
        source.get("population_scope_complete") is not False
        or source.get("production_budget_authorized") is not False
        or source.get("site_fully_understood") is not False
    )


def _lineage_fingerprint(identity: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        identity,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_manifest_evidence_lineage(
    marginal_binding: Mapping[str, Any] | Any,
    benchmark_binding: Mapping[str, Any] | Any,
) -> dict[str, Any]:
    """Return one fail-closed lineage certificate for manifest-bound Lane-A evidence.

    Both inputs must already be valid products of the dedicated manifest-binding
    helpers. This join independently checks their shared identity/count invariants
    and checkpoint geometry before emitting a deterministic certificate. It does not
    make an adaptive crawl decision and cannot authorize a larger production budget.
    """
    if not isinstance(marginal_binding, Mapping):
        return _fail("marginal_binding_not_mapping")
    if marginal_binding.get("version") != ADAPTIVE_MANIFEST_MARGINAL_BINDING_VERSION:
        return _fail("marginal_binding_version_mismatch")
    if marginal_binding.get("valid") is not True:
        return _fail("marginal_binding_invalid")
    if _forbidden_authority_claim(marginal_binding):
        return _fail("marginal_binding_forbidden_authority_claim")
    if marginal_binding.get("standard_150_preserved") is not True:
        return _fail("marginal_binding_standard_150_not_preserved")

    if not isinstance(benchmark_binding, Mapping):
        return _fail("benchmark_binding_not_mapping")
    if benchmark_binding.get("version") != ADAPTIVE_MANIFEST_BENCHMARK_BINDING_VERSION:
        return _fail("benchmark_binding_version_mismatch")
    if benchmark_binding.get("valid") is not True:
        return _fail("benchmark_binding_invalid")
    if _forbidden_authority_claim(benchmark_binding):
        return _fail("benchmark_binding_forbidden_authority_claim")
    if benchmark_binding.get("standard_150_preserved") is not True:
        return _fail("benchmark_binding_standard_150_not_preserved")

    candidate_count = _nonnegative_int(marginal_binding.get("candidate_count"))
    benchmark_unique = _nonnegative_int(benchmark_binding.get("candidate_urls_unique"))
    benchmark_supplied = _nonnegative_int(benchmark_binding.get("candidate_urls_supplied"))
    duplicates = _nonnegative_int(benchmark_binding.get("duplicate_candidate_identities_removed"))
    if (
        candidate_count is None
        or benchmark_unique is None
        or benchmark_supplied is None
        or duplicates is None
        or benchmark_supplied - benchmark_unique != duplicates
    ):
        return _fail("candidate_counts_invalid")
    if candidate_count != benchmark_unique:
        return _fail("candidate_population_count_mismatch")

    marginal_input_fp = _sha256(marginal_binding.get("input_population_fingerprint"))
    benchmark_input_fp = _sha256(benchmark_binding.get("manifest_input_population_fingerprint"))
    if marginal_input_fp is None or benchmark_input_fp is None:
        return _fail("input_population_fingerprint_invalid")
    if marginal_input_fp != benchmark_input_fp:
        return _fail("input_population_fingerprint_mismatch")

    marginal_binding_fp = _sha256(marginal_binding.get("binding_fingerprint"))
    benchmark_binding_fp = _sha256(benchmark_binding.get("binding_fingerprint"))
    benchmark_smart_fp = _sha256(benchmark_binding.get("smart_population_sha256"))
    benchmark_blind_fp = _sha256(benchmark_binding.get("blind_population_sha256"))
    if None in (
        marginal_binding_fp,
        benchmark_binding_fp,
        benchmark_smart_fp,
        benchmark_blind_fp,
    ):
        return _fail("binding_or_population_fingerprint_invalid")

    selection_targets = _sequence(marginal_binding.get("selection_targets"))
    if selection_targets is None:
        return _fail("selection_targets_invalid")
    normalized_targets: list[int] = []
    for target in selection_targets:
        parsed = _nonnegative_int(target)
        if parsed is None or parsed <= 0:
            return _fail("selection_targets_invalid")
        normalized_targets.append(parsed)
    if tuple(normalized_targets) != tuple(sorted(set(normalized_targets))):
        return _fail("selection_targets_not_strictly_increasing")
    if normalized_targets and normalized_targets[-1] > BLIND_TARGET:
        return _fail("selection_target_exceeds_lane_ceiling")

    checkpoints, reason = _checkpoint_rows(marginal_binding.get("bindings"))
    if reason:
        return _fail(reason)
    assert checkpoints is not None

    expected_pages = {
        STANDARD_TARGET: min(STANDARD_TARGET, candidate_count),
        SMART_TARGET: min(SMART_TARGET, candidate_count),
        BLIND_TARGET: min(BLIND_TARGET, candidate_count),
    }
    expected_manifest_targets = {
        checkpoint: checkpoint if candidate_count >= checkpoint else candidate_count
        for checkpoint in CHECKPOINTS
    }
    for checkpoint in CHECKPOINTS:
        row = checkpoints[checkpoint]
        if row.get("pages_assessed") != expected_pages[checkpoint]:
            return _fail(f"marginal_binding_checkpoint_{checkpoint}_page_count_mismatch")
        if row.get("manifest_target") != expected_manifest_targets[checkpoint]:
            return _fail(f"marginal_binding_checkpoint_{checkpoint}_manifest_target_mismatch")

    smart_pages = _nonnegative_int(benchmark_binding.get("smart_pages"))
    blind_pages = _nonnegative_int(benchmark_binding.get("blind_pages"))
    manifest_smart_target = _nonnegative_int(benchmark_binding.get("manifest_smart_target"))
    standard_manifest_target = _nonnegative_int(benchmark_binding.get("standard_manifest_target"))
    if None in (smart_pages, blind_pages, manifest_smart_target, standard_manifest_target):
        return _fail("benchmark_population_geometry_invalid")
    if smart_pages != expected_pages[SMART_TARGET]:
        return _fail("benchmark_smart_500_page_count_mismatch")
    if blind_pages != expected_pages[BLIND_TARGET]:
        return _fail("benchmark_blind_1000_page_count_mismatch")
    if manifest_smart_target != expected_manifest_targets[SMART_TARGET]:
        return _fail("benchmark_manifest_smart_target_mismatch")
    if standard_manifest_target != expected_manifest_targets[STANDARD_TARGET]:
        return _fail("benchmark_standard_manifest_target_mismatch")
    if checkpoints[SMART_TARGET].get("pages_assessed") != smart_pages:
        return _fail("smart_500_cross_binding_page_count_mismatch")

    identity = {
        "candidate_count": candidate_count,
        "candidate_urls_supplied": benchmark_supplied,
        "duplicate_candidate_identities_removed": duplicates,
        "input_population_fingerprint": marginal_input_fp,
        "selection_targets": tuple(normalized_targets),
        "standard_150_pages": expected_pages[STANDARD_TARGET],
        "smart_500_pages": smart_pages,
        "blind_1000_pages": blind_pages,
        "marginal_population_fingerprints": tuple(
            (checkpoint, checkpoints[checkpoint]["population_fingerprint"])
            for checkpoint in CHECKPOINTS
        ),
        "benchmark_smart_population_sha256": benchmark_smart_fp,
        "benchmark_blind_population_sha256": benchmark_blind_fp,
        "marginal_binding_fingerprint": marginal_binding_fp,
        "benchmark_binding_fingerprint": benchmark_binding_fp,
    }
    return {
        "version": ADAPTIVE_MANIFEST_EVIDENCE_LINEAGE_VERSION,
        "valid": True,
        "reason": "manifest_bound_evidence_lineage_reconciled",
        **identity,
        "comparison_state": "full_blind_1000_reference" if candidate_count >= BLIND_TARGET else "inventory_limited",
        "lineage_fingerprint": _lineage_fingerprint(identity),
        "standard_150_preserved": True,
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }


def validate_manifest_evidence_lineage(
    artifact: Mapping[str, Any] | Any,
    marginal_binding: Mapping[str, Any] | Any,
    benchmark_binding: Mapping[str, Any] | Any,
) -> dict[str, Any]:
    """Rebuild the certificate and reject any transported lineage drift."""
    expected = build_manifest_evidence_lineage(marginal_binding, benchmark_binding)
    if expected.get("valid") is not True:
        return {
            "version": ADAPTIVE_MANIFEST_EVIDENCE_LINEAGE_INTEGRITY_VERSION,
            "valid": False,
            "reason": f"source:{expected.get('reason') or 'invalid'}",
            "production_budget_authorized": False,
            "site_fully_understood": False,
        }
    if not isinstance(artifact, Mapping):
        return {
            "version": ADAPTIVE_MANIFEST_EVIDENCE_LINEAGE_INTEGRITY_VERSION,
            "valid": False,
            "reason": "artifact_not_mapping",
            "production_budget_authorized": False,
            "site_fully_understood": False,
        }
    if _canonical(artifact) != _canonical(expected):
        return {
            "version": ADAPTIVE_MANIFEST_EVIDENCE_LINEAGE_INTEGRITY_VERSION,
            "valid": False,
            "reason": "artifact_mismatch",
            "production_budget_authorized": False,
            "site_fully_understood": False,
        }
    return {
        "version": ADAPTIVE_MANIFEST_EVIDENCE_LINEAGE_INTEGRITY_VERSION,
        "valid": True,
        "reason": "ok",
        "lineage_fingerprint": expected["lineage_fingerprint"],
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }
