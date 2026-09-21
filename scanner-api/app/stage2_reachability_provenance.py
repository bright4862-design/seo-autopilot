"""B11 producer adapter for sample-scoped money-page reachability evidence.

This module does not perform network I/O and does not decide customer findings.
It converts already-observed, accepted Standard-150 internal-link evidence into a
stable provenance envelope. Sitemap discovery is deliberately not an inlink, and
no value in this module is evidence of sitewide orphaning.
"""
from __future__ import annotations

from typing import Any

REACHABILITY_PROVENANCE_VERSION = "money_page_reachability_provenance_v1"
REACHABILITY_SCOPE = "observed_standard150_sample_only"
MAX_ASSESSED_PAGES = 150
MAX_DISCOVERY_TARGETS = MAX_ASSESSED_PAGES * 8
MAX_SOURCE_SAMPLES = 20
MAX_OUTGOING_LINKS_PER_SOURCE = 2000

_INTERNAL_SOURCES = "reachability_internal_sources"
_NAV_SOURCES = "reachability_navigation_sources"
_NON_NAV_SOURCES = "reachability_non_navigation_sources"
_UNKNOWN_NAV_SOURCES = "reachability_unknown_navigation_sources"
_UNVERIFIED_SOURCES = "reachability_unverified_internal_sources"
_PRIVATE_LINKS = "_reachability_links"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dedupe(values: Any, *, limit: int = MAX_DISCOVERY_TARGETS) -> list[str]:
    if not isinstance(values, list):
        return []
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = _text(value)
        if item and item not in seen:
            seen.add(item)
            output.append(item)
            if len(output) >= limit:
                break
    return output


def ensure_reachability_record(record: dict[str, Any]) -> dict[str, Any]:
    """Ensure the discovery record contains list-only B11 producer fields.

    Scanner discovery snapshots currently copy every value with ``list(value)``.
    Keeping these fields list-only lets B11 integrate without changing that shared
    snapshot contract or the existing source_pages semantics.
    """
    if not isinstance(record, dict):
        raise ValueError("Expected discovery record")
    for key in (
        _INTERNAL_SOURCES,
        _NAV_SOURCES,
        _NON_NAV_SOURCES,
        _UNKNOWN_NAV_SOURCES,
        _UNVERIFIED_SOURCES,
    ):
        if not isinstance(record.get(key), list):
            record[key] = []
    return record


def record_internal_link_observation(
    record: dict[str, Any],
    *,
    source_url: str,
    source_usable_html: bool,
    navigation_presence: bool | None,
) -> None:
    """Retain one observed internal-link edge without changing crawl admission.

    Links parsed from challenged, failed, incomplete, or otherwise unaccepted
    source HTML are retained only as unverified diagnostics and never become
    reachability/inlink evidence.
    """
    record = ensure_reachability_record(record)
    source = _text(source_url)
    if not source:
        return
    if source_usable_html is not True:
        if source not in record[_UNVERIFIED_SOURCES]:
            record[_UNVERIFIED_SOURCES].append(source)
        return
    if source not in record[_INTERNAL_SOURCES]:
        record[_INTERNAL_SOURCES].append(source)
    if navigation_presence is True:
        target = record[_NAV_SOURCES]
    elif navigation_presence is False:
        target = record[_NON_NAV_SOURCES]
    else:
        target = record[_UNKNOWN_NAV_SOURCES]
    if source not in target:
        target.append(source)


def _usable_html_page(page: dict[str, Any]) -> bool:
    return (
        isinstance(page, dict)
        and page.get("page_evidence_class") == "usable_html"
        and 200 <= int(page.get("status_code") or 0) < 300
        and not page.get("fetch_error")
        and not page.get("raw_html_truncated")
    )


def _page_request_url(page: dict[str, Any]) -> str:
    # Requested URL is the graph identity. A redirect destination is separate
    # evidence and must not silently collapse route identity for B11.
    return _text(page.get("url"))


def _accepted_source_urls(pages: list[dict[str, Any]]) -> set[str]:
    return {
        url
        for page in pages
        if _usable_html_page(page)
        for url in [_page_request_url(page)]
        if url
    }


def _verified_edges(
    discovery: dict[str, Any],
    accepted_sources: set[str],
) -> dict[str, list[str]]:
    edges: dict[str, list[str]] = {}
    for target, raw_record in discovery.items():
        target_url = _text(target)
        if not target_url or not isinstance(raw_record, dict):
            continue
        sources = [
            source
            for source in _dedupe(raw_record.get(_INTERNAL_SOURCES))
            if source in accepted_sources
        ]
        if sources:
            edges[target_url] = sources
    return edges


def observed_crawl_depths(
    pages: list[dict[str, Any]],
    discovery: dict[str, Any],
    *,
    seed_url: str,
) -> dict[str, int]:
    """Compute shortest observed accepted-HTML path from the submitted seed.

    A sitemap listing never creates an edge. Depth is therefore unknown for a
    sitemap-only page rather than being invented from crawl order.
    """
    if not isinstance(pages, list) or len(pages) > MAX_ASSESSED_PAGES:
        raise ValueError("Expected at most 150 assessed pages")
    if not isinstance(discovery, dict) or len(discovery) > MAX_DISCOVERY_TARGETS:
        raise ValueError("Discovery graph exceeds the bounded Standard-150 frontier")
    accepted_sources = _accepted_source_urls(pages)
    seed = _text(seed_url)
    if not seed or seed not in accepted_sources:
        return {}
    edges = _verified_edges(discovery, accepted_sources)
    depths: dict[str, int] = {seed: 0}
    # The accepted assessed set is at most 150 pages. Repeated relaxation avoids
    # depending on concurrent fetch/queue order while remaining tightly bounded.
    for _ in range(MAX_ASSESSED_PAGES):
        changed = False
        for target, sources in edges.items():
            source_depths = [depths[source] for source in sources if source in depths]
            if not source_depths:
                continue
            candidate = min(source_depths) + 1
            if target not in depths or candidate < depths[target]:
                depths[target] = candidate
                changed = True
        if not changed:
            break
    return depths


def enrich_pages_with_reachability_provenance(
    pages: list[dict[str, Any]],
    discovery: dict[str, Any],
    *,
    seed_url: str,
) -> list[dict[str, Any]]:
    """Attach B11 provenance to retained assessed pages in place.

    The number/order of pages is unchanged. All counts are scoped to verified
    links observed on accepted pages inside the retained Standard-150 sample.
    """
    if not isinstance(pages, list) or len(pages) > MAX_ASSESSED_PAGES:
        raise ValueError("Expected at most 150 assessed pages")
    if any(not isinstance(page, dict) for page in pages):
        raise ValueError("Expected page dictionaries")
    if not isinstance(discovery, dict) or len(discovery) > MAX_DISCOVERY_TARGETS:
        raise ValueError("Discovery graph exceeds the bounded Standard-150 frontier")

    accepted_sources = _accepted_source_urls(pages)
    depths = observed_crawl_depths(pages, discovery, seed_url=seed_url)
    original_count = len(pages)

    for page in pages:
        request_url = _page_request_url(page)
        record = discovery.get(request_url)
        record = record if isinstance(record, dict) else {}
        internal_sources = [
            source
            for source in _dedupe(record.get(_INTERNAL_SOURCES))
            if source in accepted_sources
        ]
        navigation_sources = [
            source
            for source in _dedupe(record.get(_NAV_SOURCES))
            if source in internal_sources
        ]
        non_navigation_sources = [
            source
            for source in _dedupe(record.get(_NON_NAV_SOURCES))
            if source in internal_sources
        ]
        unknown_navigation_sources = [
            source
            for source in _dedupe(record.get(_UNKNOWN_NAV_SOURCES))
            if source in internal_sources
        ]

        if not _usable_html_page(page):
            evidence_state = "not_verified"
            observed_inlinks: int | None = None
            navigation_state: bool | None = None
            depth: int | None = None
            internal_sources = []
            navigation_sources = []
            non_navigation_sources = []
            unknown_navigation_sources = []
        else:
            evidence_state = "observed_sample"
            observed_inlinks = len(internal_sources)
            depth = depths.get(request_url)
            if navigation_sources:
                navigation_state = True
            elif unknown_navigation_sources:
                navigation_state = None
            elif internal_sources and set(internal_sources).issubset(set(non_navigation_sources)):
                navigation_state = False
            else:
                navigation_state = None

        page.update(
            {
                "reachability_provenance_version": REACHABILITY_PROVENANCE_VERSION,
                "reachability_scope": REACHABILITY_SCOPE,
                "reachability_evidence_state": evidence_state,
                "observed_internal_inlink_count": observed_inlinks,
                "internal_source_pages": internal_sources[:MAX_SOURCE_SAMPLES],
                "internal_source_pages_truncated": len(internal_sources) > MAX_SOURCE_SAMPLES,
                "navigation_presence": navigation_state,
                "navigation_source_pages": navigation_sources[:MAX_SOURCE_SAMPLES],
                "crawl_depth": depth,
                # This explicit negative capability prevents downstream copy from
                # turning a bounded sample observation into a sitewide claim.
                "sitewide_orphan_claim": False,
            }
        )

    if len(pages) != original_count:
        raise AssertionError("Reachability enrichment must not alter assessed pages")
    return pages


def enrich_pages_from_retained_link_evidence(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build B11 graph evidence from retained raw-link observations after page capping.

    ``extract_page`` temporarily retains only target URL identity plus semantic
    navigation presence on accepted HTML. This adapter runs after the final
    Standard-150 page set is known, projects edges only when both source and
    target are retained assessed pages, and then removes the private link cache
    before the scan result can be returned or persisted.
    """
    if not isinstance(pages, list) or len(pages) > MAX_ASSESSED_PAGES:
        raise ValueError("Expected at most 150 assessed pages")
    if any(not isinstance(page, dict) for page in pages):
        raise ValueError("Expected page dictionaries")

    retained_urls = {_page_request_url(page) for page in pages if _page_request_url(page)}
    discovery = {url: ensure_reachability_record({}) for url in retained_urls}
    seed_url = ""
    for page in pages:
        request_url = _page_request_url(page)
        if not request_url:
            continue
        if not seed_url and "seed" in set(page.get("discovered_from") or []):
            seed_url = request_url
        source_usable = _usable_html_page(page)
        raw_links = page.get(_PRIVATE_LINKS)
        if not isinstance(raw_links, list):
            continue
        for link in raw_links[:MAX_OUTGOING_LINKS_PER_SOURCE]:
            if not isinstance(link, dict):
                continue
            target = _text(link.get("href"))
            if target not in retained_urls:
                continue
            navigation = link.get("navigation_presence")
            navigation = navigation if isinstance(navigation, bool) else None
            record_internal_link_observation(
                discovery[target],
                source_url=request_url,
                source_usable_html=source_usable,
                navigation_presence=navigation,
            )

    try:
        return enrich_pages_with_reachability_provenance(
            pages,
            discovery,
            seed_url=seed_url,
        )
    finally:
        for page in pages:
            page.pop(_PRIVATE_LINKS, None)
