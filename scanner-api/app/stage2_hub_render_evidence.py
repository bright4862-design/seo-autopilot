"""B12 paired raw/rendered hub-link evidence over the retained Standard-150 set.

This adapter never fetches or renders pages itself. It consumes the B11 retained
internal-link provenance plus browser observations supplied by the existing
bounded render-followup policy. Raw and rendered link sets are comparison
surfaces only; neither is promoted to sole truth.
"""
from __future__ import annotations

from typing import Any, Iterable
from urllib.parse import urldefrag, urljoin, urlparse

from .stage2_coverage_evidence import HUB_RENDER_COMPARE_VERSION
from .stage2_reachability_provenance import (
    REACHABILITY_PROVENANCE_VERSION,
    REACHABILITY_SCOPE,
)

HUB_RENDER_PRODUCER_VERSION = "hub_raw_rendered_links_producer_v1"
HUB_RENDER_SCOPE = "retained_standard150_pages_only"
MAX_HUBS = 5
MAX_LINK_SAMPLES = 20

# Deliberately narrow structural families. Ordinary leaves are not promoted to
# hubs just because they happen to have many links in one observed sample.
HUB_FAMILY_PRIORITY = (
    "homepage",
    "collection_page",
    "location_landing",
    "comparison_page",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _request_url(page: dict[str, Any]) -> str:
    # B12 uses the exact published/request identity retained by B11. Redirect
    # destinations remain separate evidence rather than collapsing the route.
    return _text(page.get("url"))


def _b11_verified_page(page: dict[str, Any]) -> bool:
    return (
        isinstance(page, dict)
        and page.get("page_evidence_class") == "usable_html"
        and int(page.get("status_code") or 0) == 200
        and not page.get("fetch_error")
        and page.get("reachability_provenance_version") == REACHABILITY_PROVENANCE_VERSION
        and page.get("reachability_scope") == REACHABILITY_SCOPE
        and page.get("reachability_evidence_state") == "observed_sample"
        and page.get("sitewide_orphan_claim") is False
        and bool(_request_url(page))
    )


def select_representative_hubs(
    pages: list[dict[str, Any]],
    *,
    max_hubs: int = MAX_HUBS,
) -> list[dict[str, Any]]:
    """Select a stable, family-diverse sample of verified structural hubs."""
    limit = max(0, min(int(max_hubs or 0), MAX_HUBS))
    if not isinstance(pages, list) or limit == 0:
        return []

    eligible = [
        page
        for page in pages
        if _b11_verified_page(page)
        and _text(page.get("page_template_family")) in HUB_FAMILY_PRIORITY
    ]
    selected: list[dict[str, Any]] = []
    selected_urls: set[str] = set()

    # Take one representative from each structural family before filling the
    # remaining slots in retained-page order. This avoids one large collection
    # family crowding every other hub surface out of a five-page budget.
    for family in HUB_FAMILY_PRIORITY:
        for page in eligible:
            url = _request_url(page)
            if page.get("page_template_family") == family and url not in selected_urls:
                selected.append(page)
                selected_urls.add(url)
                break
        if len(selected) >= limit:
            return selected

    for page in eligible:
        url = _request_url(page)
        if url in selected_urls:
            continue
        selected.append(page)
        selected_urls.add(url)
        if len(selected) >= limit:
            break
    return selected


def _raw_retained_links(pages: list[dict[str, Any]], source_url: str) -> list[str]:
    """Invert B11 verified inlinks into one source's retained outgoing set."""
    links: list[str] = []
    seen: set[str] = set()
    for target in pages:
        if not _b11_verified_page(target):
            continue
        sources = target.get("internal_source_pages")
        if not isinstance(sources, list) or source_url not in sources:
            continue
        target_url = _request_url(target)
        if target_url and target_url not in seen:
            seen.add(target_url)
            links.append(target_url)
    return links


def _rendered_retained_links(
    rendered_page: dict[str, Any],
    *,
    hub_url: str,
    retained_urls: set[str],
) -> list[str] | None:
    """Return exact retained URLs from explicit renderer link evidence.

    A renderer result without a link collection is not an empty link set. It is
    unavailable evidence and therefore returns ``None``.
    """
    raw_links = rendered_page.get("links")
    if raw_links is None:
        raw_links = rendered_page.get("_links")
    if not isinstance(raw_links, list):
        return None

    output: list[str] = []
    seen: set[str] = set()
    for item in raw_links:
        href = item.get("href") if isinstance(item, dict) else item
        raw = _text(href)
        if not raw:
            continue
        try:
            resolved, _ = urldefrag(urljoin(hub_url, raw))
            parsed = urlparse(resolved)
        except Exception:
            continue
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        # The comparison is intentionally scoped to the exact retained assessed
        # set. A rendered link to an unsampled URL is not silently counted as a
        # newly assessed page and does not expand the Standard-150 denominator.
        if resolved not in retained_urls or resolved in seen:
            continue
        seen.add(resolved)
        output.append(resolved)
    return output


def build_hub_link_comparison(
    pages: list[dict[str, Any]],
    *,
    rendered_pages_by_url: dict[str, dict[str, Any]] | None = None,
    attempted_urls: Iterable[str] = (),
    failure_reasons: dict[str, str] | None = None,
    max_hubs: int = MAX_HUBS,
) -> dict[str, Any]:
    """Build truthful B12 selected/completed/failed/unassessed evidence."""
    if not isinstance(pages, list):
        raise ValueError("Expected retained page list")
    if len(pages) > 150:
        raise ValueError("B12 cannot exceed the Standard-150 assessed set")

    rendered = rendered_pages_by_url or {}
    failures = failure_reasons or {}
    attempted = {_text(value) for value in attempted_urls if _text(value)}
    all_eligible = select_representative_hubs(pages, max_hubs=MAX_HUBS)
    selected = all_eligible[: max(0, min(int(max_hubs or 0), MAX_HUBS))]
    retained_urls = {
        _request_url(page)
        for page in pages
        if _b11_verified_page(page) and _request_url(page)
    }

    rows: list[dict[str, Any]] = []
    for page in selected:
        hub_url = _request_url(page)
        raw_links = _raw_retained_links(pages, hub_url)
        base = {
            "hub_url": hub_url,
            "page_template_family": _text(page.get("page_template_family")),
            "raw_evidence_state": "completed",
            "raw_link_count": len(raw_links),
            "rendered_link_count": None,
            "render_only_count": None,
            "raw_only_count": None,
            "render_only_samples": [],
            "raw_only_samples": [],
        }
        if hub_url not in attempted:
            rows.append(
                {
                    **base,
                    "state": "unassessed",
                    "reason": "render_resource_policy_not_selected",
                    "rendered_evidence_state": "unassessed",
                }
            )
            continue
        if hub_url in failures:
            rows.append(
                {
                    **base,
                    "state": "failed",
                    "reason": _text(failures.get(hub_url))[:180] or "renderer_failed",
                    "rendered_evidence_state": "failed",
                }
            )
            continue
        rendered_page = rendered.get(hub_url)
        if not isinstance(rendered_page, dict):
            rows.append(
                {
                    **base,
                    "state": "failed",
                    "reason": "renderer_result_missing",
                    "rendered_evidence_state": "failed",
                }
            )
            continue
        rendered_links = _rendered_retained_links(
            rendered_page,
            hub_url=hub_url,
            retained_urls=retained_urls,
        )
        if rendered_links is None:
            rows.append(
                {
                    **base,
                    "state": "failed",
                    "reason": "rendered_link_evidence_unavailable",
                    "rendered_evidence_state": "failed",
                }
            )
            continue

        raw_set = set(raw_links)
        rendered_set = set(rendered_links)
        render_only = sorted(rendered_set - raw_set)
        raw_only = sorted(raw_set - rendered_set)
        rows.append(
            {
                **base,
                "state": "completed",
                "reason": "paired_successful_retained_link_evidence",
                "rendered_evidence_state": "completed",
                "rendered_link_count": len(rendered_set),
                "render_only_count": len(render_only),
                "raw_only_count": len(raw_only),
                "render_only_samples": render_only[:MAX_LINK_SAMPLES],
                "raw_only_samples": raw_only[:MAX_LINK_SAMPLES],
            }
        )

    completed = sum(1 for row in rows if row["state"] == "completed")
    failed = sum(1 for row in rows if row["state"] == "failed")
    unassessed = sum(1 for row in rows if row["state"] == "unassessed")
    evidence_state = (
        "not_assessed"
        if not rows or (completed == 0 and failed == 0)
        else "complete"
        if completed == len(rows)
        else "partial"
    )
    return {
        "version": HUB_RENDER_COMPARE_VERSION,
        "producer_version": HUB_RENDER_PRODUCER_VERSION,
        "scope": HUB_RENDER_SCOPE,
        "evidence_state": evidence_state,
        "interpretation": "paired_comparison_neither_surface_is_sole_truth",
        "eligible_hubs": len(all_eligible),
        "selected": len(rows),
        "completed": completed,
        "failed": failed,
        "unassessed": unassessed,
        "hubs": rows,
    }
