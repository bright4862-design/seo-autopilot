"""Production cutover wrapper for the calibrated FixList repair contract.

The crawler and normal Python review remain unchanged. This module runs only in
the durable worker after review has completed. It builds a separate canonical
repair snapshot from the finished review and publishes it only when the existing
complete-or-fail validator accepts every row and the full canonical order.
"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any
from urllib.parse import urlparse

from .observability import emit
from .repair_identity import annotate_repair_identity
from .repair_persistence_shadow import (
    REPAIR_CONTRACT_VERSION,
    REPAIR_PRIORITY_MODEL_VERSION,
    validate_v2_persistence_candidate,
)
from .repair_coverage import (
    first_failed_repair_invariant, normalize_repair_scope,
    repair_evidence_key_function, scan_evidence_origin,
)
from .repair_priority_calibration import annotate_calibrated_repair_priority
from .repair_shadow_calibration import build_calibrated_shadow_review_analysis, sort_calibrated_repairs
from .stage3_priority_factors import annotate_four_factor_priority
from .stage3_root_causes import group_evidenced_root_causes


REPAIR_PERSISTENCE_GROUPING_VERSION = "repair_persistence_grouping_v2_valid_fingerprint_actions"


class CanonicalRepairContractError(RuntimeError):
    """Canonical-v2 synthesis was attempted but could not produce one complete snapshot."""


def _diagnostic_count(value: Any, fallback: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return fallback


def _safe_repair_diagnostic(fix: dict[str, Any], invariant: str, *, rank: int, scan_origin: str = "", identity_version: str = "") -> dict[str, Any]:
    """Return bounded, non-secret fields sufficient to diagnose invariant drift.

    Never emit raw headers, authority material, tokens, or URL query strings.
    The diagnostic intentionally reports cardinalities and family names rather
    than representative URLs.
    """
    identity_context = {"scan_origin": scan_origin, "identity_version": identity_version}
    key_for = repair_evidence_key_function(**identity_context)
    affected_pages = fix.get("affected_pages") if isinstance(fix.get("affected_pages"), list) else []
    affected_keys = {key for value in affected_pages if (key := key_for(value))}
    breakdown = fix.get("family_breakdown") if isinstance(fix.get("family_breakdown"), dict) else {}
    representatives = (
        fix.get("representative_pages_by_family")
        if isinstance(fix.get("representative_pages_by_family"), dict)
        else {}
    )
    page_count = _diagnostic_count(fix.get("page_count"))
    reported = _diagnostic_count(fix.get("affected_reported"), page_count)
    observed = _diagnostic_count(fix.get("affected_observed"), reported)
    eligible = _diagnostic_count(fix.get("affected_eligible"), observed)
    return {
        "invariant": str(invariant or "unknown")[:160],
        "fix_id": str(fix.get("fix_id") or "")[:160],
        "canonical_action_rank": rank,
        "page_scope": str(fix.get("page_scope") or "")[:80],
        "page_count": page_count,
        "affected_page_cardinality": len(affected_keys),
        "affected_pages_complete": fix.get("affected_pages_complete") is not False,
        "family_breakdown": {
            str(key)[:120]: _diagnostic_count(value)
            for key, value in list(breakdown.items())[:20]
        },
        "representative_families": [str(key)[:120] for key in list(representatives.keys())[:20]],
        "affected_reported": reported,
        "affected_observed": observed,
        "affected_eligible": eligible,
        "checked_eligible": fix.get("checked_eligible"),
        "indexable_affected": _diagnostic_count(fix.get("indexable_affected")),
        "indexable_checked_eligible": fix.get("indexable_checked_eligible"),
    }


_ACTION_PRIORITY_WEIGHT = {"fix_first": 4, "important": 3, "improve": 2, "review": 1}
_SEVERITY_WEIGHT = {"critical": 4, "high": 3, "medium": 2, "low": 1}
_EVIDENCE_WEIGHT = {"confirmed_problem": 3, "improvement": 2, "opportunity": 1}
_DIFFICULTY_WEIGHT = {"hard": 4, "difficult": 4, "medium": 3, "moderate": 3, "easy": 2, "quick": 1}
_LOCALE_SEGMENT = re.compile(r"^[a-z]{2}(?:-[a-z]{2})?$", re.I)


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _persistence_repair_fingerprint(item: dict[str, Any]) -> str:
    """Return the scanner-owned action identity used by every customer surface.

    Stability is deliberately not required here. It remains the stricter gate
    for cross-scan `verified_fixed`; requiring it for same-scan persistence made
    canonical FixItems disagree with the customer read model on normal review
    rows that carry a valid provisional fingerprint.
    """
    return _clean_text(item.get("repair_fingerprint"))


def _dedupe_urls(values: Any, *, scan_origin: str = "", identity_version: str = "") -> list[str]:
    identity_context = {"scan_origin": scan_origin, "identity_version": identity_version}
    key_for = repair_evidence_key_function(**identity_context)
    output: list[str] = []
    seen: set[str] = set()
    for value in values if isinstance(values, list) else []:
        raw = _clean_text(value)
        key = key_for(raw)
        if raw and key and key not in seen:
            seen.add(key)
            output.append(raw)
    return output


def _locale_for_urls(values: list[str]) -> str:
    locales: set[str] = set()
    for value in values:
        raw = _clean_text(value)
        try:
            path = urlparse(raw if "://" in raw else f"https://fixlist.invalid{raw if raw.startswith('/') else '/' + raw}").path
        except Exception:
            path = raw
        first = next((part.lower() for part in str(path or "").split("/") if part), "")
        locales.add(first if _LOCALE_SEGMENT.fullmatch(first) else "")
    return next(iter(locales)) if len(locales) == 1 and "" not in locales else ""


def _repair_evidence_group(item: dict[str, Any], *, scan_origin: str = "", identity_version: str = "") -> dict[str, Any]:
    """Preserve one pre-group repair row as bounded child evidence."""
    identity_context = {"scan_origin": scan_origin, "identity_version": identity_version}
    affected = _dedupe_urls(item.get("affected_pages"), **identity_context)
    family = _clean_text(item.get("page_template_family") or item.get("template_family"))
    return {
        "fix_id": _clean_text(item.get("fix_id"))[:160],
        "family": family[:160],
        "locale": _locale_for_urls(affected)[:40],
        "representative_url": (affected[0] if affected else _clean_text(item.get("page_url")))[:2000],
        "affected_urls": affected[:150],
        "count": max(_diagnostic_count(item.get("page_count")), len(affected)),
        "priority": _clean_text(item.get("priority"))[:40],
        "action_priority": _clean_text(item.get("action_priority"))[:80],
        "evidence_class": _clean_text(item.get("evidence_class"))[:80],
        "evidence_status": _clean_text(item.get("evidence_status"))[:120],
        "verification_state": _clean_text(item.get("verification_state"))[:120],
        "repair_verification_state": _clean_text(item.get("repair_verification_state"))[:120],
    }


def _strictest_member(members: list[dict[str, Any]]) -> dict[str, Any]:
    return max(
        members,
        key=lambda item: (
            _ACTION_PRIORITY_WEIGHT.get(_clean_text(item.get("action_priority")).lower(), 0),
            _SEVERITY_WEIGHT.get(_clean_text(item.get("base_severity") or item.get("priority")).lower(), 0),
            _EVIDENCE_WEIGHT.get(_clean_text(item.get("evidence_class")).lower(), 0),
            1 if item.get("requires_developer") is True else 0,
            _DIFFICULTY_WEIGHT.get(_clean_text(item.get("difficulty")).lower(), 0),
        ),
    )


def _merge_repair_group(
    members: list[dict[str, Any]],
    pages: list[dict[str, Any]],
    *, scan_origin: str = "", identity_version: str = "",
) -> dict[str, Any]:
    """Collapse one non-empty fingerprint into one canonical persisted action."""
    identity_context = {"scan_origin": scan_origin, "identity_version": identity_version}
    group_fingerprint = _persistence_repair_fingerprint(members[0]) if members else ""
    lead = deepcopy(_strictest_member(members))
    lead.pop("observed_evidence_version", None)
    lead.pop("verified_observed_pages", None)
    child_groups = [_repair_evidence_group(member, **identity_context) for member in members]

    affected = _dedupe_urls([
        page
        for member in members
        for page in (member.get("affected_pages") if isinstance(member.get("affected_pages"), list) else [])
    ], **identity_context)
    source_pages = _dedupe_urls([
        page
        for member in members
        for page in (member.get("source_pages") if isinstance(member.get("source_pages"), list) else [])
    ], **identity_context)

    lead["affected_pages"] = affected
    if source_pages:
        lead["source_pages"] = source_pages

    member_versions = [_clean_text(member.get("observed_evidence_version")) for member in members]
    observed_versions = set(member_versions)
    if member_versions and all(member_versions) and len(observed_versions) == 1:
        lead["observed_evidence_version"] = next(iter(observed_versions))
        verified_observed_pages = _dedupe_urls([
            page
            for member in members
            for page in (
                member.get("verified_observed_pages")
                if isinstance(member.get("verified_observed_pages"), list)
                else []
            )
        ], **identity_context)
        if verified_observed_pages:
            lead["verified_observed_pages"] = verified_observed_pages

    all_complete = all(member.get("affected_pages_complete") is not False for member in members)
    lead["affected_pages_complete"] = all_complete
    lead["requires_developer"] = any(member.get("requires_developer") is True for member in members)
    lead["requires_approval"] = any(member.get("requires_approval") is True for member in members)
    lead["can_auto_fix"] = all(member.get("can_auto_fix") is True for member in members)

    hardest = max(
        members,
        key=lambda item: _DIFFICULTY_WEIGHT.get(_clean_text(item.get("difficulty")).lower(), 0),
    )
    for field in ("difficulty", "estimated_time"):
        if _clean_text(hardest.get(field)):
            lead[field] = hardest.get(field)

    if lead["requires_developer"]:
        developer_members = [member for member in members if member.get("requires_developer") is True]
        owner_source = _strictest_member(developer_members)
        if _clean_text(owner_source.get("who_can_do_this")):
            lead["who_can_do_this"] = owner_source.get("who_can_do_this")

    lead["base_severity"] = max(
        (_clean_text(member.get("base_severity") or member.get("priority")).lower() for member in members),
        key=lambda value: _SEVERITY_WEIGHT.get(value, 0),
        default=_clean_text(lead.get("base_severity")).lower(),
    )
    lead["priority"] = max(
        (_clean_text(member.get("priority")).lower() for member in members),
        key=lambda value: _SEVERITY_WEIGHT.get(value, 0),
        default=_clean_text(lead.get("priority")).lower(),
    )
    lead["action_priority"] = max(
        (_clean_text(member.get("action_priority")).lower() for member in members),
        key=lambda value: _ACTION_PRIORITY_WEIGHT.get(value, 0),
        default=_clean_text(lead.get("action_priority")).lower(),
    )
    lead["evidence_class"] = max(
        (_clean_text(member.get("evidence_class")).lower() for member in members),
        key=lambda value: _EVIDENCE_WEIGHT.get(value, 0),
        default=_clean_text(lead.get("evidence_class")).lower(),
    )

    if all_complete:
        lead["page_count"] = len(affected)
        merged = _normalize_canonical_repair_evidence(lead, pages, **identity_context)
    else:
        lead["page_count"] = max(
            len(affected),
            sum(max(_diagnostic_count(member.get("page_count")), len(_dedupe_urls(member.get("affected_pages"), **identity_context))) for member in members),
        )
        breakdown: dict[str, int] = {}
        representatives: dict[str, str] = {}
        for member in members:
            member_breakdown = member.get("family_breakdown") if isinstance(member.get("family_breakdown"), dict) else {}
            for family, count in member_breakdown.items():
                key = _clean_text(family)
                if key:
                    breakdown[key] = breakdown.get(key, 0) + max(0, _diagnostic_count(count))
            member_representatives = (
                member.get("representative_pages_by_family")
                if isinstance(member.get("representative_pages_by_family"), dict)
                else {}
            )
            for family, url in member_representatives.items():
                key = _clean_text(family)
                value = _clean_text(url)
                if key and value and key not in representatives:
                    representatives[key] = value
        if breakdown:
            lead["family_breakdown"] = breakdown
        if representatives:
            lead["representative_pages_by_family"] = representatives
        merged = annotate_repair_identity(lead)

    if identity_version and all_complete:
        merged = annotate_calibrated_repair_priority(merged, pages, **identity_context)

    if group_fingerprint:
        identity = deepcopy(merged.get("repair_identity")) if isinstance(merged.get("repair_identity"), dict) else {}
        identity["fingerprint"] = group_fingerprint
        merged["repair_identity"] = identity
        merged["repair_fingerprint"] = group_fingerprint
    merged["repair_evidence_groups"] = child_groups
    return merged


def _group_canonical_repairs(
    items: list[dict[str, Any]],
    pages: list[dict[str, Any]],
    *, scan_origin: str = "", identity_version: str = "",
) -> list[dict[str, Any]]:
    """Persist one top-level action per valid non-empty repair fingerprint."""
    identity_context = {"scan_origin": scan_origin, "identity_version": identity_version}
    groups: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for index, item in enumerate(items):
        fingerprint = _persistence_repair_fingerprint(item)
        key = f"fingerprint:{fingerprint}" if fingerprint else f"row:{index}"
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(item)

    return [_merge_repair_group(groups[key], pages, **identity_context) for key in order]


def _trusted_stage3_scan_id(scan_result: dict[str, Any]) -> str:
    """Return only an exact producer scan identity suitable for B20 grouping.

    Stage 3 must not invent or borrow a later durable identity. The crawler has
    historically carried both scan_id and scan_run_id; only an exact non-empty
    match is accepted here. Otherwise B20 grouping deliberately fails closed to
    singleton/unverified groups until the durable worker can prove the identity.
    """
    if not isinstance(scan_result, dict):
        return ""
    scan_id = _clean_text(scan_result.get("scan_id"))
    scan_run_id = _clean_text(scan_result.get("scan_run_id"))
    return scan_id if scan_id and scan_run_id and scan_id == scan_run_id else ""


def _attach_stage3_decision_evidence(
    canonical_items: list[dict[str, Any]],
    pre_group_items: list[dict[str, Any]],
    pages: list[dict[str, Any]],
    scan_result: dict[str, Any],
    *,
    scan_origin: str = "",
    identity_version: str = "",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Attach B19 factors and B20 evidenced grouping before authority signing.

    B19 is recomputed over the final canonical affected-page union, never copied
    from one pre-merge child. B20 consumes the pre-fingerprint rows so explicit
    SEO/GEO root-cause evidence is not erased by legacy repair fingerprint
    grouping. No requests, crawl budget, persistence writes or customer
    projection occur here; build_completion_envelope subsequently signs these
    derived fields with the rest of Review.
    """
    identity_context = {"scan_origin": scan_origin, "identity_version": identity_version}
    annotated: list[dict[str, Any]] = []
    for item in canonical_items:
        with_factors = annotate_four_factor_priority(item, pages, **identity_context)
        factors = deepcopy(with_factors.get("stage3_priority_factors") or {})
        with_factors["priority_factors"] = factors
        annotated.append(with_factors)

    root_cause_groups = group_evidenced_root_causes(
        pre_group_items,
        scan_id=_trusted_stage3_scan_id(scan_result),
    )
    return annotated, root_cause_groups


def apply_canonical_repair_contract(
    review_result: dict[str, Any],
    scan_result: dict[str, Any],
    *, identity_version: str = "",
) -> dict[str, Any]:
    """Attach one complete canonical v2 snapshot or leave review untouched.

    The legacy review recommendations are never reordered or rewritten here.
    Canonical repairs are carried in a separate signed completion field and are
    consumed by Base44 persistence only when the whole snapshot validates.
    """
    if not isinstance(review_result, dict):
        return review_result

    identity_context = {"scan_origin": scan_evidence_origin(scan_result) if identity_version else "",
                        "identity_version": identity_version}
    review = deepcopy(review_result)
    pages = _first_pages(scan_result)
    analysis = build_calibrated_shadow_review_analysis(review, pages, **identity_context)
    proposed = analysis.get("proposed_fixes") if isinstance(analysis, dict) else None
    if not isinstance(proposed, list):
        emit("canonical_repair_contract_absent", severity="WARNING", reason="proposed_fixes_missing")
        raise CanonicalRepairContractError("canonical repair synthesis did not produce a list")

    pre_group_items: list[dict[str, Any]] = []
    seen_fix_ids: set[str] = set()
    for source_rank, raw_fix in enumerate(proposed, start=1):
        if not isinstance(raw_fix, dict):
            emit("canonical_repair_contract_absent", severity="WARNING", reason="proposed_fix_not_object", canonical_action_rank=source_rank)
            raise CanonicalRepairContractError("canonical repair synthesis produced a non-object repair")
        canonical_fix = _normalize_canonical_repair_evidence(raw_fix, pages, **identity_context)
        failed_invariant = first_failed_repair_invariant(canonical_fix, **identity_context)
        if failed_invariant:
            emit(
                "canonical_repair_invariant_rejected",
                severity="WARNING",
                **_safe_repair_diagnostic(canonical_fix, failed_invariant, rank=source_rank, **identity_context),
            )
            raise CanonicalRepairContractError(f"canonical repair invariant rejected: {failed_invariant}")
        identity = canonical_fix.get("repair_identity") if isinstance(canonical_fix.get("repair_identity"), dict) else {}
        fix_id = _clean_text(canonical_fix.get("fix_id"))
        if fix_id and fix_id in seen_fix_ids:
            raise CanonicalRepairContractError("canonical repair synthesis produced duplicate fix ids")
        if fix_id:
            seen_fix_ids.add(fix_id)
        pre_group_items.append({
            **deepcopy(canonical_fix),
            "repair_contract_version": REPAIR_CONTRACT_VERSION,
            "repair_priority_model_version": REPAIR_PRIORITY_MODEL_VERSION,
            "repair_identity_version": str(identity.get("version") or "").strip(),
        })

    canonical_items = _group_canonical_repairs(pre_group_items, pages, **identity_context)
    if identity_version:
        canonical_items = sort_calibrated_repairs(canonical_items)
    for rank, item in enumerate(canonical_items, start=1):
        item["canonical_action_rank"] = rank
        item["repair_contract_version"] = REPAIR_CONTRACT_VERSION
        item["repair_priority_model_version"] = REPAIR_PRIORITY_MODEL_VERSION
        identity = item.get("repair_identity") if isinstance(item.get("repair_identity"), dict) else {}
        item["repair_identity_version"] = str(identity.get("version") or item.get("repair_identity_version") or "").strip()

    canonical_ids = [str(item.get("fix_id") or "").strip() for item in canonical_items]
    parent = {
        "repair_contract_version": REPAIR_CONTRACT_VERSION,
        "repair_snapshot_contract_version": REPAIR_CONTRACT_VERSION,
        "repair_snapshot_contract_complete": True,
        "repair_priority_model_version": REPAIR_PRIORITY_MODEL_VERSION,
        "total_fixes": len(canonical_items),
        "canonical_action_fix_ids": canonical_ids,
    }
    validation = validate_v2_persistence_candidate(parent, canonical_items)
    if validation.get("eligible") is not True:
        emit(
            "canonical_repair_contract_absent",
            severity="WARNING",
            reason="persistence_candidate_rejected",
            validation_code=str(validation.get("code") or validation.get("reason") or "")[:160],
            canonical_fix_count=len(canonical_items),
        )
        raise CanonicalRepairContractError("canonical repair persistence candidate was rejected")

    canonical_items, root_cause_groups = _attach_stage3_decision_evidence(
        canonical_items,
        pre_group_items,
        pages,
        scan_result,
        **identity_context,
    )

    return {
        **review,
        **parent,
        "canonical_repairs": canonical_items,
        "stage3_root_cause_groups": root_cause_groups,
        "repair_contract_validation_version": validation.get("version") or "",
    }


def _first_pages(scan_result: dict[str, Any]) -> list[dict[str, Any]]:
    source = scan_result if isinstance(scan_result, dict) else {}
    for key in ("crawled_pages", "pages", "scanned_pages", "crawl_pages"):
        value = source.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _normalize_canonical_repair_evidence(
    fix: dict[str, Any],
    pages: list[dict[str, Any]],
    *, scan_origin: str = "", identity_version: str = "",
) -> dict[str, Any]:
    """Re-derive one canonical repair from one shared affected-page identity.

    Normal review/scoring remains untouched. The durable cutover is the single
    place that reconciles the finished repair's affected URLs, page count, family
    partition and representatives before identity is re-annotated and the
    completion envelope is signed.

    The family resolver is imported lazily to reuse review's existing vocabulary
    without creating a second classifier or changing crawler behavior.
    """
    identity_context = {"scan_origin": scan_origin, "identity_version": identity_version}
    from .review import normalize_template_family

    snapshot = deepcopy(fix)
    if identity_version:
        key_for = repair_evidence_key_function(**identity_context)
        if any(not key_for(value) for value in snapshot.get("affected_pages") or []):
            raise CanonicalRepairContractError("unresolvable affected evidence")
    if snapshot.get("affected_pages_complete") is False:
        return annotate_repair_identity(snapshot)

    normalized = normalize_repair_scope(
        snapshot,
        pages,
        family_resolver=normalize_template_family,
        **identity_context,
    )
    return annotate_repair_identity(normalized)
