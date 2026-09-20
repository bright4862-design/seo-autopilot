"""Stage 3 decision-delivery contracts for honest counts, previews, score caps and handoff v2.

This module is intentionally pure and side-effect free. It does not write authority,
persistence or customer projections. Those shared integration surfaces stay with the
serialized integrator after Stage 2 is complete.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable


HANDOFF_V2 = "fixlist_handoff_v2"
DEFAULT_PRESENTATION_LIMIT = 36
DEFAULT_SAMPLE_LIMIT = 10
SAFE_SUFFICIENT_COVERAGE_QUALIFICATION = "Coverage was sufficient for the assessed scan scope."


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result


def _unique_strings(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _affected_page_union(candidate: dict[str, Any]) -> list[str]:
    """Build the exact evidence-identity union without URL normalization.

    The producer/review layer owns URL identity semantics. Stage 3 must not lower-case,
    strip slashes, remove queries or otherwise collapse distinct published evidence.
    """
    values: list[Any] = []
    values.extend(_list(candidate.get("affected_pages")))
    for group in _list(candidate.get("groups")):
        if isinstance(group, dict):
            values.extend(_list(group.get("affected_pages")))
    for observation in _list(candidate.get("observations")):
        if isinstance(observation, dict):
            values.append(observation.get("observed_url"))
    return _unique_strings(values)


def summarize_candidate_counts(
    candidate: dict[str, Any],
    *,
    sample_limit: int = DEFAULT_SAMPLE_LIMIT,
) -> dict[str, Any]:
    """Return honest affected-page/observation/population counts.

    Exact unions are computed before display sampling. A missing known population stays
    ``None`` instead of being inferred from observed pages.
    """
    candidate = _dict(candidate)
    sample_limit = max(0, int(sample_limit))
    affected_pages = _affected_page_union(candidate)

    explicit_observations = _nonnegative_int(candidate.get("observation_count"))
    if explicit_observations is None:
        observations = _list(candidate.get("observations"))
        explicit_observations = len(observations)

    known_population = _nonnegative_int(candidate.get("known_population_count"))
    displayed = affected_pages[:sample_limit]

    return {
        "unique_affected_page_count": len(affected_pages),
        "observation_count": explicit_observations,
        "known_population_count": known_population,
        "displayed_sample_count": len(displayed),
        "displayed_samples": displayed,
        "examples_partial": len(displayed) < len(affected_pages),
        "truncated_sample_count": max(0, len(affected_pages) - len(displayed)),
    }


def _candidate_priority(candidate: dict[str, Any]) -> tuple[int, float, float, str]:
    """Consume Python-owned ranking output without converting unknown scores to zero.

    B19 owns the ranking model. A numeric rank or score is a known sortable value.
    An explicitly present but non-numeric ``priority_score`` is an unknown B19 score
    and is deferred behind every known-score candidate; impact must not substitute for
    that missing composite. Rows from older callers that provide neither rank nor score
    retain deterministic legacy fallback ordering, but the B21 integration always
    supplies ``priority_score`` explicitly so its unknown state fails closed here.
    """
    impact = _number(candidate.get("impact")) or 0.0
    rule_id = str(candidate.get("rule_id") or candidate.get("id") or "")

    primary_rank = _number(candidate.get("priority_rank"))
    if primary_rank is not None:
        return 2, primary_rank, impact, rule_id

    if "priority_score" in candidate:
        priority_score = _number(candidate.get("priority_score"))
        if priority_score is None:
            return 0, 0.0, 0.0, rule_id
        return 2, priority_score, impact, rule_id

    return 1, 0.0, impact, rule_id


def prepare_ranked_candidates(
    candidates: Iterable[dict[str, Any]],
    *,
    presentation_limit: int = DEFAULT_PRESENTATION_LIMIT,
    sample_limit: int = DEFAULT_SAMPLE_LIMIT,
) -> dict[str, Any]:
    """Rank all eligible candidates before applying the presentation cap."""
    presentation_limit = max(0, int(presentation_limit))
    rows: list[dict[str, Any]] = []
    for original_index, raw in enumerate(candidates):
        if not isinstance(raw, dict):
            continue
        if raw.get("eligible") is False:
            continue
        row = deepcopy(raw)
        row["counts"] = summarize_candidate_counts(row, sample_limit=sample_limit)
        row["_original_index"] = original_index
        rows.append(row)

    rows.sort(
        key=lambda row: (
            -_candidate_priority(row)[0],
            -_candidate_priority(row)[1],
            -_candidate_priority(row)[2],
            _candidate_priority(row)[3],
            row["_original_index"],
        )
    )
    for row in rows:
        row.pop("_original_index", None)

    displayed = rows[:presentation_limit]
    return {
        "eligible_candidate_count": len(rows),
        "displayed_candidate_count": len(displayed),
        "presentation_truncated": len(displayed) < len(rows),
        "presentation_omitted_count": max(0, len(rows) - len(displayed)),
        "displayed_candidates": displayed,
    }


def _preview_eligible(
    candidate: dict[str, Any],
    *,
    requested_scan_id: str,
    requested_owner_id: str,
) -> bool:
    return bool(
        candidate.get("authority_verified") is True
        and candidate.get("preview_allowed") is True
        and candidate.get("evidence_state") == "verified"
        and candidate.get("scan_id") == requested_scan_id
        and candidate.get("owner_id") == requested_owner_id
    )


def _preview_projection(candidate: dict[str, Any]) -> dict[str, Any]:
    """Strict whitelist: never project raw findings or hidden evidence collections."""
    return {
        "rule_id": candidate.get("rule_id"),
        "title": candidate.get("title"),
        "impact": _nonnegative_int(candidate.get("impact")) or 0,
        "evidence_summary": candidate.get("evidence_summary"),
    }


def _safe_preview_coverage_qualification(value: Any) -> tuple[str, str | None]:
    """Return only a fixed customer-safe qualification for an explicit sufficient state."""
    qualification = _dict(value)
    raw_state = qualification.get("state")
    state = raw_state.strip().lower() if isinstance(raw_state, str) else ""
    text = SAFE_SUFFICIENT_COVERAGE_QUALIFICATION if state == "sufficient" else None
    return state, text


def _preview_priority_value(candidate: dict[str, Any]) -> float:
    """Preserve an exact numeric zero when ranking preview candidates."""
    priority_rank = _number(candidate.get("priority_rank"))
    if priority_rank is not None:
        return priority_rank
    priority_score = _number(candidate.get("priority_score"))
    return priority_score if priority_score is not None else 0.0


def select_evidence_led_preview(
    candidates: Iterable[dict[str, Any]],
    *,
    max_items: int = 2,
    coverage_qualification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Select a bounded verified preview from an already-authenticated candidate set.

    This helper intentionally performs no owner or entitlement decision. Callers at an
    authority boundary may use it to sign the evidence-led selection source, while the
    customer-facing ``select_private_preview`` keeps the stricter scan/owner checks.
    Only explicitly preview-allowed, individually verified candidates participate.
    """
    qualification_state, qualification_text = _safe_preview_coverage_qualification(coverage_qualification)

    eligible = [
        raw
        for raw in candidates
        if isinstance(raw, dict)
        and raw.get("preview_allowed") is True
        and raw.get("evidence_state") == "verified"
    ]
    eligible.sort(
        key=lambda item: (
            -int((_nonnegative_int(item.get("impact")) or 0) >= 4),
            -(_nonnegative_int(item.get("impact")) or 0),
            -_preview_priority_value(item),
            str(item.get("rule_id") or ""),
        )
    )

    max_items = max(0, int(max_items))
    if eligible and max_items:
        high_impact = [item for item in eligible if (_nonnegative_int(item.get("impact")) or 0) >= 4]
        selected = high_impact[:max_items] if high_impact else eligible[:1]
        return {
            "state": "findings",
            "findings": [_preview_projection(item) for item in selected],
            "coverage_qualification": qualification_text,
        }

    if qualification_state == "sufficient" and qualification_text:
        return {
            "state": "good_shape",
            "findings": [],
            "coverage_qualification": qualification_text,
        }

    return {
        "state": "not_available",
        "findings": [],
        "coverage_qualification": qualification_text,
    }


def select_private_preview(
    candidates: Iterable[dict[str, Any]],
    *,
    authority_verified: bool,
    requested_scan_id: str,
    requested_owner_id: str,
    max_items: int = 2,
    coverage_qualification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Select an evidence-led preview without exposing hidden findings.

    Individually verified impact-4/5 findings come first. If none exist, the best
    remaining verified finding is eligible. A good-shape message requires an explicit
    sufficient-coverage qualification.
    """
    _qualification_state, qualification_text = _safe_preview_coverage_qualification(coverage_qualification)

    if authority_verified is not True:
        return {
            "state": "not_available",
            "findings": [],
            "coverage_qualification": qualification_text,
        }

    eligible: list[dict[str, Any]] = []
    for raw in candidates:
        if not isinstance(raw, dict):
            continue
        if _preview_eligible(
            raw,
            requested_scan_id=requested_scan_id,
            requested_owner_id=requested_owner_id,
        ):
            eligible.append(raw)

    return select_evidence_led_preview(
        eligible,
        max_items=max_items,
        coverage_qualification=coverage_qualification,
    )


def _valid_score_cap(value: Any) -> int | None:
    number = _nonnegative_int(value)
    if number is None or number > 100:
        return None
    return number


def apply_root_cause_score_caps(
    base_health_score: int,
    root_causes: Iterable[dict[str, Any]],
    *,
    existing_score_ceiling: int | None = None,
    coverage_state: str = "sufficient",
) -> dict[str, Any]:
    """Apply only explicit caps from verified root causes.

    This function never creates a penalty for unknown/unverified evidence. Existing
    access/sample/incomplete ceilings are accepted as input and preserved independently
    of Stage-3 root-cause caps.
    """
    base = min(100, max(0, int(base_health_score)))
    existing = _valid_score_cap(existing_score_ceiling)
    applied: list[dict[str, Any]] = []
    ignored: list[dict[str, Any]] = []
    seen_root_causes: set[str] = set()

    for raw in root_causes:
        if not isinstance(raw, dict):
            continue
        root_cause_id = raw.get("root_cause_id")
        cap = _valid_score_cap(raw.get("score_cap"))
        verified = raw.get("verification_state") == "verified"
        reason = None
        if not isinstance(root_cause_id, str) or not root_cause_id:
            reason = "missing_root_cause_id"
        elif root_cause_id in seen_root_causes:
            reason = "duplicate_root_cause"
        elif not verified:
            reason = "root_cause_not_verified"
        elif cap is None:
            reason = "missing_or_invalid_explicit_cap"

        if reason is not None:
            ignored.append({
                "root_cause_id": root_cause_id,
                "score_cap": cap,
                "reason": reason,
            })
            continue

        seen_root_causes.add(root_cause_id)
        applied.append({"root_cause_id": root_cause_id, "score_cap": cap})

    root_ceiling = min((row["score_cap"] for row in applied), default=None)
    ceilings = [value for value in (existing, root_ceiling) if value is not None]
    effective = min(ceilings) if ceilings else None
    adjusted = min(base, effective) if effective is not None else base

    return {
        "base_health_score": base,
        "coverage_state": coverage_state,
        "existing_score_ceiling": existing,
        "root_cause_score_ceiling": root_ceiling,
        "effective_score_ceiling": effective,
        "adjusted_health_score": adjusted,
        "applied_root_cause_caps": applied,
        "ignored_root_cause_caps": ignored,
    }


def _handoff_fix(candidate: dict[str, Any], *, sample_limit: int) -> dict[str, Any]:
    counts = summarize_candidate_counts(candidate, sample_limit=sample_limit)
    output = {
        "rule_id": candidate.get("rule_id"),
        "title": candidate.get("title"),
        "root_cause_id": candidate.get("root_cause_id"),
        "family_ids": _unique_strings(_list(candidate.get("family_ids"))),
        "url_provenance": {
            "published_url": candidate.get("published_url"),
            "request_url": candidate.get("request_url"),
            "final_url": candidate.get("final_url"),
        },
        "counts": {
            "unique_affected_pages": counts["unique_affected_page_count"],
            "observations": counts["observation_count"],
            "known_population": counts["known_population_count"],
            "displayed_examples": counts["displayed_sample_count"],
        },
        "examples": counts["displayed_samples"],
        "examples_partial": counts["examples_partial"],
        "priority_factors": deepcopy(_dict(candidate.get("priority_factors"))),
        "evidence_refs": _unique_strings(_list(candidate.get("evidence_refs"))),
        "verification_steps": [
            value for value in _list(candidate.get("verification_steps")) if isinstance(value, str) and value
        ],
        "dependency": candidate.get("dependency"),
        "vendor_owner": candidate.get("vendor_owner"),
    }
    return output


def build_handoff_v2(
    *,
    scan_identity: dict[str, Any],
    fixes: Iterable[dict[str, Any]],
    user_agent: str,
    suppressed_findings: Iterable[dict[str, Any]] | None = None,
    operator_authorized: bool = False,
    sample_limit: int = DEFAULT_SAMPLE_LIMIT,
) -> dict[str, Any]:
    """Build a new v2 handoff without changing legacy v1 serialization."""
    payload: dict[str, Any] = {
        "handoff_version": HANDOFF_V2,
        "scan": deepcopy(_dict(scan_identity)),
        "user_agent": user_agent,
        "fixes": [
            _handoff_fix(item, sample_limit=sample_limit)
            for item in fixes
            if isinstance(item, dict)
        ],
    }
    payload["fix_count"] = len(payload["fixes"])
    if operator_authorized:
        payload["suppressed_findings"] = [
            deepcopy(item) for item in (suppressed_findings or []) if isinstance(item, dict)
        ]
    return payload


def read_handoff_compatible(payload: dict[str, Any]) -> dict[str, Any]:
    """Read v2 and legacy v1 while leaving historical payload shape untouched.

    Missing version is the existing v1 contract. Unknown explicit versions fail closed.
    """
    if not isinstance(payload, dict):
        raise ValueError("handoff must be an object")
    version = payload.get("handoff_version")
    if version is None or version in {"v1", "fixlist_handoff_v1"}:
        return deepcopy(payload)
    if version != HANDOFF_V2:
        raise ValueError(f"unsupported handoff version: {version}")
    if not isinstance(payload.get("fixes"), list):
        raise ValueError("handoff v2 fixes must be a list")
    return deepcopy(payload)
