"""Pure, shadow-only selection manifest for adaptive crawl tranches.

This module binds the existing adaptive selector to a deterministic 150→500→1000
population manifest. It performs no network I/O, does not mutate crawl budgets, and
cannot authorize production expansion.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from .adaptive_crawl import (
    DEFAULT_TRANCHE_TARGETS,
    MAX_ADAPTIVE_TARGET,
    STANDARD_150_TARGET,
    plan_tranche_targets,
    select_adaptive_urls,
)

ADAPTIVE_TRANCHE_MANIFEST_VERSION = "adaptive_tranche_selection_manifest_v1"
ADAPTIVE_TRANCHE_MANIFEST_INTEGRITY_VERSION = (
    "adaptive_tranche_selection_manifest_integrity_v1"
)


def _strict_discovered_urls(urls: Iterable[str]) -> list[str]:
    raw_urls = list(urls)
    for index, url in enumerate(raw_urls):
        if not isinstance(url, str):
            raise ValueError(f"discovered URL at index {index} must be a string")
        if not url or url != url.strip():
            raise ValueError(
                f"discovered URL at index {index} must be a non-empty exact identity "
                "without surrounding whitespace"
            )
    return raw_urls


def _ordered_unique(urls: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(urls))


def _population_fingerprint(urls: Iterable[str]) -> str:
    payload = json.dumps(
        list(urls),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _selection_targets(plan: Mapping[str, Any], discovered_count: int) -> tuple[int, ...]:
    planner_targets = tuple(int(target) for target in plan.get("targets", ()))
    if not planner_targets:
        return ()

    bound = min(
        max(0, discovered_count),
        max(0, int(plan.get("assessment_ceiling") or 0)),
        MAX_ADAPTIVE_TARGET,
    )
    if bound <= 0:
        return ()
    if bound < STANDARD_150_TARGET:
        return (bound,)

    deeper = [
        target
        for target in planner_targets
        if STANDARD_150_TARGET <= target <= bound
    ]
    return tuple(sorted({STANDARD_150_TARGET, *deeper}))


def _tranche_role(target: int, bound: int) -> str:
    if target <= STANDARD_150_TARGET:
        return "standard_reference"
    if target == 500:
        return "smart_500_candidate"
    if target == 1000:
        return "blind_1000_reference"
    if target == bound and bound < 1000:
        return "inventory_bound"
    return "adaptive_intermediate"


def build_adaptive_tranche_selection_manifest(
    urls: Iterable[str],
    family_of: Callable[[str], str],
    path_of: Callable[[str], str],
    *,
    metadata_by_url: Mapping[str, Mapping[str, Any]] | None = None,
    tranche_targets: Sequence[int] = DEFAULT_TRANCHE_TARGETS,
    ceiling: int = MAX_ADAPTIVE_TARGET,
) -> dict[str, Any]:
    """Build exact, prefix-checked page populations for planned adaptive tranches.

    Standard 150 is always selected by the existing selector. For any tranche at or
    above 150, the next selection must contain the prior selection as an exact prefix.
    A failure raises instead of transporting a misleading marginal population.
    """
    raw_urls = _strict_discovered_urls(urls)
    metadata = metadata_by_url or {}
    planner = plan_tranche_targets(
        len(raw_urls),
        ceiling=ceiling,
        candidate_targets=tranche_targets,
    )
    planner_targets = tuple(int(target) for target in planner.get("targets", ()))
    selection_targets = _selection_targets(planner, len(raw_urls))
    bound = min(
        len(raw_urls),
        max(0, int(planner.get("assessment_ceiling") or 0)),
        MAX_ADAPTIVE_TARGET,
    )

    tranches: list[dict[str, Any]] = []
    previous_selected: tuple[str, ...] = ()
    previous_target: int | None = None
    for target in selection_targets:
        selected = tuple(
            select_adaptive_urls(
                raw_urls,
                family_of,
                path_of,
                target,
                metadata_by_url=metadata,
            )
        )
        if len(selected) > target or len(selected) > MAX_ADAPTIVE_TARGET:
            raise RuntimeError("adaptive selector exceeded the requested tranche bound")

        prefix_checked = previous_target is not None and previous_target >= STANDARD_150_TARGET
        prefix_valid: bool | None = None
        if prefix_checked:
            prefix_valid = selected[: len(previous_selected)] == previous_selected
            if not prefix_valid:
                raise RuntimeError(
                    "adaptive tranche selection is not prefix-stable above Standard 150"
                )

        if previous_target is None:
            added_urls: tuple[str, ...] = selected
        elif prefix_checked:
            added_urls = selected[len(previous_selected) :]
        else:
            previous_set = set(previous_selected)
            added_urls = tuple(url for url in selected if url not in previous_set)

        tranches.append(
            {
                "target": target,
                "role": _tranche_role(target, bound),
                "selected_count": len(selected),
                "selected_urls": selected,
                "selected_population_fingerprint": _population_fingerprint(selected),
                "previous_target": previous_target,
                "prefix_nesting_checked": prefix_checked,
                "prefix_nesting_valid": prefix_valid,
                "added_count": len(added_urls),
                "added_urls": added_urls,
                "added_population_fingerprint": _population_fingerprint(added_urls),
                "inventory_limited": len(selected) < target,
            }
        )
        previous_selected = selected
        previous_target = target

    standard_reference_target = (
        min(STANDARD_150_TARGET, bound) if selection_targets else None
    )
    standard_reference = (
        tuple(
            select_adaptive_urls(
                raw_urls,
                family_of,
                path_of,
                standard_reference_target,
                metadata_by_url=metadata,
            )
        )
        if standard_reference_target is not None
        else ()
    )
    if tranches and tranches[0]["selected_urls"] != standard_reference:
        raise RuntimeError("tranche manifest changed the existing Standard-150 reference")

    return {
        "version": ADAPTIVE_TRANCHE_MANIFEST_VERSION,
        "planner_version": planner.get("version"),
        "discovered_input_count": len(raw_urls),
        "unique_discovered_count": len(_ordered_unique(raw_urls)),
        "input_population_fingerprint": _population_fingerprint(raw_urls),
        "requested_ceiling": planner.get("requested_ceiling"),
        "assessment_ceiling": planner.get("assessment_ceiling"),
        "planner_targets": planner_targets,
        "selection_targets": selection_targets,
        "ignored_pre_standard_targets": tuple(
            target for target in planner_targets if target < STANDARD_150_TARGET
        ),
        "standard_reference_target": standard_reference_target,
        "standard_reference_population_fingerprint": _population_fingerprint(
            standard_reference
        ),
        "tranches": tuple(tranches),
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return tuple(
            (str(key), _canonical(item))
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        )
    if isinstance(value, (list, tuple)):
        return tuple(_canonical(item) for item in value)
    return value


def validate_adaptive_tranche_selection_manifest(
    manifest: Mapping[str, Any],
    urls: Iterable[str],
    family_of: Callable[[str], str],
    path_of: Callable[[str], str],
    *,
    metadata_by_url: Mapping[str, Mapping[str, Any]] | None = None,
    tranche_targets: Sequence[int] = DEFAULT_TRANCHE_TARGETS,
    ceiling: int = MAX_ADAPTIVE_TARGET,
) -> dict[str, Any]:
    """Rebuild the manifest and fail closed on any transported population drift."""
    try:
        expected = build_adaptive_tranche_selection_manifest(
            urls,
            family_of,
            path_of,
            metadata_by_url=metadata_by_url,
            tranche_targets=tranche_targets,
            ceiling=ceiling,
        )
    except (TypeError, ValueError, RuntimeError) as exc:
        return {
            "version": ADAPTIVE_TRANCHE_MANIFEST_INTEGRITY_VERSION,
            "valid": False,
            "errors": ("replay_input_invalid",),
            "detail": str(exc),
        }

    errors: list[str] = []
    for key, expected_value in expected.items():
        if _canonical(manifest.get(key)) != _canonical(expected_value):
            errors.append(f"{key}_mismatch")

    if (
        manifest.get("population_scope_complete") is not False
        or manifest.get("production_budget_authorized") is not False
        or manifest.get("site_fully_understood") is not False
    ):
        errors.append("forbidden_authority_claim")

    return {
        "version": ADAPTIVE_TRANCHE_MANIFEST_INTEGRITY_VERSION,
        "valid": not errors,
        "errors": tuple(dict.fromkeys(errors)),
        "input_population_fingerprint": expected["input_population_fingerprint"],
        "selection_targets": expected["selection_targets"],
        "standard_reference_population_fingerprint": expected[
            "standard_reference_population_fingerprint"
        ],
    }
