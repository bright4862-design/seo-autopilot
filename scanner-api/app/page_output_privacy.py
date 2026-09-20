"""Fail-closed projections for internal Stage-2 page evidence.

Stage-2 producers retain richer evidence long enough for deterministic review and
scan-level aggregation. Those intermediate fields are not part of the approved
HTTP/customer/persistence contract. The common post-crawl boundary projects page
records through this module instead of forwarding producer dictionaries.
"""
from __future__ import annotations

from typing import Any, Iterable


INTERNAL_PAGE_EVIDENCE_FIELDS = frozenset({
    # B10 deterministic main-content intermediate evidence.
    "main_text",
    "main_text_evidence_version",
    "main_text_signature",
    "main_text_representation",
    "main_text_token_count",
    "main_text_char_count",
    "main_text_source",
    "main_text_verified",
    "main_text_reason",
    "main_text_truncated",
    # B13/B14 extraction intermediates. The scan-level aggregate is reduced to
    # non-content states/counts before persistence; raw normalized observations
    # are deliberately not a customer/persistence page field.
    "local_entity_observations",
    "location_context",
    # B15 evidence remains internal until an authenticated customer contract is
    # intentionally added.
    "contextual_freshness_evidence",
    # B11's private retained-link cache should already be removed by the
    # producer. Keeping it in the deny-list makes the external boundary fail
    # closed if a future regression reintroduces it.
    "_reachability_links",
})

PAGE_LIST_KEYS = ("pages", "crawled_pages", "scanned_pages", "crawl_pages")

_LOCAL_COMPLETENESS_ALLOWED_FIELDS = frozenset({
    "version",
    "state",
    "reason",
    "missing_required",
    "unverified_fields",
    "contextual_status",
    "optional_available",
    "entity_match",
    "entity_identity_reason",
    "source",
    "surface_provenance",
    "context_provenance_version",
    "contextual_status_state",
})

_LOCAL_NAP_INCONSISTENCY_ALLOWED_FIELDS = frozenset({
    "fields",
    "source_count",
    "provenance",
})


def project_page_for_external_boundary(page: Any) -> Any:
    """Copy one page while removing producer-only evidence fields."""
    if not isinstance(page, dict):
        return page
    return {
        key: value
        for key, value in page.items()
        if key not in INTERNAL_PAGE_EVIDENCE_FIELDS
    }


def project_pages_for_external_boundary(pages: Iterable[Any]) -> list[Any]:
    """Return a projected page list without mutating internal review evidence."""
    return [project_page_for_external_boundary(page) for page in pages]


def project_local_entity_scan_evidence(evidence: Any) -> Any:
    """Keep B13/B14 states/counts while dropping content and entity identity.

    The producer aggregate is useful downstream for requirement/version/state
    proof, but its internal rows still carry exact page URLs, absolute entity IDs
    and accepted-heading provenance. Those values are not required to prove the
    aggregate state and must not cross the customer/persistence boundary.
    """
    if not isinstance(evidence, dict):
        return evidence

    projected = {
        key: value
        for key, value in evidence.items()
        if key not in {"completeness", "nap_consistency"}
    }

    completeness = evidence.get("completeness")
    if isinstance(completeness, list):
        projected["completeness"] = [
            {
                key: value
                for key, value in row.items()
                if key in _LOCAL_COMPLETENESS_ALLOWED_FIELDS
            }
            for row in completeness
            if isinstance(row, dict)
        ]

    nap = evidence.get("nap_consistency")
    if isinstance(nap, dict):
        safe_nap = {
            key: value
            for key, value in nap.items()
            if key != "inconsistencies"
        }
        inconsistencies = nap.get("inconsistencies")
        if isinstance(inconsistencies, list):
            safe_nap["inconsistencies"] = [
                {
                    key: value
                    for key, value in row.items()
                    if key in _LOCAL_NAP_INCONSISTENCY_ALLOWED_FIELDS
                }
                for row in inconsistencies
                if isinstance(row, dict)
            ]
        projected["nap_consistency"] = safe_nap

    return projected


def _project_local_entity_aggregate(container: dict[str, Any]) -> dict[str, Any]:
    projected = dict(container)
    if "local_entity_scan_evidence" in container:
        projected["local_entity_scan_evidence"] = project_local_entity_scan_evidence(
            container.get("local_entity_scan_evidence")
        )
    return projected


def project_scan_result_for_external_boundary(result: dict[str, Any]) -> dict[str, Any]:
    """Copy a scan while removing producer-only content/identity evidence.

    Page arrays are projected independently so aliases cannot retain a private
    field. B13/B14 scan-level evidence is reduced to versioned states/counts and
    non-content diagnostics. The input result is never mutated.
    """
    projected = _project_local_entity_aggregate(result)
    for key in PAGE_LIST_KEYS:
        value = result.get(key)
        if isinstance(value, list):
            projected[key] = project_pages_for_external_boundary(value)

    technical = result.get("technical_audit_summary")
    if isinstance(technical, dict):
        projected["technical_audit_summary"] = _project_local_entity_aggregate(technical)

    return projected
