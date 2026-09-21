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
from .robots_policy import SCANNER_USER_AGENT
from .stage3_delivery import (
    DEFAULT_PRESENTATION_LIMIT,
    apply_root_cause_score_caps,
    build_handoff_v2,
    prepare_ranked_candidates,
    select_evidence_led_preview,
    summarize_candidate_counts,
)
from .stage3_priority_factors import annotate_four_factor_priority
from .stage3_root_causes import group_evidenced_root_causes


REPAIR_PERSISTENCE_GROUPING_VERSION = "repair_persistence_grouping_v2_valid_fingerprint_actions"
STAGE3_DELIVERY_VERSION = "stage3_delivery_v1_rank_before_truncate"
STAGE3_PREVIEW_SOURCE_VERSION = "stage3_preview_source_v1_verified_evidence"
STAGE3_SCORE_CAP_VERSION = "stage3_health_score_caps_v1_verified_root_cause"
STAGE3_AUTHORITY_CLAIM_VERSION = "stage3_authority_claim_v1"


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
    string match is accepted here. Otherwise B20 grouping deliberately fails
    closed to singleton/unverified groups until the durable worker can prove the
    identity.
    """
    if not isinstance(scan_result, dict):
        return ""
    raw_scan_id = scan_result.get("scan_id")
    raw_scan_run_id = scan_result.get("scan_run_id")
    if not isinstance(raw_scan_id, str) or not isinstance(raw_scan_run_id, str):
        return ""
    scan_id = raw_scan_id.strip()
    scan_run_id = raw_scan_run_id.strip()
    return scan_id if scan_id and scan_run_id and scan_id == scan_run_id else ""


def _stage3_text(value: Any) -> str:
    """Accept only literal scalar text at Stage-3 signed/customer boundaries."""
    return value.strip() if isinstance(value, str) else ""


def _first_stage3_text(*values: Any) -> str:
    """Return the first non-empty literal string without coercing structured values."""
    for value in values:
        text = _stage3_text(value)
        if text:
            return text
    return ""


def _optional_nonnegative_count(value: Any) -> int | None:
    """Preserve an evidenced whole-number count or keep it unknown."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and value.is_integer() and value >= 0:
        return int(value)
    return None


def _verified_stage3_groups_by_member(
    root_cause_groups: list[dict[str, Any]],
    *,
    trusted_scan_id: str,
) -> dict[str, list[dict[str, Any]]]:
    """Index only B20 groups verified for the exact producer scan."""
    output: dict[str, list[dict[str, Any]]] = {}
    for group in root_cause_groups:
        if not isinstance(group, dict):
            continue
        if group.get("grouping_state") != "verified":
            continue
        if _stage3_text(group.get("scan_id")) != trusted_scan_id:
            continue
        members = group.get("member_ids") if isinstance(group.get("member_ids"), list) else []
        for member_id in members:
            clean_member = _stage3_text(member_id)
            if clean_member:
                output.setdefault(clean_member, []).append(group)
    return output


def _stage3_handoff_candidate(
    item: dict[str, Any],
    groups_by_member: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any], bool]:
    """Project one canonical repair into the B24 serializer without inventing IDs.

    B20 may legitimately prove no shared root cause. It may also discover that a
    legacy fingerprint action contains members with different verified causes.
    A singular B24 ``root_cause_id`` cannot truthfully encode that latter shape,
    so the caller fails the whole source snapshot closed instead of guessing.
    """
    member_ids: list[str] = []
    evidence_groups = item.get("repair_evidence_groups") if isinstance(item.get("repair_evidence_groups"), list) else []
    for child in evidence_groups:
        if not isinstance(child, dict):
            continue
        member_id = _stage3_text(child.get("fix_id"))
        if member_id and member_id not in member_ids:
            member_ids.append(member_id)
    if not member_ids:
        fallback = _stage3_text(item.get("fix_id"))
        if fallback:
            member_ids.append(fallback)

    matched_groups: list[dict[str, Any]] = []
    seen_group_keys: set[tuple[str, str, tuple[str, ...]]] = set()
    for member_id in member_ids:
        for group in groups_by_member.get(member_id, []):
            member_key = tuple(
                text
                for value in (group.get("member_ids") if isinstance(group.get("member_ids"), list) else [])
                if (text := _stage3_text(value))
            )
            key = (
                _stage3_text(group.get("root_cause_id")),
                _stage3_text(group.get("repair_surface_id")),
                member_key,
            )
            if key not in seen_group_keys:
                seen_group_keys.add(key)
                matched_groups.append(group)

    root_cause_ids: list[str] = []
    family_ids: list[str] = []
    evidence_refs: list[str] = []
    for group in matched_groups:
        root_cause_id = _stage3_text(group.get("root_cause_id"))
        if root_cause_id and root_cause_id not in root_cause_ids:
            root_cause_ids.append(root_cause_id)
        partitions = group.get("family_partitions") if isinstance(group.get("family_partitions"), dict) else {}
        for family in partitions:
            clean_family = _stage3_text(family)
            if clean_family and clean_family not in family_ids:
                family_ids.append(clean_family)
        refs = group.get("contributing_evidence_refs") if isinstance(group.get("contributing_evidence_refs"), list) else []
        for ref in refs:
            clean_ref = _stage3_text(ref)
            if clean_ref and clean_ref not in evidence_refs:
                evidence_refs.append(clean_ref)

    if not family_ids:
        for child in evidence_groups:
            if isinstance(child, dict):
                family = _stage3_text(child.get("family"))
                if family and family not in family_ids:
                    family_ids.append(family)
    if not family_ids:
        family = _first_stage3_text(item.get("page_template_family"), item.get("template_family"))
        if family:
            family_ids.append(family)

    existing_refs = item.get("evidence_refs") if isinstance(item.get("evidence_refs"), list) else []
    for ref in existing_refs:
        clean_ref = _stage3_text(ref)
        if clean_ref and clean_ref not in evidence_refs:
            evidence_refs.append(clean_ref)

    counts = item.get("stage3_counts") if isinstance(item.get("stage3_counts"), dict) else {}
    candidate = {
        **deepcopy(item),
        "rule_id": _first_stage3_text(item.get("fix_id"), item.get("rule")),
        "title": _first_stage3_text(item.get("issue_title"), item.get("title"), item.get("fix_id"), item.get("rule")),
        "root_cause_id": root_cause_ids[0] if len(root_cause_ids) == 1 else None,
        "family_ids": family_ids,
        "observation_count": counts.get("observation_count"),
        "known_population_count": counts.get("known_population_count"),
        "evidence_refs": evidence_refs,
        "vendor_owner": _first_stage3_text(item.get("vendor_owner"), item.get("who_can_do_this")) or None,
    }
    return candidate, len(root_cause_ids) > 1


def _build_stage3_handoff_v2_source(
    canonical_items: list[dict[str, Any]],
    root_cause_groups: list[dict[str, Any]],
    scan_result: dict[str, Any],
    *,
    scan_origin: str = "",
    identity_version: str = "",
) -> dict[str, Any] | None:
    """Build a customer-safe B24 source snapshot inside the signed Review.

    This is deliberately not a new customer route and does not touch V7
    persistence. It proves the authoritative Python source shape while Stage-1
    publication remains frozen. The eventual durable exporter must consume this
    authenticated source after reconciliation instead of rebuilding Stage 3 from
    an alternate path.
    """
    trusted_scan_id = _trusted_stage3_scan_id(scan_result)
    if not trusted_scan_id:
        return None

    groups_by_member = _verified_stage3_groups_by_member(
        root_cause_groups,
        trusted_scan_id=trusted_scan_id,
    )
    candidates: list[dict[str, Any]] = []
    for item in canonical_items:
        candidate, ambiguous_root_cause = _stage3_handoff_candidate(item, groups_by_member)
        if ambiguous_root_cause:
            return None
        candidates.append(candidate)

    scan_identity = {
        "scan_id": trusted_scan_id,
        "scan_run_id": trusted_scan_id,
        "normalized_domain": _stage3_text(scan_result.get("normalized_domain")) or None,
        "scan_origin": _stage3_text(scan_origin) or None,
        "evidence_url_identity_version": _stage3_text(identity_version) or None,
    }
    source = build_handoff_v2(
        scan_identity=scan_identity,
        fixes=candidates,
        user_agent=SCANNER_USER_AGENT,
        operator_authorized=False,
    )

    # The isolated B24 helper predates the canonical indexable-count requirement.
    # Enrich only the shared authoritative source with the existing evidenced
    # canonical count; missing/invalid values stay None rather than becoming 0.
    serialized_fixes = source.get("fixes") if isinstance(source.get("fixes"), list) else []
    for serialized, candidate in zip(serialized_fixes, candidates):
        if not isinstance(serialized, dict):
            continue
        counts = serialized.get("counts") if isinstance(serialized.get("counts"), dict) else {}
        counts["indexable_affected"] = _optional_nonnegative_count(candidate.get("indexable_affected"))
        serialized["counts"] = counts
    return source


def _stage3_preview_coverage_qualification(review: dict[str, Any]) -> dict[str, Any]:
    """Carry only an explicit bounded coverage qualification; never infer one."""
    fingerprint = review.get("site_fingerprint") if isinstance(review.get("site_fingerprint"), dict) else {}
    assessment = fingerprint.get("coverage_assessment") if isinstance(fingerprint.get("coverage_assessment"), dict) else {}
    state = _clean_text(assessment.get("state") or review.get("coverage_state")) or "unknown"
    output: dict[str, Any] = {"state": state[:80]}
    text = assessment.get("text")
    if isinstance(text, str) and text.strip():
        output["text"] = text.strip()[:500]
    return output


def _stage3_preview_candidate(item: dict[str, Any]) -> dict[str, Any]:
    """Project one canonical repair to the strict B22 selection vocabulary."""
    factors = item.get("stage3_priority_factors") if isinstance(item.get("stage3_priority_factors"), dict) else {}
    verified = _stage3_text(item.get("verification_state")).lower() == "verified"
    summary = item.get("evidence_summary")
    evidence_summary = summary.strip()[:500] if isinstance(summary, str) and summary.strip() else None
    return {
        "rule_id": _first_stage3_text(item.get("fix_id"), item.get("rule"))[:160],
        "title": _first_stage3_text(item.get("issue_title"), item.get("title"), item.get("fix_id"), item.get("rule"))[:240],
        "impact": factors.get("impact"),
        "priority_score": factors.get("priority_factor_score"),
        "preview_allowed": verified,
        "evidence_state": "verified" if verified else "not_verified",
        "evidence_summary": evidence_summary,
    }


def _build_stage3_private_preview_source(
    canonical_items: list[dict[str, Any]],
    review: dict[str, Any],
    scan_result: dict[str, Any],
) -> dict[str, Any] | None:
    """Sign B22's evidence-led selection source without granting customer access.

    The source is intentionally owner-agnostic and carries an explicit entitlement
    requirement. V7 remains responsible for authenticated exact-owner access and the
    two-finding customer projection after Stage-1 reconciliation. This layer only
    authenticates which verified canonical findings are eligible and their strict
    allowlisted preview shape.
    """
    trusted_scan_id = _trusted_stage3_scan_id(scan_result)
    if not trusted_scan_id:
        return None
    selection = select_evidence_led_preview(
        (_stage3_preview_candidate(item) for item in canonical_items),
        max_items=2,
        coverage_qualification=_stage3_preview_coverage_qualification(review),
    )
    return {
        "version": STAGE3_PREVIEW_SOURCE_VERSION,
        "scan_id": trusted_scan_id,
        "entitlement_state": "requires_authenticated_customer_gate",
        **selection,
    }


def _delivery_candidate(item: dict[str, Any]) -> dict[str, Any]:
    """Map authenticated B19 evidence into the reviewed B21 ranking helper.

    This is a temporary ranking view only. It does not write a second priority
    model back into the canonical repair. Unknown B19 scores stay unknown/zero
    for the primary sort, with evidenced impact as the deterministic fallback.
    """
    candidate = deepcopy(item)
    factors = candidate.get("stage3_priority_factors") if isinstance(candidate.get("stage3_priority_factors"), dict) else {}
    # B21 ranks the authenticated B19 factors, not the earlier calibration rank.
    # Remove that legacy presentation hint only from this temporary view so it
    # cannot mask a higher four-factor score before the Stage-3 truncation cap.
    candidate.pop("priority_rank", None)
    candidate["rule_id"] = _first_stage3_text(candidate.get("fix_id"), candidate.get("rule"))
    candidate["priority_score"] = factors.get("priority_factor_score")
    candidate["impact"] = factors.get("impact")
    return candidate


def _health_score_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        result = value
    elif isinstance(value, float) and value.is_integer():
        result = int(value)
    else:
        return None
    return result if 0 <= result <= 100 else None


def _stage3_coverage_state(review: dict[str, Any]) -> str:
    fingerprint = review.get("site_fingerprint") if isinstance(review.get("site_fingerprint"), dict) else {}
    assessment = fingerprint.get("coverage_assessment") if isinstance(fingerprint.get("coverage_assessment"), dict) else {}
    state = _clean_text(assessment.get("state") or review.get("coverage_state"))
    return state or "unknown"


def _stage3_existing_score_ceiling(review: dict[str, Any]) -> int | None:
    """Read an already-applied legacy ceiling without recomputing score policy."""
    explanation = review.get("health_score_explanation") if isinstance(review.get("health_score_explanation"), dict) else {}
    ceiling = _health_score_value(explanation.get("applied_ceiling"))
    return ceiling if ceiling is not None and ceiling < 100 else None


def _stage3_root_cause_cap_inputs(root_cause_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse authenticated B20 groups to one fail-closed B23 cap per cause."""
    by_root: dict[str, dict[str, Any]] = {}
    for group in root_cause_groups:
        if not isinstance(group, dict) or group.get("grouping_state") != "verified":
            continue
        root_cause_id = _stage3_text(group.get("root_cause_id"))
        if not root_cause_id:
            continue
        state = by_root.setdefault(root_cause_id, {"caps": set(), "conflicted": False})
        cap_state = _stage3_text(group.get("score_cap_state"))
        cap = _health_score_value(group.get("score_cap"))
        if cap_state == "conflicted":
            state["conflicted"] = True
        elif cap_state == "documented" and cap is not None:
            state["caps"].add(cap)

    output: list[dict[str, Any]] = []
    for root_cause_id, state in by_root.items():
        caps = state["caps"]
        if state["conflicted"] or len(caps) > 1:
            output.append({
                "root_cause_id": root_cause_id,
                "verification_state": "conflicted",
                "score_cap": None,
            })
        elif len(caps) == 1:
            output.append({
                "root_cause_id": root_cause_id,
                "verification_state": "verified",
                "score_cap": next(iter(caps)),
            })
        else:
            output.append({
                "root_cause_id": root_cause_id,
                "verification_state": "verified",
                "score_cap": None,
            })
    return output


def _build_stage3_health_score_decision(
    review: dict[str, Any],
    root_cause_groups: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Bind B23 to the already-final legacy score without rewriting it yet.

    The current health score has already passed access/sample/incomplete gates.
    Treating that final value as B23's base means this layer can only keep or
    lower it. The existing applied ceiling is carried as authenticated diagnostic
    evidence when the legacy explanation exposes one; it is never recomputed.
    Customer-visible score replacement remains release-gated behind V7 durable
    persistence/card/export integration.
    """
    base_score = _health_score_value(review.get("health_score"))
    if base_score is None:
        return None
    decision = apply_root_cause_score_caps(
        base_score,
        _stage3_root_cause_cap_inputs(root_cause_groups),
        existing_score_ceiling=_stage3_existing_score_ceiling(review),
        coverage_state=_stage3_coverage_state(review),
    )
    return {
        "version": STAGE3_SCORE_CAP_VERSION,
        "state": "decided",
        **decision,
        "legacy_health_score_unchanged": True,
    }


def _attach_stage3_decision_evidence(
    canonical_items: list[dict[str, Any]],
    pre_group_items: list[dict[str, Any]],
    pages: list[dict[str, Any]],
    scan_result: dict[str, Any],
    *,
    scan_origin: str = "", identity_version: str = "",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Attach B19/B20/B21 reviewed evidence before authority signing.

    B19 is recomputed over the final canonical affected-page union, never copied
    from one pre-merge child. B20 consumes the pre-fingerprint rows so explicit
    SEO/GEO root-cause evidence is not erased by legacy repair fingerprint
    grouping. B21 computes truthful counts on every canonical repair and ranks
    every eligible B19-scored repair before the legacy presentation limit. The
    signed delivery summary retains only bounded fix IDs and aggregate counts;
    it does not duplicate raw candidate evidence.
    """
    identity_context = {"scan_origin": scan_origin, "identity_version": identity_version}
    annotated: list[dict[str, Any]] = []
    for item in canonical_items:
        with_factors = annotate_four_factor_priority(item, pages, **identity_context)
        factors = deepcopy(with_factors.get("stage3_priority_factors") or {})
        with_factors["priority_factors"] = factors
        with_factors["stage3_counts"] = summarize_candidate_counts(with_factors)
        annotated.append(with_factors)

    root_cause_groups = group_evidenced_root_causes(
        pre_group_items,
        scan_id=_trusted_stage3_scan_id(scan_result),
    )

    ranked = prepare_ranked_candidates(
        (_delivery_candidate(item) for item in annotated),
        presentation_limit=DEFAULT_PRESENTATION_LIMIT,
    )
    displayed_fix_ids = [
        _stage3_text(item.get("fix_id"))
        for item in ranked.get("displayed_candidates", [])
        if isinstance(item, dict) and _stage3_text(item.get("fix_id"))
    ]
    delivery = {
        "version": STAGE3_DELIVERY_VERSION,
        "eligible_candidate_count": ranked.get("eligible_candidate_count", 0),
        "displayed_candidate_count": ranked.get("displayed_candidate_count", 0),
        "presentation_truncated": ranked.get("presentation_truncated") is True,
        "presentation_omitted_count": ranked.get("presentation_omitted_count", 0),
        "displayed_fix_ids": displayed_fix_ids,
    }
    return annotated, root_cause_groups, delivery


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

    canonical_items, root_cause_groups, stage3_delivery = _attach_stage3_decision_evidence(
        canonical_items,
        pre_group_items,
        pages,
        scan_result,
        **identity_context,
    )
    stage3_private_preview_source = _build_stage3_private_preview_source(
        canonical_items,
        review,
        scan_result,
    )
    stage3_health_score_decision = _build_stage3_health_score_decision(review, root_cause_groups)
    stage3_handoff_v2_source = _build_stage3_handoff_v2_source(
        canonical_items,
        root_cause_groups,
        scan_result,
        **identity_context,
    )
    trusted_stage3_scan_id = _trusted_stage3_scan_id(scan_result)
    stage3_authority_claim = (
        {
            "version": STAGE3_AUTHORITY_CLAIM_VERSION,
            "scan_id": trusted_stage3_scan_id,
            "delivery_version": stage3_delivery.get("version"),
            "score_version": stage3_health_score_decision.get("version"),
        }
        if trusted_stage3_scan_id
        and isinstance(stage3_delivery, dict)
        and isinstance(stage3_health_score_decision, dict)
        else None
    )

    return {
        **review,
        **parent,
        "canonical_repairs": canonical_items,
        "stage3_root_cause_groups": root_cause_groups,
        "stage3_delivery": stage3_delivery,
        **({"stage3_authority_claim": stage3_authority_claim} if stage3_authority_claim is not None else {}),
        **({"stage3_private_preview_source": stage3_private_preview_source} if stage3_private_preview_source is not None else {}),
        **({"stage3_health_score_decision": stage3_health_score_decision} if stage3_health_score_decision is not None else {}),
        **({"stage3_handoff_v2_source": stage3_handoff_v2_source} if stage3_handoff_v2_source is not None else {}),
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