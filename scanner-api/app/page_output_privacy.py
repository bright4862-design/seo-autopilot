"""Fail-closed projections for internal per-page evidence.

Stage-2 producers retain richer evidence long enough for deterministic review and
scan-level aggregation. Those intermediate fields are not part of the approved
HTTP/customer/persistence contract. External boundaries must project page
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
    # B13/B14 extraction intermediates. The scan-level authenticated aggregate
    # is the supported contract; raw normalized entity/contact observations are
    # deliberately not a customer/persistence page field.
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


def project_scan_result_for_external_boundary(result: dict[str, Any]) -> dict[str, Any]:
    """Shallow-copy a scan and sanitize every recognized page-list projection.

    Non-page aggregates remain unchanged. In particular, authenticated
    scan-level Stage-2 summaries may survive while raw per-page producer inputs
    stay private. The input result is never mutated, so the canonical Python
    Review can continue consuming the richer internal evidence before the
    persistence boundary is built.
    """
    projected = dict(result)
    for key in PAGE_LIST_KEYS:
        value = result.get(key)
        if isinstance(value, list):
            projected[key] = project_pages_for_external_boundary(value)
    return projected
