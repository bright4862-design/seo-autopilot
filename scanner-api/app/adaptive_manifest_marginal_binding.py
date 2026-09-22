"""Bind marginal-yield telemetry to exact adaptive tranche selections.

This module is pure and shadow-only. It does not crawl, persist, change budgets, or
make production decisions. It proves that transported 150/500/1000 Smart marginal
telemetry refers to the exact page populations selected by a replay-validated tranche
manifest, including inventory-limited terminal populations.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from .adaptive_marginal_benchmark import MARGINAL_CHECKPOINTS
from .adaptive_marginal_integrity import validate_marginal_population_integrity
from .adaptive_tranche_manifest import (
    ADAPTIVE_TRANCHE_MANIFEST_INTEGRITY_VERSION,
    ADAPTIVE_TRANCHE_MANIFEST_VERSION,
)

ADAPTIVE_MANIFEST_MARGINAL_BINDING_VERSION = "adaptive_manifest_marginal_binding_v1"
ADAPTIVE_MANIFEST_MARGINAL_BINDING_INTEGRITY_VERSION = (
    "adaptive_manifest_marginal_binding_integrity_v1"
)


def _fail(reason: str) -> dict[str, Any]:
    return {
        "version": ADAPTIVE_MANIFEST_MARGINAL_BINDING_VERSION,
        "valid": False,
        "reason": reason,
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }


def _marginal_population_fingerprint(urls: Sequence[str]) -> str:
    """Reproduce the published marginal-benchmark ordered-population fingerprint."""
    digest = hashlib.sha256()
    digest.update(b"adaptive_marginal_population_v1\0")
    for url in urls:
        if not isinstance(url, str) or not url or url != url.strip():
            raise ValueError("invalid_manifest_url_identity")
        digest.update(url.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _binding_fingerprint(bindings: Sequence[Mapping[str, Any]]) -> str:
    payload = [
        {
            "checkpoint": item["checkpoint"],
            "manifest_target": item["manifest_target"],
            "pages_assessed": item["pages_assessed"],
            "population_fingerprint": item["population_fingerprint"],
        }
        for item in bindings
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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


def build_manifest_bound_marginal_telemetry(
    manifest: Mapping[str, Any] | Any,
    marginal: Mapping[str, Any] | Any,
    *,
    manifest_integrity: Mapping[str, Any] | Any,
) -> dict[str, Any]:
    """Bind Smart marginal checkpoints to an exact replay-validated manifest.

    ``manifest_integrity`` must be the result of replaying
    ``validate_adaptive_tranche_selection_manifest`` against the original discovery
    sequence, selector callbacks, and metadata. This helper then prevents marginal
    telemetry from being transplanted onto a different Smart population with the same
    page counts.
    """
    if not isinstance(manifest, Mapping):
        return _fail("manifest_not_mapping")
    if manifest.get("version") != ADAPTIVE_TRANCHE_MANIFEST_VERSION:
        return _fail("manifest_version_mismatch")
    if not isinstance(manifest_integrity, Mapping):
        return _fail("manifest_integrity_not_mapping")
    if manifest_integrity.get("version") != ADAPTIVE_TRANCHE_MANIFEST_INTEGRITY_VERSION:
        return _fail("manifest_integrity_version_mismatch")
    if manifest_integrity.get("valid") is not True:
        return _fail("manifest_integrity_invalid")

    for key in (
        "input_population_fingerprint",
        "selection_targets",
        "standard_reference_population_fingerprint",
    ):
        if _canonical(manifest_integrity.get(key)) != _canonical(manifest.get(key)):
            return _fail(f"manifest_integrity_{key}_mismatch")

    if (
        manifest.get("population_scope_complete") is not False
        or manifest.get("production_budget_authorized") is not False
        or manifest.get("site_fully_understood") is not False
    ):
        return _fail("manifest_forbidden_authority_claim")

    marginal_integrity = validate_marginal_population_integrity(marginal)
    if marginal_integrity.get("valid") is not True:
        return _fail(f"marginal_integrity:{marginal_integrity.get('reason') or 'invalid'}")
    if not isinstance(marginal, Mapping):
        return _fail("marginal_not_mapping")

    candidate_count = marginal.get("candidate_count")
    unique_discovered_count = manifest.get("unique_discovered_count")
    if candidate_count != unique_discovered_count:
        return _fail("candidate_population_count_mismatch")

    tranches = _sequence(manifest.get("tranches"))
    smart_rows = _sequence(marginal.get("smart"))
    if tranches is None or smart_rows is None:
        return _fail("population_rows_invalid")
    if len(smart_rows) != len(MARGINAL_CHECKPOINTS):
        return _fail("smart_checkpoint_count_mismatch")

    tranche_by_target: dict[int, Mapping[str, Any]] = {}
    for raw in tranches:
        if not isinstance(raw, Mapping):
            return _fail("manifest_tranche_invalid")
        target = raw.get("target")
        if isinstance(target, bool) or not isinstance(target, int) or target <= 0:
            return _fail("manifest_tranche_target_invalid")
        if target in tranche_by_target:
            return _fail("manifest_duplicate_tranche_target")
        tranche_by_target[target] = raw

    terminal = tranches[-1] if tranches else None
    bindings: list[dict[str, Any]] = []
    for checkpoint, row in zip(MARGINAL_CHECKPOINTS, smart_rows):
        if not isinstance(row, Mapping):
            return _fail("smart_row_invalid")
        if row.get("target") != checkpoint or row.get("strategy") != "smart":
            return _fail("smart_row_identity_mismatch")

        source = tranche_by_target.get(checkpoint)
        if source is None and isinstance(terminal, Mapping):
            terminal_count = terminal.get("selected_count")
            if (
                isinstance(candidate_count, int)
                and not isinstance(candidate_count, bool)
                and candidate_count < checkpoint
                and terminal_count == candidate_count
            ):
                source = terminal
        if source is None:
            return _fail(f"smart_checkpoint_{checkpoint}_unbound")

        selected_urls = _sequence(source.get("selected_urls"))
        selected_count = source.get("selected_count")
        if selected_urls is None or selected_count != len(selected_urls):
            return _fail(f"manifest_checkpoint_{checkpoint}_population_invalid")
        try:
            expected_fingerprint = _marginal_population_fingerprint(selected_urls)
        except ValueError as exc:
            return _fail(str(exc))

        if row.get("pages_assessed") != selected_count:
            return _fail(f"smart_checkpoint_{checkpoint}_page_count_mismatch")
        if row.get("population_fingerprint") != expected_fingerprint:
            return _fail(f"smart_checkpoint_{checkpoint}_population_mismatch")

        bindings.append(
            {
                "checkpoint": checkpoint,
                "manifest_target": source.get("target"),
                "manifest_role": source.get("role"),
                "pages_assessed": selected_count,
                "population_fingerprint": expected_fingerprint,
                "inventory_limited": selected_count < checkpoint,
            }
        )

    first = bindings[0] if bindings else None
    if first is None:
        return _fail("standard_reference_missing")
    manifest_standard_target = manifest.get("standard_reference_target")
    if first["pages_assessed"] != min(150, candidate_count):
        return _fail("standard_reference_page_count_mismatch")
    if manifest_standard_target != min(150, candidate_count):
        return _fail("standard_reference_target_mismatch")

    return {
        "version": ADAPTIVE_MANIFEST_MARGINAL_BINDING_VERSION,
        "valid": True,
        "reason": "ok",
        "candidate_count": candidate_count,
        "input_population_fingerprint": manifest.get("input_population_fingerprint"),
        "selection_targets": tuple(manifest.get("selection_targets") or ()),
        "checkpoints": MARGINAL_CHECKPOINTS,
        "bindings": tuple(bindings),
        "binding_fingerprint": _binding_fingerprint(bindings),
        "standard_150_preserved": True,
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }


def validate_manifest_bound_marginal_telemetry(
    artifact: Mapping[str, Any] | Any,
    manifest: Mapping[str, Any] | Any,
    marginal: Mapping[str, Any] | Any,
    *,
    manifest_integrity: Mapping[str, Any] | Any,
) -> dict[str, Any]:
    """Rebuild the binding and fail closed on any transported lineage drift."""
    expected = build_manifest_bound_marginal_telemetry(
        manifest,
        marginal,
        manifest_integrity=manifest_integrity,
    )
    if expected.get("valid") is not True:
        return {
            "version": ADAPTIVE_MANIFEST_MARGINAL_BINDING_INTEGRITY_VERSION,
            "valid": False,
            "reason": f"source:{expected.get('reason') or 'invalid'}",
            "production_budget_authorized": False,
            "site_fully_understood": False,
        }
    if not isinstance(artifact, Mapping):
        return {
            "version": ADAPTIVE_MANIFEST_MARGINAL_BINDING_INTEGRITY_VERSION,
            "valid": False,
            "reason": "artifact_not_mapping",
            "production_budget_authorized": False,
            "site_fully_understood": False,
        }

    if _canonical(artifact) != _canonical(expected):
        return {
            "version": ADAPTIVE_MANIFEST_MARGINAL_BINDING_INTEGRITY_VERSION,
            "valid": False,
            "reason": "artifact_mismatch",
            "production_budget_authorized": False,
            "site_fully_understood": False,
        }

    return {
        "version": ADAPTIVE_MANIFEST_MARGINAL_BINDING_INTEGRITY_VERSION,
        "valid": True,
        "reason": "ok",
        "binding_fingerprint": expected["binding_fingerprint"],
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }
