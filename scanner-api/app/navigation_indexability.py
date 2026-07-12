from __future__ import annotations

from collections import Counter
import re
from urllib.parse import parse_qsl, urlparse


NAVIGATION_INDEXABILITY_VERSION = "navigation_indexability_v1"
MIN_GROUP_SIZE = 3

PAGINATION_KEYS = {
    "page",
    "paged",
    "page_number",
    "pagenum",
    "pg",
    "offset",
    "start",
}
FACET_KEYS = {
    "brand",
    "category",
    "collection",
    "color",
    "colour",
    "facet",
    "facets",
    "filter",
    "filters",
    "material",
    "max_price",
    "min_price",
    "order",
    "orderby",
    "price",
    "product_type",
    "size",
    "sort",
    "style",
    "tag",
    "type",
    "vendor",
}
TRACKING_KEYS = {
    "dclid",
    "fbclid",
    "gclid",
    "gbraid",
    "mc_cid",
    "mc_eid",
    "msclkid",
    "ref",
    "source",
    "wbraid",
}
PAGINATION_PATH = re.compile(r"/(?:page|paged|p)/\d+/?$|/page-\d+/?$", re.I)


def _normalized_key(value: str) -> str:
    return str(value or "").strip().lower().replace("[]", "")


def _is_tracking_key(key: str) -> bool:
    return key in TRACKING_KEYS or key.startswith("utm_")


def _is_facet_key(key: str) -> bool:
    return (
        key in FACET_KEYS
        or key.startswith("filter_")
        or key.startswith("filter[")
        or key.startswith("facet_")
        or key.startswith("attribute_")
        or key.startswith("pa_")
    )


def _page_url(page: dict) -> str:
    return str(page.get("url") or page.get("final_url") or "")


def _display_url(page: dict) -> str:
    raw = _page_url(page)
    try:
        parsed = urlparse(raw)
    except Exception:
        return str(page.get("path") or raw or "/")
    path = parsed.path or "/"
    return f"{path}?{parsed.query}" if parsed.query else path


def _is_redirect(page: dict) -> bool:
    return bool(
        int(page.get("redirect_hop_count") or 0) > 0
        or str(page.get("indexability_state") or "") == "Redirected"
        or str(page.get("redirect_state") or "").startswith("redirect_")
    )


def annotate_navigation_indexability(page: dict) -> dict:
    raw_url = _page_url(page)
    try:
        parsed = urlparse(raw_url)
        pairs = parse_qsl(parsed.query, keep_blank_values=True)
        path = parsed.path or "/"
    except Exception:
        pairs = []
        path = str(page.get("path") or "/")

    query_keys = [_normalized_key(key) for key, _ in pairs if _normalized_key(key)]
    pagination_keys = sorted({key for key in query_keys if key in PAGINATION_KEYS})
    facet_keys = sorted({key for key in query_keys if _is_facet_key(key)})
    tracking_only = bool(query_keys) and all(_is_tracking_key(key) for key in query_keys)
    pagination = bool(pagination_keys or PAGINATION_PATH.search(path))
    faceted = bool(facet_keys)

    sources = set(page.get("discovered_from") or [])
    status_code = int(page.get("status_code") or 0)
    clean_indexable = (
        200 <= status_code < 300
        and page.get("indexable") is True
        and str(page.get("indexability_state") or "") == "Indexable"
        and not _is_redirect(page)
        and not page.get("soft_404_suspected")
        and not page.get("canonicalized_by_valid_target")
    )

    if page.get("trust_discovery_probe"):
        orphan_state = "excluded_trust_probe"
    elif "seed" in sources:
        orphan_state = "excluded_seed"
    elif "sitemap" not in sources:
        orphan_state = "not_sitemap_discovered"
    elif "internal_link" in sources:
        orphan_state = "internally_linked_in_sample"
    elif pagination:
        orphan_state = "excluded_pagination"
    elif faceted:
        orphan_state = "excluded_faceted_navigation"
    elif tracking_only:
        orphan_state = "excluded_tracking_parameters"
    elif query_keys:
        orphan_state = "excluded_parameterized_url"
    elif not clean_indexable:
        orphan_state = "excluded_non_indexable"
    else:
        orphan_state = "candidate_needs_verification"

    page.update({
        "navigation_indexability_version": NAVIGATION_INDEXABILITY_VERSION,
        "navigation_query_keys": sorted(set(query_keys)),
        "pagination_query_keys": pagination_keys,
        "facet_query_keys": facet_keys,
        "pagination_url": pagination,
        "faceted_navigation_url": faceted,
        "tracking_only_url": tracking_only,
        "orphan_evidence_state": orphan_state,
        "potential_orphan_in_sample": orphan_state == "candidate_needs_verification",
        "indexable_faceted_url": bool(faceted and clean_indexable),
    })
    return page


def _verification_finding(
    create_finding,
    *,
    rule: str,
    title: str,
    current_value: str,
    explanation: str,
    recommendation: str,
    affected_pages: list[str],
    limitation_code: str,
    confidence_score: int,
) -> dict:
    finding = create_finding(
        rule=rule,
        category="indexability",
        priority="low",
        title=title,
        page_url="",
        current_value=current_value,
        explanation=explanation,
        recommendation=recommendation,
        difficulty="developer",
    )
    finding.update({
        "affected_pages": affected_pages[:150],
        "page_count": len(affected_pages),
        "evidence_status": "needs_verification",
        "verification_state": "needs_verification",
        "limitation_code": limitation_code,
        "confidence_score": confidence_score,
        "score_impact": 0,
        "non_scoring": True,
        "navigation_indexability_version": NAVIGATION_INDEXABILITY_VERSION,
    })
    return finding


def build_navigation_indexability_findings(pages: list[dict], create_finding) -> list[dict]:
    orphan_candidates = [
        page for page in pages
        if page.get("potential_orphan_in_sample") and not page.get("trust_discovery_probe")
    ]
    faceted_candidates = [
        page for page in pages
        if page.get("indexable_faceted_url") and not page.get("trust_discovery_probe")
    ]

    findings: list[dict] = []
    if len(orphan_candidates) >= MIN_GROUP_SIZE:
        affected = list(dict.fromkeys(_display_url(page) for page in orphan_candidates))
        findings.append(_verification_finding(
            create_finding,
            rule="potential_orphan_pages",
            title="Verify sitemap-only pages are internally linked",
            current_value=f"{len(affected)} indexable sitemap URLs were not linked in the sampled crawl",
            explanation=(
                "The representative crawl found these URLs in XML sitemaps but did not encounter internal links to them. "
                "Because the crawl is sampled, this is a verification lead rather than proof that the pages are orphaned."
            ),
            recommendation=(
                "Confirm the URLs with a complete internal-link crawl, server logs, or Search Console. Add useful contextual "
                "links to important pages that are genuinely isolated."
            ),
            affected_pages=affected,
            limitation_code="sampled_crawl_cannot_prove_orphan",
            confidence_score=64,
        ))

    if len(faceted_candidates) >= MIN_GROUP_SIZE:
        affected = list(dict.fromkeys(_display_url(page) for page in faceted_candidates))
        findings.append(_verification_finding(
            create_finding,
            rule="indexable_faceted_navigation",
            title="Review indexable filter and sort URLs",
            current_value=f"{len(affected)} sampled parameter URLs appear indexable",
            explanation=(
                "Several filter, sort, or attribute URLs returned indexable pages. Some faceted URLs are intentional landing "
                "pages, so this evidence is not automatically a defect."
            ),
            recommendation=(
                "Decide which parameter combinations deserve search visibility. Keep valuable landing pages indexable and "
                "canonical; consolidate, noindex, or block low-value combinations without preventing discovery of products."
            ),
            affected_pages=affected,
            limitation_code="faceted_navigation_requires_strategy_review",
            confidence_score=72,
        ))

    return findings


def summarize_navigation_indexability(pages: list[dict]) -> dict:
    orphan_states = Counter(str(page.get("orphan_evidence_state") or "unknown") for page in pages)
    return {
        "version": NAVIGATION_INDEXABILITY_VERSION,
        "pages_evaluated": len(pages),
        "pagination_pages": sum(1 for page in pages if page.get("pagination_url")),
        "faceted_navigation_pages": sum(1 for page in pages if page.get("faceted_navigation_url")),
        "tracking_only_pages": sum(1 for page in pages if page.get("tracking_only_url")),
        "potential_orphan_candidates": sum(1 for page in pages if page.get("potential_orphan_in_sample")),
        "indexable_faceted_pages": sum(1 for page in pages if page.get("indexable_faceted_url")),
        "orphan_evidence_state_counts": dict(sorted(orphan_states.items())),
        "representative_orphan_candidates": [
            _display_url(page) for page in pages if page.get("potential_orphan_in_sample")
        ][:20],
        "representative_faceted_pages": [
            _display_url(page) for page in pages if page.get("indexable_faceted_url")
        ][:20],
        "orphan_evidence_limitation": "A representative sampled crawl cannot prove that a sitemap-only URL has no internal links anywhere on the site.",
    }
