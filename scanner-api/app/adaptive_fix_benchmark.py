"""Pure Smart-500 vs blind-1000 Fix-yield benchmark for Lane-A adaptive crawl.

The helper binds opaque Fix fingerprints to one replay-validated tranche manifest
and the exact discovered URL sequence. It performs no crawl, persistence, repair
prioritization, budget authorization, customer projection, or production wiring.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

ADAPTIVE_FIX_BENCHMARK_VERSION = "adaptive_manifest_fix_benchmark_v1"
ADAPTIVE_FIX_BENCHMARK_INTEGRITY_VERSION = "adaptive_manifest_fix_benchmark_integrity_v1"
ADAPTIVE_TRANCHE_MANIFEST_VERSION = "adaptive_tranche_selection_manifest_v1"
ADAPTIVE_TRANCHE_MANIFEST_INTEGRITY_VERSION = "adaptive_tranche_selection_manifest_integrity_v1"
STANDARD_150_TARGET = 150
SMART_500_TARGET = 500
BLIND_1000_TARGET = 1000


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, set):
        return sorted(_canonical(item) for item in value)
    return value


def _fingerprint_json(value: Any, *, domain: str) -> str:
    digest = hashlib.sha256()
    digest.update(domain.encode("utf-8"))
    digest.update(b"\0")
    digest.update(
        json.dumps(
            _canonical(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    return digest.hexdigest()


def _population_fingerprint(urls: Sequence[str]) -> str:
    payload = json.dumps(list(urls), ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(payload).hexdigest()


def _strict_sequence(value: Any, *, field: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        raise ValueError(f"{field}_invalid")
    return tuple(value)


def _strict_urls(value: Any, *, field: str, allow_duplicates: bool = False) -> tuple[str, ...]:
    rows = _strict_sequence(value, field=field)
    for url in rows:
        if not isinstance(url, str) or not url or url != url.strip():
            raise ValueError(f"{field}_invalid_url_identity")
    if not allow_duplicates and len(set(rows)) != len(rows):
        raise ValueError(f"{field}_duplicate_url_identity")
    return rows


def _materialize_discovered(values: Iterable[str] | Any) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, Mapping)):
        raise ValueError("discovered_urls_invalid")
    try:
        rows = tuple(values)
    except TypeError as exc:
        raise ValueError("discovered_urls_invalid") from exc
    for url in rows:
        if not isinstance(url, str) or not url or url != url.strip():
            raise ValueError("discovered_urls_invalid_url_identity")
    return rows


def _ordered_unique(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _strict_fix_set(
    urls: Sequence[str],
    fingerprints_by_url: Mapping[str, Iterable[str]],
    *,
    field: str,
) -> set[str]:
    result: set[str] = set()
    for url in urls:
        raw_values = fingerprints_by_url.get(url, ())
        if isinstance(raw_values, (str, bytes, Mapping)):
            raise ValueError(f"{field}_invalid_iterable")
        try:
            values = tuple(raw_values)
        except TypeError as exc:
            raise ValueError(f"{field}_invalid_iterable") from exc
        for raw in values:
            if not isinstance(raw, str) or not raw or raw != raw.strip():
                raise ValueError(f"{field}_invalid_fingerprint")
            result.add(raw)
    return result


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 6)


def _per_100(count: int, pages: int) -> float | None:
    if pages <= 0:
        return None
    return round(count * 100.0 / pages, 4)


def _require_manifest_integrity(
    manifest: Mapping[str, Any],
    manifest_integrity: Mapping[str, Any],
) -> None:
    if manifest.get("version") != ADAPTIVE_TRANCHE_MANIFEST_VERSION:
        raise ValueError("manifest_version_mismatch")
    if (
        manifest_integrity.get("version")
        != ADAPTIVE_TRANCHE_MANIFEST_INTEGRITY_VERSION
        or manifest_integrity.get("valid") is not True
    ):
        raise ValueError("manifest_not_replay_validated")
    for key in (
        "population_scope_complete",
        "production_budget_authorized",
        "site_fully_understood",
    ):
        if manifest.get(key) is not False:
            raise ValueError("manifest_forbidden_authority_claim")

    for key in (
        "input_population_fingerprint",
        "selection_targets",
        "standard_reference_population_fingerprint",
    ):
        if _canonical(manifest_integrity.get(key)) != _canonical(manifest.get(key)):
            raise ValueError(f"manifest_integrity_{key}_mismatch")


def _validated_tranches(manifest: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    tranches = _strict_sequence(manifest.get("tranches"), field="tranches")
    targets = _strict_sequence(manifest.get("selection_targets"), field="selection_targets")
    if len(tranches) != len(targets):
        raise ValueError("tranche_count_mismatch")

    validated: list[dict[str, Any]] = []
    previous: tuple[str, ...] = ()
    previous_target: int | None = None
    for index, (target, raw) in enumerate(zip(targets, tranches)):
        if isinstance(target, bool) or not isinstance(target, int) or target <= 0 or target > BLIND_1000_TARGET:
            raise ValueError("selection_target_invalid")
        if not isinstance(raw, Mapping) or raw.get("target") != target:
            raise ValueError("tranche_identity_mismatch")
        selected = _strict_urls(raw.get("selected_urls"), field=f"tranche_{index}_selected_urls")
        if len(selected) > target:
            raise ValueError("tranche_target_exceeded")
        if raw.get("selected_count") != len(selected):
            raise ValueError("selected_count_mismatch")
        if raw.get("selected_population_fingerprint") != _population_fingerprint(selected):
            raise ValueError("selected_population_fingerprint_mismatch")
        if raw.get("inventory_limited") is not (len(selected) < target):
            raise ValueError("inventory_limited_mismatch")

        if previous_target is not None and previous_target >= STANDARD_150_TARGET:
            if selected[: len(previous)] != previous:
                raise ValueError("tranche_prefix_drift")
            if raw.get("prefix_nesting_checked") is not True or raw.get("prefix_nesting_valid") is not True:
                raise ValueError("prefix_check_invalid")
        validated.append({"target": target, "selected": selected})
        previous = selected
        previous_target = target

    if not validated:
        raise ValueError("manifest_has_no_tranches")
    standard = validated[0]
    if standard["target"] != manifest.get("standard_reference_target"):
        raise ValueError("standard_reference_target_mismatch")
    if standard["target"] > STANDARD_150_TARGET:
        raise ValueError("standard_reference_exceeded")
    if manifest.get("standard_reference_population_fingerprint") != _population_fingerprint(standard["selected"]):
        raise ValueError("standard_reference_population_mismatch")
    return tuple(validated)


def _population_for_smart_500(
    tranches: Sequence[Mapping[str, Any]],
    *,
    unique_count: int,
) -> tuple[int, tuple[str, ...]]:
    for row in tranches:
        if row["target"] == SMART_500_TARGET:
            return SMART_500_TARGET, tuple(row["selected"])
    if unique_count < SMART_500_TARGET:
        terminal = tranches[-1]
        selected = tuple(terminal["selected"])
        if len(selected) != unique_count:
            raise ValueError("inventory_limited_smart_population_unbound")
        return int(terminal["target"]), selected
    raise ValueError("smart_500_population_unbound")


def build_manifest_bound_fix_benchmark(
    manifest: Mapping[str, Any],
    manifest_integrity: Mapping[str, Any],
    discovered_urls: Iterable[str],
    *,
    fix_fingerprints_by_url: Mapping[str, Iterable[str]],
    high_impact_fix_fingerprints_by_url: Mapping[str, Iterable[str]] | None = None,
) -> dict[str, Any]:
    """Compare exact Smart-500 and FIFO blind-1000 Fix evidence.

    Fix fingerprints are opaque evidence identities. No severity or repair-priority
    semantics are inferred here.
    """
    if not isinstance(manifest, Mapping) or not isinstance(manifest_integrity, Mapping):
        raise ValueError("manifest_or_integrity_not_mapping")
    if not isinstance(fix_fingerprints_by_url, Mapping):
        raise ValueError("fix_fingerprints_not_mapping")
    if high_impact_fix_fingerprints_by_url is not None and not isinstance(
        high_impact_fix_fingerprints_by_url, Mapping
    ):
        raise ValueError("high_impact_fix_fingerprints_not_mapping")

    _require_manifest_integrity(manifest, manifest_integrity)
    tranches = _validated_tranches(manifest)
    raw_urls = _materialize_discovered(discovered_urls)
    unique_urls = _ordered_unique(raw_urls)

    if manifest.get("discovered_input_count") != len(raw_urls):
        raise ValueError("manifest_discovered_input_count_mismatch")
    if manifest.get("unique_discovered_count") != len(unique_urls):
        raise ValueError("manifest_unique_discovered_count_mismatch")
    if manifest.get("input_population_fingerprint") != _population_fingerprint(raw_urls):
        raise ValueError("manifest_input_population_mismatch")

    smart_manifest_target, smart_urls = _population_for_smart_500(
        tranches, unique_count=len(unique_urls)
    )
    blind_urls = unique_urls[: min(BLIND_1000_TARGET, len(unique_urls))]
    standard_urls = tuple(tranches[0]["selected"])

    universe = set(unique_urls)
    if any(url not in universe for url in smart_urls):
        raise ValueError("smart_population_outside_discovery")
    if any(url not in universe for url in standard_urls):
        raise ValueError("standard_population_outside_discovery")
    if smart_urls[: len(standard_urls)] != standard_urls:
        raise ValueError("standard_150_prefix_mismatch")

    standard_fixes = _strict_fix_set(
        standard_urls, fix_fingerprints_by_url, field="fix_fingerprints"
    )
    smart_fixes = _strict_fix_set(
        smart_urls, fix_fingerprints_by_url, field="fix_fingerprints"
    )
    blind_fixes = _strict_fix_set(
        blind_urls, fix_fingerprints_by_url, field="fix_fingerprints"
    )
    shared_fixes = smart_fixes & blind_fixes
    blind_only_fixes = blind_fixes - smart_fixes
    smart_only_fixes = smart_fixes - blind_fixes
    incremental_smart_fixes = smart_fixes - standard_fixes
    incremental_smart_pages = len(smart_urls) - len(standard_urls)
    if incremental_smart_pages < 0:
        raise ValueError("smart_pages_regressed_below_standard")

    if high_impact_fix_fingerprints_by_url is None:
        high_state = "not_observed"
        smart_high_count = None
        blind_high_count = None
        shared_high_count = None
        blind_only_high_count = None
        smart_high_coverage = None
    else:
        smart_high = _strict_fix_set(
            smart_urls,
            high_impact_fix_fingerprints_by_url,
            field="high_impact_fix_fingerprints",
        )
        blind_high = _strict_fix_set(
            blind_urls,
            high_impact_fix_fingerprints_by_url,
            field="high_impact_fix_fingerprints",
        )
        if not smart_high.issubset(smart_fixes) or not blind_high.issubset(blind_fixes):
            raise ValueError("high_impact_fix_not_in_fix_population")
        shared_high = smart_high & blind_high
        high_state = "observed"
        smart_high_count = len(smart_high)
        blind_high_count = len(blind_high)
        shared_high_count = len(shared_high)
        blind_only_high_count = len(blind_high - smart_high)
        smart_high_coverage = _ratio(len(shared_high), len(blind_high))

    identity = {
        "manifest_input_population_fingerprint": manifest["input_population_fingerprint"],
        "candidate_urls_supplied": len(raw_urls),
        "candidate_urls_unique": len(unique_urls),
        "duplicate_candidate_identities_removed": len(raw_urls) - len(unique_urls),
        "standard_reference_target": manifest.get("standard_reference_target"),
        "standard_reference_pages": len(standard_urls),
        "standard_reference_population_fingerprint": _population_fingerprint(standard_urls),
        "smart_manifest_target": smart_manifest_target,
        "smart_pages_assessed": len(smart_urls),
        "smart_population_fingerprint": _population_fingerprint(smart_urls),
        "blind_pages_assessed": len(blind_urls),
        "blind_population_fingerprint": _population_fingerprint(blind_urls),
    }
    result = {
        "version": ADAPTIVE_FIX_BENCHMARK_VERSION,
        **identity,
        "pages_saved_by_smart": len(blind_urls) - len(smart_urls),
        "standard_fix_fingerprints": len(standard_fixes),
        "smart_fix_fingerprints": len(smart_fixes),
        "blind_fix_fingerprints": len(blind_fixes),
        "shared_fix_fingerprints": len(shared_fixes),
        "blind_only_fix_fingerprints": len(blind_only_fixes),
        "smart_only_fix_fingerprints": len(smart_only_fixes),
        "smart_fix_coverage_vs_blind": _ratio(len(shared_fixes), len(blind_fixes)),
        "smart_incremental_pages_vs_standard": incremental_smart_pages,
        "smart_incremental_fix_fingerprints_vs_standard": len(incremental_smart_fixes),
        "smart_incremental_fix_yield_per_100": _per_100(
            len(incremental_smart_fixes), incremental_smart_pages
        ),
        "high_impact_evidence_state": high_state,
        "smart_high_impact_fix_fingerprints": smart_high_count,
        "blind_high_impact_fix_fingerprints": blind_high_count,
        "shared_high_impact_fix_fingerprints": shared_high_count,
        "blind_only_high_impact_fix_fingerprints": blind_only_high_count,
        "smart_high_impact_coverage_vs_blind": smart_high_coverage,
        "standard_150_preserved": True,
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }
    result["binding_fingerprint"] = _fingerprint_json(
        result, domain=ADAPTIVE_FIX_BENCHMARK_VERSION
    )
    return result


def validate_manifest_bound_fix_benchmark(
    result: Mapping[str, Any] | Any,
    manifest: Mapping[str, Any],
    manifest_integrity: Mapping[str, Any],
    discovered_urls: Iterable[str],
    *,
    fix_fingerprints_by_url: Mapping[str, Iterable[str]],
    high_impact_fix_fingerprints_by_url: Mapping[str, Iterable[str]] | None = None,
) -> dict[str, Any]:
    """Rebuild benchmark evidence and fail closed on lineage/arithmetic drift."""
    if not isinstance(result, Mapping):
        return {
            "version": ADAPTIVE_FIX_BENCHMARK_INTEGRITY_VERSION,
            "valid": False,
            "errors": ("result_not_mapping",),
        }
    try:
        expected = build_manifest_bound_fix_benchmark(
            manifest,
            manifest_integrity,
            discovered_urls,
            fix_fingerprints_by_url=fix_fingerprints_by_url,
            high_impact_fix_fingerprints_by_url=high_impact_fix_fingerprints_by_url,
        )
    except (TypeError, ValueError) as exc:
        return {
            "version": ADAPTIVE_FIX_BENCHMARK_INTEGRITY_VERSION,
            "valid": False,
            "errors": ("replay_input_invalid",),
            "detail": str(exc),
        }

    errors: list[str] = []
    for key, expected_value in expected.items():
        if _canonical(result.get(key)) != _canonical(expected_value):
            errors.append(f"{key}_mismatch")
    for key in (
        "population_scope_complete",
        "production_budget_authorized",
        "site_fully_understood",
    ):
        if result.get(key) is not False:
            errors.append("forbidden_authority_claim")
    return {
        "version": ADAPTIVE_FIX_BENCHMARK_INTEGRITY_VERSION,
        "valid": not errors,
        "errors": tuple(dict.fromkeys(errors)),
        "binding_fingerprint": expected["binding_fingerprint"],
        "standard_150_preserved": expected["standard_150_preserved"],
    }
