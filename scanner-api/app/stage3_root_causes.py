from __future__ import annotations

from collections import OrderedDict
from typing import Any

ROOT_CAUSE_GROUPING_VERSION = "root_cause_grouping_v1_evidenced"
ROOT_CAUSE_EVIDENCE_VERSION = "root_cause_evidence_v1_verified"

VERIFIED_STATES = {"confirmed", "verified"}
CONFLICT_STATES = {"conflicted", "conflict"}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _strict_text(value: Any) -> str:
    """Accept only actual string evidence at signed root-cause identity boundaries."""
    return value.strip() if isinstance(value, str) else ""


def _lower(value: Any) -> str:
    return _clean(value).lower()


def _score_cap(value: Any) -> int | None:
    """Accept only an explicitly numeric whole-number 0..100 cap.

    A root-cause cap changes health-score authority, so string coercion and
    fractional truncation are deliberately rejected instead of guessed.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        result = value
    elif isinstance(value, float) and value.is_integer():
        result = int(value)
    else:
        return None
    return result if 0 <= result <= 100 else None


def _fix_id(fix: dict[str, Any], index: int) -> str:
    return _clean(fix.get("id") or fix.get("repair_id") or fix.get("fix_id")) or f"member:{index}"


def _domain(fix: dict[str, Any]) -> str:
    explicit = _lower(fix.get("finding_domain") or fix.get("seo_geo_scope") or fix.get("domain"))
    if explicit in {"seo", "geo"}:
        return explicit
    rule = _lower(fix.get("rule") or fix.get("type"))
    category = _lower(fix.get("category"))
    if rule.startswith("geo_") or category.startswith("geo"):
        return "geo"
    return "seo"


def _family(fix: dict[str, Any]) -> str:
    return _lower(fix.get("page_template_family") or fix.get("template_family")) or "unknown"


def _affected_pages(fix: dict[str, Any]) -> list[str]:
    values = fix.get("affected_pages") if isinstance(fix.get("affected_pages"), list) else []
    if not values:
        fallback = fix.get("page_url") or fix.get("representative_page_url")
        values = [fallback] if fallback else []
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        raw = _clean(value)
        if raw and raw not in seen:
            seen.add(raw)
            output.append(raw)
    return output


def _observation_ids(fix: dict[str, Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for field in ("observation_ids", "contributing_observations", "evidence_refs"):
        values = fix.get(field)
        if not isinstance(values, list):
            continue
        for value in values:
            raw = _clean(value)
            if raw and raw not in seen:
                seen.add(raw)
                output.append(raw)
    return output


def validate_root_cause_evidence(fix: dict[str, Any]) -> dict[str, Any]:
    evidence = fix.get("root_cause_evidence")
    if not isinstance(evidence, dict):
        return {
            "state": "not_verified",
            "reason": "missing explicit root-cause evidence",
            "root_cause_id": None,
            "repair_surface_id": None,
            "evidence_refs": [],
            "score_cap": None,
        }

    if evidence.get("version") != ROOT_CAUSE_EVIDENCE_VERSION:
        return {
            "state": "not_verified",
            "reason": "unknown or missing root-cause evidence version",
            "root_cause_id": None,
            "repair_surface_id": None,
            "evidence_refs": [],
            "score_cap": None,
        }

    state = _lower(evidence.get("state"))
    root_cause_id = _strict_text(evidence.get("root_cause_id"))
    repair_surface_id = _strict_text(evidence.get("repair_surface_id"))
    refs = []
    seen: set[str] = set()
    for value in evidence.get("evidence_refs") if isinstance(evidence.get("evidence_refs"), list) else []:
        raw = _strict_text(value)
        if raw and raw not in seen:
            seen.add(raw)
            refs.append(raw)
    score_cap = _score_cap(evidence.get("score_cap"))

    if state in CONFLICT_STATES:
        return {
            "state": "conflicted",
            "reason": "root-cause evidence conflicts",
            "root_cause_id": root_cause_id or None,
            "repair_surface_id": repair_surface_id or None,
            "evidence_refs": refs,
            "score_cap": None,
        }
    if state not in VERIFIED_STATES:
        return {
            "state": "not_verified",
            "reason": "root-cause evidence is not verified",
            "root_cause_id": root_cause_id or None,
            "repair_surface_id": repair_surface_id or None,
            "evidence_refs": refs,
            "score_cap": None,
        }
    if not root_cause_id:
        return {
            "state": "not_verified",
            "reason": "verified root-cause evidence is missing a stable root_cause_id",
            "root_cause_id": None,
            "repair_surface_id": repair_surface_id or None,
            "evidence_refs": refs,
            "score_cap": None,
        }
    if not refs:
        return {
            "state": "not_verified",
            "reason": "verified root-cause evidence has no contributing evidence references",
            "root_cause_id": root_cause_id,
            "repair_surface_id": repair_surface_id or None,
            "evidence_refs": [],
            "score_cap": None,
        }

    return {
        "state": "verified",
        "reason": "explicit verified root-cause evidence",
        "root_cause_id": root_cause_id,
        "repair_surface_id": repair_surface_id or None,
        "evidence_refs": refs,
        "score_cap": score_cap,
    }


def _trusted_member_scan_identity(fix: dict[str, Any], provided_scan_id: str) -> tuple[str, bool]:
    """Bind a B20 member to the trusted producer identity, never a repair-local one.

    ``provided_scan_id`` is already validated at the caller as the exact matching
    producer ``scan_id == scan_run_id``. Repair-local identity fields are only
    consistency assertions: if either is present it must exactly match the trusted
    producer identity. Missing/invalid producer identity cannot be resurrected by a
    repair-local value.
    """
    trusted = _clean(provided_scan_id)
    if not trusted:
        return "", False

    for field in ("scan_id", "scan_run_id"):
        local = _clean(fix.get(field))
        if local and local != trusted:
            return trusted, False
    return trusted, True


def _singleton_group(
    fix: dict[str, Any],
    *,
    index: int,
    evidence: dict[str, Any],
    scan_id: str,
) -> dict[str, Any]:
    member_id = _fix_id(fix, index)
    family = _family(fix)
    domain = _domain(fix)
    affected_pages = _affected_pages(fix)
    return {
        "version": ROOT_CAUSE_GROUPING_VERSION,
        "grouping_state": evidence["state"],
        "grouping_reason": evidence["reason"],
        "root_cause_id": evidence.get("root_cause_id"),
        "repair_surface_id": evidence.get("repair_surface_id"),
        "scan_id": scan_id or None,
        "member_ids": [member_id],
        "member_count": 1,
        "domains": [domain],
        "family_partitions": {family: [member_id]},
        "affected_pages": affected_pages,
        "affected_page_count": len(affected_pages),
        "contributing_evidence_refs": list(evidence.get("evidence_refs") or []),
        "contributing_observation_ids": _observation_ids(fix),
        "score_cap": None,
        "score_cap_state": "not_verified",
        "suppressed_members": [],
    }


def group_evidenced_root_causes(
    fixes: list[dict[str, Any]],
    *,
    scan_id: str = "",
) -> list[dict[str, Any]]:
    """Group only repairs with the same explicit verified cause in one scan.

    Page/template family, impact class and similar wording are never sufficient
    grouping evidence. Verified SEO and GEO members may share one cause while
    retaining domain/family partitions and exact affected URL unions. Output
    order is anchored to the first member seen, so grouping cannot move an
    earlier-ranked verified repair behind later singleton repairs. Verified
    grouping also requires an exact trusted producer scan identity; missing or
    mismatched producer identity, or any conflicting repair-local identity,
    fails closed to a singleton rather than creating a cross-run merge surface.

    B23 caps travel only inside the same versioned verified root-cause evidence.
    Missing caps do not invent a penalty; conflicting explicit caps for the same
    group fail closed rather than choosing the harsher value.
    """
    ordered_groups: list[dict[str, Any]] = []
    verified: OrderedDict[tuple[str, str, str], dict[str, Any]] = OrderedDict()

    for index, fix in enumerate(fixes or []):
        if not isinstance(fix, dict):
            continue
        evidence = validate_root_cause_evidence(fix)
        member_scan_id, identity_matches = _trusted_member_scan_identity(fix, scan_id)
        if evidence["state"] == "verified" and not identity_matches:
            reason = (
                "repair scan identity does not match trusted producer identity"
                if member_scan_id
                else "verified root-cause grouping requires exact scan identity"
            )
            evidence = {
                **evidence,
                "state": "not_verified",
                "reason": reason,
                "score_cap": None,
            }
        if evidence["state"] != "verified":
            ordered_groups.append(
                _singleton_group(
                    fix,
                    index=index,
                    evidence=evidence,
                    scan_id=member_scan_id,
                )
            )
            continue

        root_cause_id = str(evidence["root_cause_id"])
        repair_surface_id = str(evidence.get("repair_surface_id") or "")
        key = (member_scan_id, root_cause_id, repair_surface_id)
        member_id = _fix_id(fix, index)
        family = _family(fix)
        domain = _domain(fix)

        group = verified.get(key)
        if group is None:
            cap = evidence.get("score_cap")
            group = {
                "version": ROOT_CAUSE_GROUPING_VERSION,
                "grouping_state": "verified",
                "grouping_reason": "members share the same explicit verified root cause",
                "root_cause_id": root_cause_id,
                "repair_surface_id": repair_surface_id or None,
                "scan_id": member_scan_id,
                "member_ids": [],
                "member_count": 0,
                "domains": [],
                "family_partitions": {},
                "affected_pages": [],
                "affected_page_count": 0,
                "contributing_evidence_refs": [],
                "contributing_observation_ids": [],
                "score_cap": cap,
                "score_cap_state": "documented" if cap is not None else "not_documented",
                "suppressed_members": [],
            }
            verified[key] = group
            ordered_groups.append(group)
        else:
            member_cap = evidence.get("score_cap")
            if member_cap is not None and group.get("score_cap_state") != "conflicted":
                current_cap = group.get("score_cap")
                if current_cap is None:
                    group["score_cap"] = member_cap
                    group["score_cap_state"] = "documented"
                elif current_cap != member_cap:
                    group["score_cap"] = None
                    group["score_cap_state"] = "conflicted"

        group["member_ids"].append(member_id)
        group["member_count"] = len(group["member_ids"])
        if domain not in group["domains"]:
            group["domains"].append(domain)
        family_members = group["family_partitions"].setdefault(family, [])
        family_members.append(member_id)

        for url in _affected_pages(fix):
            if url not in group["affected_pages"]:
                group["affected_pages"].append(url)
        group["affected_page_count"] = len(group["affected_pages"])

        for ref in evidence.get("evidence_refs") or []:
            if ref not in group["contributing_evidence_refs"]:
                group["contributing_evidence_refs"].append(ref)
        for observation_id in _observation_ids(fix):
            if observation_id not in group["contributing_observation_ids"]:
                group["contributing_observation_ids"].append(observation_id)

        if len(group["member_ids"]) > 1:
            group["suppressed_members"].append(
                {
                    "member_id": member_id,
                    "reason": "same_verified_root_cause",
                    "root_cause_id": root_cause_id,
                    "repair_surface_id": repair_surface_id or None,
                    "evidence_refs": list(evidence.get("evidence_refs") or []),
                }
            )

    return ordered_groups
