from __future__ import annotations

from typing import Any

from .repair_identity import REPAIR_VERIFICATION_VERSION
from .scan_comparison import (
    SCAN_COMPARISON_VERSION,
    build_customer_scan_comparison_presentation,
    build_scan_comparison_transport_v1,
)

SCAN_COMPARISON_INTEGRITY_VERSION = "scan_comparison_integrity_v1"

_COMPARATOR_STATES = frozenset({"verified_fixed", "still_detected", "came_back", "could_not_verify"})
_SUMMARY_STATES = frozenset({"fixed", "still_detected", "came_back", "could_not_verify"})
_REFERENCE_SOURCES = frozenset({"persisted_repair_fingerprint", "computed_repair_identity"})
_VERIFIED_FIXED_CONTRACT_STATES = frozenset({"compatible", "legacy_compatible"})


def _exact_scan_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > 256:
        raise ValueError(f"{field} must be an exact non-empty scan ID")
    return value


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _finite_score(value: Any, field: str) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric or null")
    if value != value or value in {float("inf"), float("-inf")}:
        raise ValueError(f"{field} must be finite")
    return value


def _exact_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    return value


def _fingerprint(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if allow_empty and value == "":
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a fingerprint string")
    if value != value.strip() or value != value.lower():
        raise ValueError(f"{field} must use canonical lowercase fingerprint form")
    if len(value) != 24 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{field} must be a 24-character lowercase hex fingerprint")
    return value


def _finding_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or value != value.strip() or len(value) > 512:
        raise ValueError(f"{field} must be a canonical finding ID string")
    return value


def validate_scan_comparison_v1(comparison: dict[str, Any]) -> dict[str, Any]:
    """Fail closed on contradictions in a serialized ``scan_comparison_v1``.

    This is an integrity/read contract, not a repair comparison engine. It never
    decides whether a repair is fixed. The only producer of repair states remains
    ``repair_identity.compare_repair_runs()`` through ``build_scan_comparison_v1``.
    The validator exists so a stored/tampered summary cannot become customer copy
    or a V8 transport candidate merely because it still carries the v1 version.
    """
    if not isinstance(comparison, dict) or comparison.get("version") != SCAN_COMPARISON_VERSION:
        raise ValueError("unsupported scan comparison contract")

    previous_scan_id = _exact_scan_id(comparison.get("previous_scan_id"), "previous_scan_id")
    current_scan_id = _exact_scan_id(comparison.get("current_scan_id"), "current_scan_id")
    current_previous_scan_id = _exact_scan_id(
        comparison.get("current_previous_scan_id"),
        "current_previous_scan_id",
    )
    if current_scan_id == previous_scan_id:
        raise ValueError("current_scan_id must differ from previous_scan_id")
    if current_previous_scan_id != previous_scan_id:
        raise ValueError("current scan lineage does not point to the supplied previous scan")

    rows = comparison.get("repair_comparisons")
    if not isinstance(rows, list):
        raise ValueError("repair_comparisons must be a list")

    expected_counts = {
        "fixed": 0,
        "still_detected": 0,
        "came_back": 0,
        "could_not_verify": 0,
    }
    expected_previous_without_reference = 0
    expected_previous_stable_identity = 0
    previous_fingerprints: set[str] = set()
    sort_keys: list[tuple[str, str, str]] = []
    row_continuity: list[tuple[str, bool, str, str]] = []

    for index, row in enumerate(rows):
        field = f"repair_comparisons[{index}]"
        if not isinstance(row, dict):
            raise ValueError(f"{field} must be an object")

        fingerprint = _fingerprint(
            row.get("repair_fingerprint"),
            f"{field}.repair_fingerprint",
            allow_empty=True,
        )
        source = row.get("repair_fingerprint_source")
        if source not in _REFERENCE_SOURCES:
            raise ValueError(f"{field}.repair_fingerprint_source is unsupported")
        stable = _exact_bool(row.get("repair_identity_stable"), f"{field}.repair_identity_stable")
        if stable and not fingerprint:
            raise ValueError(f"{field} cannot mark an empty repair fingerprint stable")
        if source == "persisted_repair_fingerprint" and not fingerprint:
            raise ValueError(f"{field} cannot claim a persisted fingerprint without one")
        if not fingerprint:
            expected_previous_without_reference += 1
        if stable:
            expected_previous_stable_identity += 1
        same_reference_observed = _exact_bool(
            row.get("same_reference_fingerprint_observed"),
            f"{field}.same_reference_fingerprint_observed",
        )

        previous_finding_id = row.get("previous_finding_id")
        current_finding_id = row.get("current_finding_id")
        if not isinstance(previous_finding_id, str) or not isinstance(current_finding_id, str):
            raise ValueError(f"{field} finding IDs must be strings")
        if current_finding_id and not same_reference_observed:
            raise ValueError(f"{field} cannot name a current finding without observing the same reference fingerprint")

        state = row.get("state")
        if state not in _COMPARATOR_STATES:
            raise ValueError(f"{field}.state is unsupported")
        summary_state = row.get("summary_state")
        expected_summary_state = "fixed" if state == "verified_fixed" else state
        if summary_state != expected_summary_state or summary_state not in _SUMMARY_STATES:
            raise ValueError(f"{field}.summary_state contradicts comparator state")

        # Positive cross-scan states are emitted by the canonical comparator only
        # from a stable historical technical identity. Persisted fingerprints are
        # useful continuity references, but never authority on their own.
        if state in {"verified_fixed", "still_detected", "came_back"} and not stable:
            raise ValueError(f"{field}.{state} requires a stable historical repair identity")
        if state == "verified_fixed" and same_reference_observed:
            raise ValueError(f"{field}.verified_fixed contradicts a same-fingerprint observation in the current scan")
        if state in {"still_detected", "came_back"} and not same_reference_observed:
            raise ValueError(f"{field}.{state} requires the same stable repair fingerprint in the current scan")

        expected_counts[summary_state] += 1

        previous_affected_pages = _nonnegative_int(
            row.get("previous_affected_pages"),
            f"{field}.previous_affected_pages",
        )
        rechecked_pages = _nonnegative_int(row.get("rechecked_pages"), f"{field}.rechecked_pages")
        eligible_rechecked_pages = _nonnegative_int(
            row.get("eligible_rechecked_pages"),
            f"{field}.eligible_rechecked_pages",
        )
        if rechecked_pages > previous_affected_pages or eligible_rechecked_pages > rechecked_pages:
            raise ValueError(f"{field} page verification accounting is contradictory")

        reason = row.get("reason")
        verification_version = row.get("verification_version")
        comparison_contract_state = row.get("comparison_contract_state")
        if not isinstance(reason, str) or not isinstance(verification_version, str) or not isinstance(comparison_contract_state, str):
            raise ValueError(f"{field} reason/version/contract state must be strings")
        if verification_version != REPAIR_VERIFICATION_VERSION:
            raise ValueError(f"{field}.verification_version is not the canonical repair verification version")

        if state == "verified_fixed":
            if previous_affected_pages <= 0:
                raise ValueError(f"{field}.verified_fixed requires at least one previously affected page")
            if rechecked_pages != previous_affected_pages or eligible_rechecked_pages != previous_affected_pages:
                raise ValueError(f"{field}.verified_fixed requires every previously affected page to be rechecked and eligible")
            if comparison_contract_state not in _VERIFIED_FIXED_CONTRACT_STATES:
                raise ValueError(f"{field}.verified_fixed requires a compatible comparison contract")
        elif state in {"still_detected", "came_back"} and eligible_rechecked_pages != 0:
            raise ValueError(f"{field}.{state} cannot claim page-level fixed verification evidence")

        if fingerprint:
            previous_fingerprints.add(fingerprint)
        sort_keys.append((fingerprint or "~", previous_finding_id, summary_state))
        row_continuity.append((fingerprint, same_reference_observed, current_finding_id, field))

    if sort_keys != sorted(sort_keys):
        raise ValueError("repair_comparisons are not in deterministic v1 order")

    current_references = comparison.get("current_repair_references")
    if not isinstance(current_references, list):
        raise ValueError("current_repair_references must be a list")
    expected_current_without_reference = 0
    expected_current_stable_identity = 0
    current_fingerprints: set[str] = set()
    current_finding_ids_by_fingerprint: dict[str, list[str]] = {}
    current_sort_keys: list[tuple[str, str, str, bool]] = []
    for index, reference in enumerate(current_references):
        field = f"current_repair_references[{index}]"
        if not isinstance(reference, dict):
            raise ValueError(f"{field} must be an object")
        fingerprint = _fingerprint(
            reference.get("repair_fingerprint"),
            f"{field}.repair_fingerprint",
            allow_empty=True,
        )
        source = reference.get("repair_fingerprint_source")
        if source not in _REFERENCE_SOURCES:
            raise ValueError(f"{field}.repair_fingerprint_source is unsupported")
        stable = _exact_bool(reference.get("repair_identity_stable"), f"{field}.repair_identity_stable")
        finding_id = _finding_id(reference.get("finding_id"), f"{field}.finding_id")
        if stable and not fingerprint:
            raise ValueError(f"{field} cannot mark an empty repair fingerprint stable")
        if source == "persisted_repair_fingerprint" and not fingerprint:
            raise ValueError(f"{field} cannot claim a persisted fingerprint without one")
        if source == "computed_repair_identity" and fingerprint and not stable:
            raise ValueError(f"{field} cannot expose a provisional computed fingerprint as a reference")
        if not fingerprint:
            expected_current_without_reference += 1
        else:
            current_fingerprints.add(fingerprint)
            current_finding_ids_by_fingerprint.setdefault(fingerprint, []).append(finding_id)
        if stable:
            expected_current_stable_identity += 1
        current_sort_keys.append((fingerprint or "~", finding_id, source, stable))

    if current_sort_keys != sorted(current_sort_keys):
        raise ValueError("current_repair_references are not in deterministic v1 order")
    for finding_ids in current_finding_ids_by_fingerprint.values():
        finding_ids.sort()

    for fingerprint, observed, current_finding_id, field in row_continuity:
        expected_observed = bool(fingerprint and fingerprint in current_fingerprints)
        if observed != expected_observed:
            raise ValueError(f"{field}.same_reference_fingerprint_observed contradicts current repair references")
        expected_current_finding_id = (
            current_finding_ids_by_fingerprint[fingerprint][0]
            if expected_observed
            else ""
        )
        if current_finding_id != expected_current_finding_id:
            raise ValueError(f"{field}.current_finding_id contradicts current repair references")

    summary = comparison.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("summary must be an object")
    for state, expected in expected_counts.items():
        actual = _nonnegative_int(summary.get(state), f"summary.{state}")
        if actual != expected:
            raise ValueError(f"summary.{state} does not match repair comparisons")

    summary_fields = (
        "previous_repairs_total",
        "current_repairs_total",
        "previous_repairs_without_reference_fingerprint",
        "current_repairs_without_reference_fingerprint",
        "previous_repairs_with_stable_verification_identity",
        "current_repairs_with_stable_verification_identity",
    )
    values = {name: _nonnegative_int(summary.get(name), f"summary.{name}") for name in summary_fields}
    if values["previous_repairs_total"] != len(rows):
        raise ValueError("summary.previous_repairs_total does not match repair comparisons")
    if values["current_repairs_total"] != len(current_references):
        raise ValueError("summary.current_repairs_total does not match current repair references")
    if values["previous_repairs_without_reference_fingerprint"] != expected_previous_without_reference:
        raise ValueError("summary.previous_repairs_without_reference_fingerprint does not match repair comparisons")
    if values["current_repairs_without_reference_fingerprint"] != expected_current_without_reference:
        raise ValueError("summary.current_repairs_without_reference_fingerprint does not match current repair references")
    if values["previous_repairs_with_stable_verification_identity"] != expected_previous_stable_identity:
        raise ValueError("summary.previous_repairs_with_stable_verification_identity does not match repair comparisons")
    if values["current_repairs_with_stable_verification_identity"] != expected_current_stable_identity:
        raise ValueError("summary.current_repairs_with_stable_verification_identity does not match current repair references")
    for population in ("previous", "current"):
        total = values[f"{population}_repairs_total"]
        without_reference = values[f"{population}_repairs_without_reference_fingerprint"]
        stable = values[f"{population}_repairs_with_stable_verification_identity"]
        if without_reference > total or stable > total or without_reference + stable > total:
            raise ValueError(f"{population} repair identity accounting is contradictory")

    candidates = comparison.get("new_or_came_back_repair_fingerprints")
    if not isinstance(candidates, list):
        raise ValueError("new_or_came_back_repair_fingerprints must be a list")
    canonical_candidates = [
        _fingerprint(value, f"new_or_came_back_repair_fingerprints[{index}]")
        for index, value in enumerate(candidates)
    ]
    if canonical_candidates != sorted(set(canonical_candidates)):
        raise ValueError("new-or-came-back candidate fingerprints must be unique and deterministic")
    expected_candidates = sorted(current_fingerprints - previous_fingerprints)
    if canonical_candidates != expected_candidates:
        raise ValueError("new-or-came-back candidate fingerprints contradict current repair references")
    if comparison.get("new_or_came_back_candidate_only") is not True:
        raise ValueError("new_or_came_back_candidate_only must remain true")
    expected_new_or_came_back = len(canonical_candidates) + expected_counts["came_back"]
    if _nonnegative_int(summary.get("new_or_came_back"), "summary.new_or_came_back") != expected_new_or_came_back:
        raise ValueError("summary.new_or_came_back contradicts candidate/came-back evidence")

    context = comparison.get("score_sample_context")
    if not isinstance(context, dict):
        raise ValueError("score_sample_context must be an object")
    previous_score = _finite_score(context.get("previous_score"), "score_sample_context.previous_score")
    current_score = _finite_score(context.get("current_score"), "score_sample_context.current_score")
    previous_pages = _nonnegative_int(context.get("previous_pages_checked"), "score_sample_context.previous_pages_checked")
    current_pages = _nonnegative_int(context.get("current_pages_checked"), "score_sample_context.current_pages_checked")
    expected_sample_changed = previous_pages != current_pages
    if _exact_bool(context.get("sample_size_changed"), "score_sample_context.sample_size_changed") != expected_sample_changed:
        raise ValueError("score sample-size flag contradicts page counts")

    expected_delta = None if previous_score is None or current_score is None else current_score - previous_score
    actual_delta = context.get("score_delta")
    if expected_delta is None:
        if actual_delta is not None:
            raise ValueError("score delta must be null when either score is unavailable")
    elif _finite_score(actual_delta, "score_sample_context.score_delta") != expected_delta:
        raise ValueError("score delta contradicts source scores")

    if context.get("score_direction_claim_allowed") is not False:
        raise ValueError("score direction claims are not authorized by scan_comparison_v1")
    expected_context_state = (
        "sample_size_changed_do_not_infer_direction"
        if expected_sample_changed
        else "score_delta_descriptive_only"
    )
    if context.get("score_context_state") != expected_context_state:
        raise ValueError("score context state contradicts sample evidence")

    if comparison.get("comparison_engine") != "repair_identity.compare_repair_runs":
        raise ValueError("scan comparison must use the canonical repair comparator")
    for field in ("creates_customer_fixes", "recomputes_score", "mutates_historical_rows"):
        if comparison.get(field) is not False:
            raise ValueError(f"{field} must remain false")

    return comparison


def build_validated_customer_scan_comparison_presentation(comparison: dict[str, Any]) -> dict[str, Any]:
    validate_scan_comparison_v1(comparison)
    return build_customer_scan_comparison_presentation(comparison)


def build_validated_scan_comparison_transport_v1(
    comparison: dict[str, Any],
    *,
    previous_authority_receipt: dict[str, Any],
    current_authority_receipt: dict[str, Any],
) -> dict[str, Any]:
    validate_scan_comparison_v1(comparison)
    return build_scan_comparison_transport_v1(
        comparison,
        previous_authority_receipt=previous_authority_receipt,
        current_authority_receipt=current_authority_receipt,
    )
