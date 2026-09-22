"""Pure, manifest-bound marginal Fix-yield telemetry for Lane-A adaptive crawl.

This module consumes an already replay-validated adaptive tranche manifest plus
caller-supplied Fix fingerprints. It performs no crawl, persistence, repair
prioritization, budget authorization, or production wiring.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

ADAPTIVE_FIX_YIELD_VERSION = "adaptive_manifest_fix_yield_v1"
ADAPTIVE_FIX_YIELD_INTEGRITY_VERSION = "adaptive_manifest_fix_yield_integrity_v1"
ADAPTIVE_TRANCHE_MANIFEST_VERSION = "adaptive_tranche_selection_manifest_v1"
ADAPTIVE_TRANCHE_MANIFEST_INTEGRITY_VERSION = (
    "adaptive_tranche_selection_manifest_integrity_v1"
)
STANDARD_150_TARGET = 150
MAX_ADAPTIVE_TARGET = 1000


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
    payload = json.dumps(
        list(urls),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _strict_sequence(value: Any, *, field: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        raise ValueError(f"{field}_invalid")
    return tuple(value)


def _strict_urls(value: Any, *, field: str) -> tuple[str, ...]:
    rows = _strict_sequence(value, field=field)
    for url in rows:
        if not isinstance(url, str) or not url or url != url.strip():
            raise ValueError(f"{field}_invalid_url_identity")
    if len(set(rows)) != len(rows):
        raise ValueError(f"{field}_duplicate_url_identity")
    return rows


def _strict_fix_set(
    selected_urls: Sequence[str],
    fingerprints_by_url: Mapping[str, Iterable[str]],
    *,
    field: str,
) -> set[str]:
    result: set[str] = set()
    for url in selected_urls:
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


def _per_100(count: int, pages_added: int) -> float | None:
    if pages_added <= 0:
        return None
    return round(count * 100.0 / pages_added, 4)


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

    if (
        manifest_integrity.get("input_population_fingerprint")
        != manifest.get("input_population_fingerprint")
    ):
        raise ValueError("manifest_integrity_input_fingerprint_mismatch")
    if tuple(manifest_integrity.get("selection_targets") or ()) != tuple(
        manifest.get("selection_targets") or ()
    ):
        raise ValueError("manifest_integrity_selection_targets_mismatch")
    if (
        manifest_integrity.get("standard_reference_population_fingerprint")
        != manifest.get("standard_reference_population_fingerprint")
    ):
        raise ValueError("manifest_integrity_standard_reference_mismatch")


def _validated_tranches(manifest: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    tranches = _strict_sequence(manifest.get("tranches"), field="tranches")
    selection_targets = tuple(manifest.get("selection_targets") or ())
    if len(tranches) != len(selection_targets):
        raise ValueError("tranche_count_mismatch")

    validated: list[dict[str, Any]] = []
    previous_urls: tuple[str, ...] = ()
    previous_target: int | None = None
    for index, (raw_target, raw_row) in enumerate(zip(selection_targets, tranches)):
        if (
            isinstance(raw_target, bool)
            or not isinstance(raw_target, int)
            or raw_target <= 0
            or raw_target > MAX_ADAPTIVE_TARGET
        ):
            raise ValueError("selection_target_invalid")
        if not isinstance(raw_row, Mapping) or raw_row.get("target") != raw_target:
            raise ValueError("tranche_identity_mismatch")

        selected = _strict_urls(
            raw_row.get("selected_urls"),
            field=f"tranche_{index}_selected_urls",
        )
        added = _strict_urls(
            raw_row.get("added_urls"),
            field=f"tranche_{index}_added_urls",
        )
        if len(selected) > raw_target:
            raise ValueError("tranche_target_exceeded")
        if raw_row.get("selected_count") != len(selected):
            raise ValueError("selected_count_mismatch")
        if raw_row.get("added_count") != len(added):
            raise ValueError("added_count_mismatch")
        if raw_row.get("selected_population_fingerprint") != _population_fingerprint(selected):
            raise ValueError("selected_population_fingerprint_mismatch")
        if raw_row.get("added_population_fingerprint") != _population_fingerprint(added):
            raise ValueError("added_population_fingerprint_mismatch")

        if previous_target is None:
            expected_added = selected
        elif previous_target >= STANDARD_150_TARGET:
            if selected[: len(previous_urls)] != previous_urls:
                raise ValueError("tranche_prefix_drift")
            expected_added = selected[len(previous_urls) :]
            if raw_row.get("prefix_nesting_checked") is not True:
                raise ValueError("prefix_check_missing")
            if raw_row.get("prefix_nesting_valid") is not True:
                raise ValueError("prefix_check_invalid")
        else:
            previous_set = set(previous_urls)
            expected_added = tuple(url for url in selected if url not in previous_set)
        if added != expected_added:
            raise ValueError("added_population_mismatch")
        if raw_row.get("inventory_limited") is not (len(selected) < raw_target):
            raise ValueError("inventory_limited_mismatch")

        validated.append(
            {
                "target": raw_target,
                "selected_urls": selected,
                "added_urls": added,
                "selected_population_fingerprint": raw_row[
                    "selected_population_fingerprint"
                ],
                "added_population_fingerprint": raw_row[
                    "added_population_fingerprint"
                ],
            }
        )
        previous_urls = selected
        previous_target = raw_target

    if validated:
        first = validated[0]
        standard_target = manifest.get("standard_reference_target")
        if first["target"] != standard_target:
            raise ValueError("standard_reference_target_mismatch")
        if first["target"] > STANDARD_150_TARGET:
            raise ValueError("standard_reference_exceeded")
        if (
            manifest.get("standard_reference_population_fingerprint")
            != first["selected_population_fingerprint"]
        ):
            raise ValueError("standard_reference_population_mismatch")
    return tuple(validated)


def build_manifest_bound_fix_yield(
    manifest: Mapping[str, Any],
    manifest_integrity: Mapping[str, Any],
    *,
    fix_fingerprints_by_url: Mapping[str, Iterable[str]],
    high_impact_fix_fingerprints_by_url: Mapping[str, Iterable[str]] | None = None,
) -> dict[str, Any]:
    """Build exact per-tranche marginal Fix-yield telemetry.

    ``manifest_integrity`` must come from the replay validator for the exact
    manifest. The helper only measures evidence already supplied by the caller.
    """
    if not isinstance(manifest, Mapping) or not isinstance(manifest_integrity, Mapping):
        raise ValueError("manifest_or_integrity_not_mapping")
    if not isinstance(fix_fingerprints_by_url, Mapping):
        raise ValueError("fix_fingerprints_not_mapping")
    if (
        high_impact_fix_fingerprints_by_url is not None
        and not isinstance(high_impact_fix_fingerprints_by_url, Mapping)
    ):
        raise ValueError("high_impact_fix_fingerprints_not_mapping")

    _require_manifest_integrity(manifest, manifest_integrity)
    tranches = _validated_tranches(manifest)

    rows: list[dict[str, Any]] = []
    previous_fixes: set[str] = set()
    previous_high: set[str] = set()
    previous_pages = 0

    for tranche in tranches:
        selected = tranche["selected_urls"]
        current_fixes = _strict_fix_set(
            selected,
            fix_fingerprints_by_url,
            field="fix_fingerprints",
        )
        pages_assessed = len(selected)
        pages_added = pages_assessed - previous_pages
        if pages_added < 0:
            raise ValueError("tranche_page_count_regressed")

        new_fixes = current_fixes - previous_fixes
        if high_impact_fix_fingerprints_by_url is None:
            current_high: set[str] = set()
            new_high_count: int | None = None
            cumulative_high_count: int | None = None
            high_yield: float | None = None
            high_state = "not_observed"
        else:
            current_high = _strict_fix_set(
                selected,
                high_impact_fix_fingerprints_by_url,
                field="high_impact_fix_fingerprints",
            )
            if not current_high.issubset(current_fixes):
                raise ValueError("high_impact_fix_not_in_fix_population")
            new_high = current_high - previous_high
            new_high_count = len(new_high)
            cumulative_high_count = len(current_high)
            high_yield = _per_100(new_high_count, pages_added)
            high_state = "observed"

        rows.append(
            {
                "target": tranche["target"],
                "pages_assessed": pages_assessed,
                "pages_added": pages_added,
                "selected_population_fingerprint": tranche[
                    "selected_population_fingerprint"
                ],
                "added_population_fingerprint": tranche[
                    "added_population_fingerprint"
                ],
                "new_fix_fingerprints": len(new_fixes),
                "new_fix_yield_per_100": _per_100(len(new_fixes), pages_added),
                "cumulative_fix_fingerprints": len(current_fixes),
                "new_high_impact_fix_fingerprints": new_high_count,
                "new_high_impact_fix_yield_per_100": high_yield,
                "cumulative_high_impact_fix_fingerprints": cumulative_high_count,
                "high_impact_evidence_state": high_state,
                "state": "observed" if pages_added > 0 else "no_incremental_pages",
            }
        )
        previous_pages = pages_assessed
        previous_fixes = current_fixes
        previous_high = current_high

    result = {
        "version": ADAPTIVE_FIX_YIELD_VERSION,
        "manifest_input_population_fingerprint": manifest.get(
            "input_population_fingerprint"
        ),
        "selection_targets": tuple(manifest.get("selection_targets") or ()),
        "standard_reference_target": manifest.get("standard_reference_target"),
        "standard_reference_population_fingerprint": manifest.get(
            "standard_reference_population_fingerprint"
        ),
        "standard_150_preserved": bool(
            tranches
            and tranches[0]["target"] <= STANDARD_150_TARGET
            and tranches[0]["selected_population_fingerprint"]
            == manifest.get("standard_reference_population_fingerprint")
        ),
        "high_impact_evidence_state": (
            "observed"
            if high_impact_fix_fingerprints_by_url is not None
            else "not_observed"
        ),
        "tranches": tuple(rows),
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }
    result["binding_fingerprint"] = _fingerprint_json(
        result,
        domain=ADAPTIVE_FIX_YIELD_VERSION,
    )
    return result


def validate_manifest_bound_fix_yield(
    result: Mapping[str, Any] | Any,
    manifest: Mapping[str, Any],
    manifest_integrity: Mapping[str, Any],
    *,
    fix_fingerprints_by_url: Mapping[str, Iterable[str]],
    high_impact_fix_fingerprints_by_url: Mapping[str, Iterable[str]] | None = None,
) -> dict[str, Any]:
    """Recompute the artifact and fail closed on transport or arithmetic drift."""
    if not isinstance(result, Mapping):
        return {
            "version": ADAPTIVE_FIX_YIELD_INTEGRITY_VERSION,
            "valid": False,
            "errors": ("result_not_mapping",),
        }
    try:
        expected = build_manifest_bound_fix_yield(
            manifest,
            manifest_integrity,
            fix_fingerprints_by_url=fix_fingerprints_by_url,
            high_impact_fix_fingerprints_by_url=high_impact_fix_fingerprints_by_url,
        )
    except (TypeError, ValueError) as exc:
        return {
            "version": ADAPTIVE_FIX_YIELD_INTEGRITY_VERSION,
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
        "version": ADAPTIVE_FIX_YIELD_INTEGRITY_VERSION,
        "valid": not errors,
        "errors": tuple(dict.fromkeys(errors)),
        "binding_fingerprint": expected["binding_fingerprint"],
        "standard_150_preserved": expected["standard_150_preserved"],
    }
