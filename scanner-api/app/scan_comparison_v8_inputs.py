from __future__ import annotations

from copy import deepcopy
from math import isfinite
from typing import Any

from .scan_comparison import build_scan_comparison_v1
from .scan_comparison_integrity import (
    build_validated_scan_comparison_transport_v1,
    validate_scan_comparison_v1,
)

SCAN_COMPARISON_V8_INPUT_BINDING_VERSION = "scan_comparison_v8_input_binding_v1"


def _exact_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > 256:
        raise ValueError(f"{field} must be an exact non-empty ID")
    return value


def _record_id(record: Any, *, fields: tuple[str, ...], label: str) -> str:
    if not isinstance(record, dict):
        raise ValueError(f"{label} must be an object")
    observed: list[str] = []
    for field in fields:
        value = record.get(field)
        if value in (None, ""):
            continue
        observed.append(_exact_id(value, f"{label}.{field}"))
    if not observed:
        raise ValueError(f"{label} is missing an exact identity")
    if len(set(observed)) != 1:
        raise ValueError(f"{label} identity fields disagree")
    return observed[0]


def _nonnegative_integral(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a non-negative whole number")
    if isinstance(value, float) and (not isfinite(value) or not value.is_integer()):
        raise ValueError(f"{field} must be a non-negative whole number")
    result = int(value)
    if result < 0:
        raise ValueError(f"{field} must be a non-negative whole number")
    return result


def _finite_number(value: Any, field: str) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(float(value)):
        raise ValueError(f"{field} must be finite numeric or null")
    return value


def _bind_fix_population(
    fixes: Any,
    *,
    expected_scan_id: str,
    expected_fix_list_id: str,
    label: str,
) -> list[dict[str, Any]]:
    if not isinstance(fixes, list):
        raise ValueError(f"{label} must be a list")
    bound: list[dict[str, Any]] = []
    for index, fix in enumerate(fixes):
        field = f"{label}[{index}]"
        if not isinstance(fix, dict):
            raise ValueError(f"{field} must be an object")
        scan_run_id = _exact_id(fix.get("scan_run_id"), f"{field}.scan_run_id")
        fix_list_id = _exact_id(fix.get("fix_list_id"), f"{field}.fix_list_id")
        if scan_run_id != expected_scan_id:
            raise ValueError(f"{field}.scan_run_id does not match its bound scan")
        if fix_list_id != expected_fix_list_id:
            raise ValueError(f"{field}.fix_list_id does not match its bound FixList")
        bound.append(deepcopy(fix))
    return bound


def build_v8_bound_scan_comparison_v1(
    *,
    previous_scan: dict[str, Any],
    current_scan: dict[str, Any],
    previous_fix_list: dict[str, Any],
    current_fix_list: dict[str, Any],
    previous_fixes: list[dict[str, Any]],
    current_fixes: list[dict[str, Any]],
    current_pages: list[dict[str, Any]],
    current_contract: dict[str, Any] | None = None,
    previous_scan_origin: str = "",
    current_scan_origin: str = "",
) -> dict[str, Any]:
    """Bind authenticated V8 rows before invoking the canonical comparison contract.

    This helper does not verify V8 authority and does not classify repair states.
    The serialized V8 reader must authenticate the exact rows first. Once the row
    relationships are proven structurally here, repair truth is delegated once to
    :func:`build_scan_comparison_v1`, which in turn delegates every historical
    repair state to ``repair_identity.compare_repair_runs()``.
    """
    previous_scan_copy = deepcopy(previous_scan)
    current_scan_copy = deepcopy(current_scan)
    previous_fix_list_copy = deepcopy(previous_fix_list)
    current_fix_list_copy = deepcopy(current_fix_list)
    current_pages_copy = deepcopy(current_pages)
    current_contract_copy = deepcopy(current_contract)

    previous_scan_id = _record_id(
        previous_scan_copy,
        fields=("id", "scan_id"),
        label="previous_scan",
    )
    current_scan_id = _record_id(
        current_scan_copy,
        fields=("id", "scan_id"),
        label="current_scan",
    )
    if previous_scan_id == current_scan_id:
        raise ValueError("previous and current scan IDs must differ")

    current_previous_scan_id = _exact_id(
        current_scan_copy.get("previous_scan_id"),
        "current_scan.previous_scan_id",
    )
    if current_previous_scan_id != previous_scan_id:
        raise ValueError("current scan lineage does not point to the bound previous scan")

    previous_fix_list_id = _record_id(
        previous_fix_list_copy,
        fields=("id",),
        label="previous_fix_list",
    )
    current_fix_list_id = _record_id(
        current_fix_list_copy,
        fields=("id",),
        label="current_fix_list",
    )
    if previous_fix_list_id == current_fix_list_id:
        raise ValueError("previous and current FixList IDs must differ")

    previous_scan_fix_list_id = _exact_id(previous_scan_copy.get("fix_list_id"), "previous_scan.fix_list_id")
    current_scan_fix_list_id = _exact_id(current_scan_copy.get("fix_list_id"), "current_scan.fix_list_id")
    if previous_scan_fix_list_id != previous_fix_list_id:
        raise ValueError("previous ScanRun does not reference the supplied previous FixList")
    if current_scan_fix_list_id != current_fix_list_id:
        raise ValueError("current ScanRun does not reference the supplied current FixList")

    previous_fix_list_scan_id = _exact_id(previous_fix_list_copy.get("scan_run_id"), "previous_fix_list.scan_run_id")
    current_fix_list_scan_id = _exact_id(current_fix_list_copy.get("scan_run_id"), "current_fix_list.scan_run_id")
    if previous_fix_list_scan_id != previous_scan_id:
        raise ValueError("previous FixList does not belong to the bound previous scan")
    if current_fix_list_scan_id != current_scan_id:
        raise ValueError("current FixList does not belong to the bound current scan")

    bound_previous_fixes = _bind_fix_population(
        previous_fixes,
        expected_scan_id=previous_scan_id,
        expected_fix_list_id=previous_fix_list_id,
        label="previous_fixes",
    )
    bound_current_fixes = _bind_fix_population(
        current_fixes,
        expected_scan_id=current_scan_id,
        expected_fix_list_id=current_fix_list_id,
        label="current_fixes",
    )

    previous_declared_fixes = _nonnegative_integral(previous_fix_list_copy.get("total_fixes"), "previous_fix_list.total_fixes")
    current_declared_fixes = _nonnegative_integral(current_fix_list_copy.get("total_fixes"), "current_fix_list.total_fixes")
    if previous_declared_fixes != len(bound_previous_fixes):
        raise ValueError("previous FixList total_fixes does not match the bound FixItem population")
    if current_declared_fixes != len(bound_current_fixes):
        raise ValueError("current FixList total_fixes does not match the bound FixItem population")

    previous_score = _finite_number(previous_scan_copy.get("health_score"), "previous_scan.health_score")
    current_score = _finite_number(current_scan_copy.get("health_score"), "current_scan.health_score")
    previous_fix_list_score = _finite_number(previous_fix_list_copy.get("health_score"), "previous_fix_list.health_score")
    current_fix_list_score = _finite_number(current_fix_list_copy.get("health_score"), "current_fix_list.health_score")
    if previous_score != previous_fix_list_score:
        raise ValueError("previous ScanRun and FixList health scores disagree")
    if current_score != current_fix_list_score:
        raise ValueError("current ScanRun and FixList health scores disagree")

    previous_pages_checked = _nonnegative_integral(previous_scan_copy.get("pages_retained"), "previous_scan.pages_retained")
    current_pages_checked = _nonnegative_integral(current_scan_copy.get("pages_retained"), "current_scan.pages_retained")

    comparison = build_scan_comparison_v1(
        previous_scan_id=previous_scan_id,
        current_scan_id=current_scan_id,
        current_previous_scan_id=current_previous_scan_id,
        previous_fixes=bound_previous_fixes,
        current_fixes=bound_current_fixes,
        current_pages=current_pages_copy,
        previous_score=previous_score,
        current_score=current_score,
        previous_pages_checked=previous_pages_checked,
        current_pages_checked=current_pages_checked,
        current_contract=current_contract_copy,
        previous_scan_origin=previous_scan_origin,
        current_scan_origin=current_scan_origin,
    )
    validate_scan_comparison_v1(comparison)

    return {
        "version": SCAN_COMPARISON_V8_INPUT_BINDING_VERSION,
        "previous_scan_id": previous_scan_id,
        "current_scan_id": current_scan_id,
        "previous_fix_list_id": previous_fix_list_id,
        "current_fix_list_id": current_fix_list_id,
        "previous_fix_count": len(bound_previous_fixes),
        "current_fix_count": len(bound_current_fixes),
        "score_source": "ScanRun.health_score_bound_to_FixList.health_score",
        "sample_source": "ScanRun.pages_retained",
        "comparison": comparison,
        "requires_upstream_v8_authority_verification": True,
        "authority_verified_by_adapter": False,
        "creates_customer_fixes": False,
        "recomputes_score": False,
        "mutates_historical_rows": False,
    }


def validate_v8_scan_comparison_input_binding_v1(binding: dict[str, Any]) -> dict[str, Any]:
    """Validate a lane-owned V8 binding before presentation/transport handoff."""
    if not isinstance(binding, dict) or binding.get("version") != SCAN_COMPARISON_V8_INPUT_BINDING_VERSION:
        raise ValueError("unsupported V8 scan comparison input binding")

    previous_scan_id = _exact_id(binding.get("previous_scan_id"), "previous_scan_id")
    current_scan_id = _exact_id(binding.get("current_scan_id"), "current_scan_id")
    if previous_scan_id == current_scan_id:
        raise ValueError("previous and current scan IDs must differ")
    _exact_id(binding.get("previous_fix_list_id"), "previous_fix_list_id")
    _exact_id(binding.get("current_fix_list_id"), "current_fix_list_id")
    previous_fix_count = _nonnegative_integral(binding.get("previous_fix_count"), "previous_fix_count")
    current_fix_count = _nonnegative_integral(binding.get("current_fix_count"), "current_fix_count")

    comparison = binding.get("comparison")
    if not isinstance(comparison, dict):
        raise ValueError("binding.comparison must be a scan_comparison_v1 object")
    validate_scan_comparison_v1(comparison)
    if comparison.get("previous_scan_id") != previous_scan_id or comparison.get("current_scan_id") != current_scan_id:
        raise ValueError("binding scan IDs disagree with the validated comparison")
    summary = comparison.get("summary") or {}
    if summary.get("previous_repairs_total") != previous_fix_count:
        raise ValueError("previous_fix_count disagrees with the validated comparison")
    if summary.get("current_repairs_total") != current_fix_count:
        raise ValueError("current_fix_count disagrees with the validated comparison")

    if binding.get("score_source") != "ScanRun.health_score_bound_to_FixList.health_score":
        raise ValueError("unsupported V8 score source")
    if binding.get("sample_source") != "ScanRun.pages_retained":
        raise ValueError("unsupported V8 sample source")
    if binding.get("requires_upstream_v8_authority_verification") is not True:
        raise ValueError("V8 authority verification requirement must remain enabled")
    if binding.get("authority_verified_by_adapter") is not False:
        raise ValueError("the input adapter cannot claim V8 authority verification")
    for field in ("creates_customer_fixes", "recomputes_score", "mutates_historical_rows"):
        if binding.get(field) is not False:
            raise ValueError(f"{field} must remain false")
    return binding


def build_v8_bound_scan_comparison_transport_v1(
    binding: dict[str, Any],
    *,
    previous_authority_receipt: dict[str, Any],
    current_authority_receipt: dict[str, Any],
) -> dict[str, Any]:
    """Transport a V8-bound comparison only after upstream authority receipts exist."""
    validate_v8_scan_comparison_input_binding_v1(binding)
    return build_validated_scan_comparison_transport_v1(
        binding["comparison"],
        previous_authority_receipt=previous_authority_receipt,
        current_authority_receipt=current_authority_receipt,
    )
