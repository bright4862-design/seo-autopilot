"""Bind Smart-500 benchmark evidence to replay-validated adaptive populations.

This module is pure and shadow-only. It proves that a transported population-bound
Smart-500-vs-blind-1000 benchmark bundle belongs to the exact discovered population
and Smart tranche manifest that produced the adaptive experiment. It performs no
network I/O, does not persist data, does not change crawl budgets, and cannot authorize
production expansion.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from .adaptive_benchmark_bundle import (
    ADAPTIVE_BENCHMARK_BUNDLE_VERSION,
    ADAPTIVE_BENCHMARK_POPULATION_VERSION,
    validate_adaptive_benchmark_bundle,
)
from .adaptive_crawl import MAX_ADAPTIVE_TARGET, STANDARD_150_TARGET
from .adaptive_tranche_manifest import (
    ADAPTIVE_TRANCHE_MANIFEST_INTEGRITY_VERSION,
    ADAPTIVE_TRANCHE_MANIFEST_VERSION,
)

ADAPTIVE_MANIFEST_BENCHMARK_BINDING_VERSION = "adaptive_manifest_benchmark_binding_v1"
ADAPTIVE_MANIFEST_BENCHMARK_BINDING_INTEGRITY_VERSION = (
    "adaptive_manifest_benchmark_binding_integrity_v1"
)
SMART_500_TARGET = 500


def _fail(reason: str) -> dict[str, Any]:
    return {
        "version": ADAPTIVE_MANIFEST_BENCHMARK_BINDING_VERSION,
        "valid": False,
        "reason": reason,
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }


def _materialize_exact_urls(values: Iterable[str] | Any) -> tuple[tuple[str, ...] | None, str | None]:
    if isinstance(values, (str, bytes, Mapping)):
        return None, "discovered_urls_not_sequence"
    try:
        materialized = tuple(values)
    except TypeError:
        return None, "discovered_urls_not_sequence"
    for value in materialized:
        if not isinstance(value, str) or not value or value != value.strip():
            return None, "discovered_urls_invalid_identity"
    return materialized, None


def _ordered_unique(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _manifest_population_fingerprint(urls: Sequence[str]) -> str:
    payload = json.dumps(
        list(urls),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _benchmark_population_fingerprint(role: str, urls: Sequence[str]) -> str:
    payload = json.dumps(
        {
            "version": ADAPTIVE_BENCHMARK_POPULATION_VERSION,
            "role": role,
            "urls": tuple(urls),
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _binding_fingerprint(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
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


def _manifest_population_for_target(
    manifest: Mapping[str, Any],
    target: int,
    *,
    unique_count: int,
) -> tuple[tuple[str, ...] | None, int | None, str | None]:
    tranches = _sequence(manifest.get("tranches"))
    if tranches is None:
        return None, None, "manifest_tranches_invalid"

    terminal: Mapping[str, Any] | None = None
    for raw in tranches:
        if not isinstance(raw, Mapping):
            return None, None, "manifest_tranche_invalid"
        terminal = raw
        if raw.get("target") == target:
            selected = _sequence(raw.get("selected_urls"))
            if selected is None:
                return None, None, f"manifest_target_{target}_population_invalid"
            selected_urls = tuple(selected)
            if raw.get("selected_count") != len(selected_urls):
                return None, None, f"manifest_target_{target}_count_mismatch"
            return selected_urls, int(raw.get("target")), None

    if terminal is not None and unique_count < target and terminal.get("selected_count") == unique_count:
        selected = _sequence(terminal.get("selected_urls"))
        if selected is None:
            return None, None, f"manifest_target_{target}_population_invalid"
        selected_urls = tuple(selected)
        if len(selected_urls) != unique_count:
            return None, None, f"manifest_target_{target}_count_mismatch"
        terminal_target = terminal.get("target")
        if isinstance(terminal_target, bool) or not isinstance(terminal_target, int):
            return None, None, "manifest_terminal_target_invalid"
        return selected_urls, terminal_target, None

    return None, None, f"manifest_target_{target}_unbound"


def build_manifest_bound_benchmark_bundle(
    manifest: Mapping[str, Any] | Any,
    benchmark_bundle: Mapping[str, Any] | Any,
    discovered_urls: Iterable[str] | Any,
    *,
    manifest_integrity: Mapping[str, Any] | Any,
) -> dict[str, Any]:
    """Bind one benchmark bundle to exact replayed Smart and FIFO reference populations."""
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

    raw_urls, reason = _materialize_exact_urls(discovered_urls)
    if reason:
        return _fail(reason)
    assert raw_urls is not None
    unique_urls = _ordered_unique(raw_urls)

    if manifest.get("discovered_input_count") != len(raw_urls):
        return _fail("manifest_discovered_input_count_mismatch")
    if manifest.get("unique_discovered_count") != len(unique_urls):
        return _fail("manifest_unique_discovered_count_mismatch")
    if manifest.get("input_population_fingerprint") != _manifest_population_fingerprint(raw_urls):
        return _fail("manifest_input_population_mismatch")

    if not isinstance(benchmark_bundle, Mapping):
        return _fail("benchmark_bundle_not_mapping")
    if benchmark_bundle.get("version") != ADAPTIVE_BENCHMARK_BUNDLE_VERSION:
        return _fail("benchmark_bundle_version_mismatch")
    bundle_integrity = validate_adaptive_benchmark_bundle(benchmark_bundle)
    if bundle_integrity.get("valid") is not True:
        return _fail(f"benchmark_bundle_integrity:{bundle_integrity.get('reason') or 'invalid'}")

    duplicate_count = len(raw_urls) - len(unique_urls)
    if benchmark_bundle.get("candidate_urls_supplied") != len(raw_urls):
        return _fail("benchmark_candidate_supplied_count_mismatch")
    if benchmark_bundle.get("candidate_urls_unique") != len(unique_urls):
        return _fail("benchmark_candidate_unique_count_mismatch")
    if benchmark_bundle.get("duplicate_candidate_identities_removed") != duplicate_count:
        return _fail("benchmark_duplicate_count_mismatch")

    expected_smart, manifest_smart_target, reason = _manifest_population_for_target(
        manifest,
        SMART_500_TARGET,
        unique_count=len(unique_urls),
    )
    if reason:
        return _fail(reason)
    assert expected_smart is not None and manifest_smart_target is not None

    smart = _sequence(benchmark_bundle.get("smart_selected"))
    blind = _sequence(benchmark_bundle.get("blind_selected"))
    if smart is None or blind is None:
        return _fail("benchmark_selected_populations_invalid")
    smart_urls = tuple(smart)
    blind_urls = tuple(blind)
    expected_blind = unique_urls[: min(MAX_ADAPTIVE_TARGET, len(unique_urls))]

    if smart_urls != expected_smart:
        return _fail("smart_500_population_mismatch")
    if blind_urls != expected_blind:
        return _fail("blind_1000_population_mismatch")

    expected_smart_fp = _benchmark_population_fingerprint("smart_500", smart_urls)
    expected_blind_fp = _benchmark_population_fingerprint("blind_1000", blind_urls)
    if benchmark_bundle.get("smart_population_sha256") != expected_smart_fp:
        return _fail("smart_500_population_fingerprint_mismatch")
    if benchmark_bundle.get("blind_population_sha256") != expected_blind_fp:
        return _fail("blind_1000_population_fingerprint_mismatch")

    tranches = _sequence(manifest.get("tranches"))
    if tranches is None or not tranches or not isinstance(tranches[0], Mapping):
        return _fail("standard_reference_missing")
    standard_row = tranches[0]
    standard_selected = _sequence(standard_row.get("selected_urls"))
    if standard_selected is None:
        return _fail("standard_reference_population_invalid")
    standard_population = tuple(standard_selected)
    standard_manifest_target = standard_row.get("target")
    if isinstance(standard_manifest_target, bool) or not isinstance(standard_manifest_target, int):
        return _fail("standard_reference_target_invalid")
    if standard_row.get("selected_count") != len(standard_population):
        return _fail("standard_reference_count_mismatch")
    if len(standard_population) > min(STANDARD_150_TARGET, len(unique_urls)):
        return _fail("standard_reference_exceeds_standard_150")
    if smart_urls[: len(standard_population)] != standard_population:
        return _fail("standard_150_prefix_mismatch")

    identity = {
        "candidate_urls_supplied": len(raw_urls),
        "candidate_urls_unique": len(unique_urls),
        "duplicate_candidate_identities_removed": duplicate_count,
        "manifest_input_population_fingerprint": manifest.get("input_population_fingerprint"),
        "manifest_smart_target": manifest_smart_target,
        "standard_manifest_target": standard_manifest_target,
        "smart_pages": len(smart_urls),
        "blind_pages": len(blind_urls),
        "smart_population_sha256": expected_smart_fp,
        "blind_population_sha256": expected_blind_fp,
    }
    return {
        "version": ADAPTIVE_MANIFEST_BENCHMARK_BINDING_VERSION,
        "valid": True,
        "reason": "benchmark_populations_bound_to_replay_manifest",
        **identity,
        "binding_fingerprint": _binding_fingerprint(identity),
        "standard_150_preserved": True,
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }


def validate_manifest_bound_benchmark_bundle(
    artifact: Mapping[str, Any] | Any,
    manifest: Mapping[str, Any] | Any,
    benchmark_bundle: Mapping[str, Any] | Any,
    discovered_urls: Iterable[str] | Any,
    *,
    manifest_integrity: Mapping[str, Any] | Any,
) -> dict[str, Any]:
    """Rebuild the binding and fail closed on any transported lineage drift."""
    expected = build_manifest_bound_benchmark_bundle(
        manifest,
        benchmark_bundle,
        discovered_urls,
        manifest_integrity=manifest_integrity,
    )
    if expected.get("valid") is not True:
        return {
            "version": ADAPTIVE_MANIFEST_BENCHMARK_BINDING_INTEGRITY_VERSION,
            "valid": False,
            "reason": f"source:{expected.get('reason') or 'invalid'}",
            "production_budget_authorized": False,
            "site_fully_understood": False,
        }
    if not isinstance(artifact, Mapping):
        return {
            "version": ADAPTIVE_MANIFEST_BENCHMARK_BINDING_INTEGRITY_VERSION,
            "valid": False,
            "reason": "artifact_not_mapping",
            "production_budget_authorized": False,
            "site_fully_understood": False,
        }
    if _canonical(artifact) != _canonical(expected):
        return {
            "version": ADAPTIVE_MANIFEST_BENCHMARK_BINDING_INTEGRITY_VERSION,
            "valid": False,
            "reason": "artifact_mismatch",
            "production_budget_authorized": False,
            "site_fully_understood": False,
        }
    return {
        "version": ADAPTIVE_MANIFEST_BENCHMARK_BINDING_INTEGRITY_VERSION,
        "valid": True,
        "reason": "ok",
        "binding_fingerprint": expected["binding_fingerprint"],
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }
