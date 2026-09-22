"""Cross-check manifest-bound adaptive evidence against one exact page population.

Pure/shadow-only Lane-A helper. It independently replays the population identity
carried by a replay-validated tranche manifest, the manifest-bound marginal telemetry,
and the manifest-bound Smart-500-vs-blind-1000 benchmark. It performs no crawling,
network I/O, persistence, budget mutation, authority writes, projection, admission,
release, deployment, or production work.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

ADAPTIVE_TRANCHE_MANIFEST_VERSION = "adaptive_tranche_selection_manifest_v1"
ADAPTIVE_TRANCHE_MANIFEST_INTEGRITY_VERSION = (
    "adaptive_tranche_selection_manifest_integrity_v1"
)
ADAPTIVE_MANIFEST_MARGINAL_BINDING_VERSION = "adaptive_manifest_marginal_binding_v1"
ADAPTIVE_MANIFEST_BENCHMARK_BINDING_VERSION = "adaptive_manifest_benchmark_binding_v1"
ADAPTIVE_BENCHMARK_POPULATION_VERSION = "adaptive_benchmark_population_v1"
ADAPTIVE_MANIFEST_POPULATION_CROSSCHECK_VERSION = (
    "adaptive_manifest_population_crosscheck_v1"
)
ADAPTIVE_MANIFEST_POPULATION_CROSSCHECK_INTEGRITY_VERSION = (
    "adaptive_manifest_population_crosscheck_integrity_v1"
)

STANDARD_TARGET = 150
SMART_TARGET = 500
BLIND_TARGET = 1000
CHECKPOINTS = (STANDARD_TARGET, SMART_TARGET, BLIND_TARGET)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _fail(reason: str) -> dict[str, Any]:
    return {
        "version": ADAPTIVE_MANIFEST_POPULATION_CROSSCHECK_VERSION,
        "valid": False,
        "reason": reason,
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }


def _sequence(value: Any) -> Sequence[Any] | None:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        return None
    return value


def _sha256(value: Any) -> str | None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        return None
    return value


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
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


def _exact_urls(values: Iterable[str] | Any) -> tuple[tuple[str, ...] | None, str | None]:
    if isinstance(values, (str, bytes, Mapping)):
        return None, "discovered_urls_not_sequence"
    try:
        urls = tuple(values)
    except TypeError:
        return None, "discovered_urls_not_sequence"
    for value in urls:
        if not isinstance(value, str) or not value or value != value.strip():
            return None, "discovered_urls_invalid_identity"
    return urls, None


def _ordered_unique(urls: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(urls))


def _manifest_population_fingerprint(urls: Sequence[str]) -> str:
    payload = json.dumps(
        list(urls),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _marginal_population_fingerprint(urls: Sequence[str]) -> str:
    digest = hashlib.sha256()
    digest.update(b"adaptive_marginal_population_v1\0")
    for url in urls:
        digest.update(url.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


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


def _crosscheck_fingerprint(identity: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        identity,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _forbidden_authority_claim(source: Mapping[str, Any]) -> bool:
    return (
        source.get("population_scope_complete") is not False
        or source.get("production_budget_authorized") is not False
        or source.get("site_fully_understood") is not False
    )


def _manifest_population_for_checkpoint(
    manifest: Mapping[str, Any],
    checkpoint: int,
    *,
    unique_count: int,
) -> tuple[tuple[str, ...] | None, Mapping[str, Any] | None, str | None]:
    tranches = _sequence(manifest.get("tranches"))
    if tranches is None or not tranches:
        return None, None, "manifest_tranches_invalid"

    terminal: Mapping[str, Any] | None = None
    for raw in tranches:
        if not isinstance(raw, Mapping):
            return None, None, "manifest_tranche_invalid"
        terminal = raw
        if raw.get("target") == checkpoint:
            selected = _sequence(raw.get("selected_urls"))
            if selected is None:
                return None, None, f"manifest_checkpoint_{checkpoint}_population_invalid"
            selected_urls = tuple(selected)
            if raw.get("selected_count") != len(selected_urls):
                return None, None, f"manifest_checkpoint_{checkpoint}_count_mismatch"
            return selected_urls, raw, None

    if terminal is not None and unique_count < checkpoint:
        selected = _sequence(terminal.get("selected_urls"))
        selected_count = _nonnegative_int(terminal.get("selected_count"))
        if selected is not None and selected_count == unique_count == len(selected):
            return tuple(selected), terminal, None

    return None, None, f"manifest_checkpoint_{checkpoint}_unbound"


def _marginal_rows(
    marginal_binding: Mapping[str, Any],
) -> tuple[dict[int, Mapping[str, Any]] | None, str | None]:
    rows = _sequence(marginal_binding.get("bindings"))
    if rows is None or len(rows) != len(CHECKPOINTS):
        return None, "marginal_binding_checkpoint_count_invalid"
    result: dict[int, Mapping[str, Any]] = {}
    for raw in rows:
        if not isinstance(raw, Mapping):
            return None, "marginal_binding_checkpoint_invalid"
        checkpoint = raw.get("checkpoint")
        if checkpoint not in CHECKPOINTS or checkpoint in result:
            return None, "marginal_binding_checkpoint_identity_invalid"
        result[checkpoint] = raw
    if tuple(sorted(result)) != CHECKPOINTS:
        return None, "marginal_binding_checkpoint_set_invalid"
    return result, None


def build_manifest_population_crosscheck(
    manifest: Mapping[str, Any] | Any,
    marginal_binding: Mapping[str, Any] | Any,
    benchmark_binding: Mapping[str, Any] | Any,
    discovered_urls: Iterable[str] | Any,
    *,
    manifest_integrity: Mapping[str, Any] | Any,
) -> dict[str, Any]:
    """Prove both evidence families refer to one exact replayed population lineage."""
    if not isinstance(manifest, Mapping):
        return _fail("manifest_not_mapping")
    if manifest.get("version") != ADAPTIVE_TRANCHE_MANIFEST_VERSION:
        return _fail("manifest_version_mismatch")
    if _forbidden_authority_claim(manifest):
        return _fail("manifest_forbidden_authority_claim")

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

    raw_urls, reason = _exact_urls(discovered_urls)
    if reason:
        return _fail(reason)
    assert raw_urls is not None
    unique_urls = _ordered_unique(raw_urls)

    if manifest.get("discovered_input_count") != len(raw_urls):
        return _fail("manifest_discovered_input_count_mismatch")
    if manifest.get("unique_discovered_count") != len(unique_urls):
        return _fail("manifest_unique_discovered_count_mismatch")
    input_fingerprint = _manifest_population_fingerprint(raw_urls)
    if manifest.get("input_population_fingerprint") != input_fingerprint:
        return _fail("manifest_input_population_mismatch")

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

    unique_count = len(unique_urls)
    marginal_count = _nonnegative_int(marginal_binding.get("candidate_count"))
    benchmark_unique = _nonnegative_int(benchmark_binding.get("candidate_urls_unique"))
    benchmark_supplied = _nonnegative_int(benchmark_binding.get("candidate_urls_supplied"))
    benchmark_duplicates = _nonnegative_int(
        benchmark_binding.get("duplicate_candidate_identities_removed")
    )
    if (
        marginal_count != unique_count
        or benchmark_unique != unique_count
        or benchmark_supplied != len(raw_urls)
        or benchmark_duplicates != len(raw_urls) - unique_count
    ):
        return _fail("candidate_population_geometry_mismatch")

    if marginal_binding.get("input_population_fingerprint") != input_fingerprint:
        return _fail("marginal_binding_input_population_mismatch")
    if benchmark_binding.get("manifest_input_population_fingerprint") != input_fingerprint:
        return _fail("benchmark_binding_input_population_mismatch")
    if _sha256(marginal_binding.get("binding_fingerprint")) is None:
        return _fail("marginal_binding_fingerprint_invalid")
    if _sha256(benchmark_binding.get("binding_fingerprint")) is None:
        return _fail("benchmark_binding_fingerprint_invalid")

    rows, reason = _marginal_rows(marginal_binding)
    if reason:
        return _fail(reason)
    assert rows is not None

    manifest_populations: dict[int, tuple[str, ...]] = {}
    manifest_rows: dict[int, Mapping[str, Any]] = {}
    marginal_population_fingerprints: list[tuple[int, str]] = []
    manifest_population_fingerprints: list[tuple[int, str]] = []

    for checkpoint in CHECKPOINTS:
        selected, source, reason = _manifest_population_for_checkpoint(
            manifest,
            checkpoint,
            unique_count=unique_count,
        )
        if reason:
            return _fail(reason)
        assert selected is not None and source is not None

        source_fp = _manifest_population_fingerprint(selected)
        if source.get("selected_population_fingerprint") != source_fp:
            return _fail(f"manifest_checkpoint_{checkpoint}_fingerprint_mismatch")

        row = rows[checkpoint]
        expected_marginal_fp = _marginal_population_fingerprint(selected)
        if row.get("pages_assessed") != len(selected):
            return _fail(f"marginal_binding_checkpoint_{checkpoint}_page_count_mismatch")
        if row.get("manifest_target") != source.get("target"):
            return _fail(f"marginal_binding_checkpoint_{checkpoint}_manifest_target_mismatch")
        if row.get("manifest_role") != source.get("role"):
            return _fail(f"marginal_binding_checkpoint_{checkpoint}_manifest_role_mismatch")
        if row.get("population_fingerprint") != expected_marginal_fp:
            return _fail(f"marginal_binding_checkpoint_{checkpoint}_population_mismatch")
        if row.get("inventory_limited") is not (len(selected) < checkpoint):
            return _fail(f"marginal_binding_checkpoint_{checkpoint}_inventory_state_mismatch")

        manifest_populations[checkpoint] = selected
        manifest_rows[checkpoint] = source
        marginal_population_fingerprints.append((checkpoint, expected_marginal_fp))
        manifest_population_fingerprints.append((checkpoint, source_fp))

    standard_population = manifest_populations[STANDARD_TARGET]
    smart_population = manifest_populations[SMART_TARGET]
    if smart_population[: len(standard_population)] != standard_population:
        return _fail("manifest_standard_150_not_smart_prefix")

    expected_blind = unique_urls[: min(BLIND_TARGET, unique_count)]
    expected_smart_benchmark_fp = _benchmark_population_fingerprint(
        "smart_500", smart_population
    )
    expected_blind_benchmark_fp = _benchmark_population_fingerprint(
        "blind_1000", expected_blind
    )

    smart_pages = _nonnegative_int(benchmark_binding.get("smart_pages"))
    blind_pages = _nonnegative_int(benchmark_binding.get("blind_pages"))
    manifest_smart_target = _nonnegative_int(benchmark_binding.get("manifest_smart_target"))
    standard_manifest_target = _nonnegative_int(
        benchmark_binding.get("standard_manifest_target")
    )
    if (
        smart_pages != len(smart_population)
        or blind_pages != len(expected_blind)
        or manifest_smart_target != manifest_rows[SMART_TARGET].get("target")
        or standard_manifest_target != manifest_rows[STANDARD_TARGET].get("target")
    ):
        return _fail("benchmark_population_geometry_mismatch")
    if benchmark_binding.get("smart_population_sha256") != expected_smart_benchmark_fp:
        return _fail("benchmark_smart_500_population_mismatch")
    if benchmark_binding.get("blind_population_sha256") != expected_blind_benchmark_fp:
        return _fail("benchmark_blind_1000_population_mismatch")

    identity = {
        "candidate_urls_supplied": len(raw_urls),
        "candidate_urls_unique": unique_count,
        "duplicate_candidate_identities_removed": len(raw_urls) - unique_count,
        "input_population_fingerprint": input_fingerprint,
        "selection_targets": tuple(manifest.get("selection_targets") or ()),
        "standard_150_pages": len(standard_population),
        "smart_500_pages": len(smart_population),
        "blind_1000_pages": len(expected_blind),
        "manifest_population_fingerprints": tuple(manifest_population_fingerprints),
        "marginal_population_fingerprints": tuple(marginal_population_fingerprints),
        "benchmark_smart_population_sha256": expected_smart_benchmark_fp,
        "benchmark_blind_population_sha256": expected_blind_benchmark_fp,
        "marginal_binding_fingerprint": marginal_binding["binding_fingerprint"],
        "benchmark_binding_fingerprint": benchmark_binding["binding_fingerprint"],
    }
    return {
        "version": ADAPTIVE_MANIFEST_POPULATION_CROSSCHECK_VERSION,
        "valid": True,
        "reason": "manifest_population_lineage_crosschecked",
        **identity,
        "crosscheck_fingerprint": _crosscheck_fingerprint(identity),
        "standard_150_preserved": True,
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }


def validate_manifest_population_crosscheck(
    artifact: Mapping[str, Any] | Any,
    manifest: Mapping[str, Any] | Any,
    marginal_binding: Mapping[str, Any] | Any,
    benchmark_binding: Mapping[str, Any] | Any,
    discovered_urls: Iterable[str] | Any,
    *,
    manifest_integrity: Mapping[str, Any] | Any,
) -> dict[str, Any]:
    """Rebuild the cross-check and reject transported population drift."""
    expected = build_manifest_population_crosscheck(
        manifest,
        marginal_binding,
        benchmark_binding,
        discovered_urls,
        manifest_integrity=manifest_integrity,
    )
    if expected.get("valid") is not True:
        return {
            "version": ADAPTIVE_MANIFEST_POPULATION_CROSSCHECK_INTEGRITY_VERSION,
            "valid": False,
            "reason": f"source:{expected.get('reason') or 'invalid'}",
            "production_budget_authorized": False,
            "site_fully_understood": False,
        }
    if not isinstance(artifact, Mapping):
        return {
            "version": ADAPTIVE_MANIFEST_POPULATION_CROSSCHECK_INTEGRITY_VERSION,
            "valid": False,
            "reason": "artifact_not_mapping",
            "production_budget_authorized": False,
            "site_fully_understood": False,
        }
    if _canonical(artifact) != _canonical(expected):
        return {
            "version": ADAPTIVE_MANIFEST_POPULATION_CROSSCHECK_INTEGRITY_VERSION,
            "valid": False,
            "reason": "artifact_mismatch",
            "production_budget_authorized": False,
            "site_fully_understood": False,
        }
    return {
        "version": ADAPTIVE_MANIFEST_POPULATION_CROSSCHECK_INTEGRITY_VERSION,
        "valid": True,
        "reason": "ok",
        "crosscheck_fingerprint": expected["crosscheck_fingerprint"],
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }
