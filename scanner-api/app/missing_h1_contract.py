from __future__ import annotations

from typing import Any

from .page_evidence_gate import page_evidence_class
from .repair_coverage import PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION, repair_evidence_key_function

MISSING_H1_RULE = "missing_h1"
MISSING_H1_REPAIR_SURFACE = "document_primary_heading"
MISSING_H1_REMEDIATION_FAMILY = "add_semantic_h1"
MISSING_H1_RULE_DEFINITION_VERSION = "missing_h1_rule_v1_usable_html_h1_count_zero"
MISSING_H1_COMPARISON_PROFILE_VERSION = "missing_h1_comparison_v1_exact_affected_pages"
MISSING_H1_COMPARISON_EVIDENCE_VERSION = "scan_comparison_evidence_v1_missing_h1"


def missing_h1_contract_fields() -> dict[str, Any]:
    """Return the producer-owned technical identity and comparison contract."""
    return {
        "repair_surface": MISSING_H1_REPAIR_SURFACE,
        "remediation_family": MISSING_H1_REMEDIATION_FAMILY,
        "rule_definition_version": MISSING_H1_RULE_DEFINITION_VERSION,
        "comparison_profile_version": MISSING_H1_COMPARISON_PROFILE_VERSION,
    }


def apply_missing_h1_contract(finding: dict[str, Any]) -> dict[str, Any]:
    """Stamp the exact missing-H1 producer output with stable technical identity.

    This helper must only be used by the deterministic missing-H1 producer. It
    deliberately does not infer identity from display copy or template labels.
    """
    if not isinstance(finding, dict) or str(finding.get("rule") or "").strip().lower() != MISSING_H1_RULE:
        return finding
    return {**finding, **missing_h1_contract_fields()}


def _status_code(page: dict[str, Any]) -> int:
    raw = page.get("status_code") if page.get("status_code") is not None else page.get("status")
    if isinstance(raw, bool):
        return 0
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 0
    return value if 0 <= value <= 599 else 0


def _h1_count(page: dict[str, Any]) -> int | None:
    raw = page.get("h1_count")
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
        return None
    return raw


def _indexable(page: dict[str, Any]) -> bool | None:
    value = page.get("indexable")
    if isinstance(value, bool):
        return value
    state = str(page.get("indexability_state") or "").strip().lower()
    if state in {"indexable", "indexable_candidate"}:
        return True
    if state in {"noindexed", "blocked by robots.txt", "non_indexable", "non-indexable"}:
        return False
    return None


def _page_url(page: dict[str, Any]) -> str:
    for key in ("url", "final_url", "page_url", "path"):
        value = page.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def build_missing_h1_comparison_evidence(
    pages: list[dict[str, Any]],
    *,
    scan_origin: str = "",
    identity_version: str = "",
) -> dict[str, Any]:
    """Build bounded deterministic page/rule evidence for missing-H1 comparison.

    Only the exact retained page population is represented. Omitted or
    unevaluable URLs stay non-proof on a later comparison; they can never be
    interpreted as a fixed heading.
    """
    if identity_version != PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION or not scan_origin:
        return {}

    key_for = repair_evidence_key_function(scan_origin=scan_origin, identity_version=identity_version)
    observations: list[dict[str, Any]] = []
    seen: set[str] = set()

    for page in pages or []:
        if not isinstance(page, dict):
            continue
        page_url = key_for(_page_url(page))
        if not page_url or page_url in seen:
            continue
        seen.add(page_url)

        evidence_class = page_evidence_class(page)
        status_code = _status_code(page)
        h1_count = _h1_count(page)
        evaluated = evidence_class == "usable_html" and status_code == 200 and h1_count is not None
        finding_present = (h1_count == 0) if evaluated else None
        indexable = _indexable(page)
        robots = page.get("robots") or page.get("robots_meta") or page.get("meta_robots") or ""

        observations.append({
            "page_url": page_url,
            "status_code": status_code,
            "content_type": str(page.get("content_type") or page.get("mime_type") or "")[:200],
            "page_evidence_class": evidence_class,
            "indexable": indexable,
            "robots": str(robots)[:500] if isinstance(robots, str) else "",
            "h1_count": h1_count,
            "evaluated": evaluated,
            "applicable": evaluated,
            "finding_present": finding_present,
        })

    observations.sort(key=lambda item: item["page_url"])
    observations = observations[:150]
    evaluated = [item for item in observations if item["evaluated"] is True]
    present = [item for item in evaluated if item["finding_present"] is True]
    absent = [item for item in evaluated if item["finding_present"] is False]

    return {
        "version": MISSING_H1_COMPARISON_EVIDENCE_VERSION,
        "rule": MISSING_H1_RULE,
        "rule_definition_version": MISSING_H1_RULE_DEFINITION_VERSION,
        "comparison_profile_version": MISSING_H1_COMPARISON_PROFILE_VERSION,
        "evidence_url_identity_version": identity_version,
        "observation_count": len(observations),
        "evaluated_page_count": len(evaluated),
        "finding_present_count": len(present),
        "finding_absent_count": len(absent),
        "observations": observations,
    }
