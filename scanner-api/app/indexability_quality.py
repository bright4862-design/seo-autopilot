from __future__ import annotations

import re
from collections import Counter
from urllib.parse import urlparse


INDEXABILITY_QUALITY_VERSION = "indexability_quality_v1"
SOFT_404_MAX_WORDS = 250
SOFT_404_THIN_WORDS = 120

_ERROR_PATTERNS = (
    ("http_404_marker", re.compile(r"(?:^|\W)404(?:\W|$)", re.I)),
    ("page_not_found", re.compile(r"\bpage\s+(?:not\s+found|introuvable|non\s+trouv[ée]e?|no\s+encontrada|nicht\s+gefunden)\b", re.I)),
    ("not_found", re.compile(r"\bnot\s+found\b", re.I)),
    ("does_not_exist", re.compile(r"\b(?:does\s+not|doesn't)\s+exist\b", re.I)),
    ("could_not_find", re.compile(r"\b(?:could\s+not|can't|cannot)\s+find\b", re.I)),
)
_PATH_ERROR_PATTERN = re.compile(r"(?:^|/)(?:404|not-found|page-not-found|page-introuvable)(?:/|$)", re.I)


def _clean(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _directive_sources(page: dict) -> list[tuple[str, set[str]]]:
    meta = page.get("robots_meta_directives") or {}
    headers = page.get("x_robots_tag_directives") or {}
    sources = [
        ("meta robots", set(meta.get("robots") or [])),
        ("meta googlebot", set(meta.get("googlebot") or [])),
        ("X-Robots-Tag", set(headers.get("robots") or [])),
        ("X-Robots-Tag googlebot", set(headers.get("googlebot") or [])),
    ]
    return [(label, {str(item).lower() for item in directives}) for label, directives in sources if directives]


def _soft_404_signals(page: dict) -> list[str]:
    status_code = int(page.get("status_code") or 0)
    if not (200 <= status_code < 300) or page.get("fetch_error"):
        return []
    if int(page.get("redirect_hop_count") or 0) > 0:
        return []
    content_type = str(page.get("content_type") or "").lower()
    if content_type and "html" not in content_type:
        return []

    word_count = int(page.get("word_count") or 0)
    if word_count > SOFT_404_MAX_WORDS:
        return []

    field_hits: list[str] = []
    for field in ("title", "h1"):
        text = _clean(page.get(field))
        if not text:
            continue
        matched = next((label for label, pattern in _ERROR_PATTERNS if pattern.search(text)), "")
        if matched:
            field_hits.append(f"{field}:{matched}")

    path = urlparse(str(page.get("final_url") or page.get("url") or "")).path or "/"
    path_hit = bool(_PATH_ERROR_PATTERN.search(path))
    high_confidence = bool(field_hits) and (
        len(field_hits) >= 2
        or word_count <= SOFT_404_THIN_WORDS
        or path_hit
    )
    if not high_confidence:
        return []

    signals = list(field_hits)
    signals.append(f"thin_content:{word_count}_words")
    if path_hit:
        signals.append("error_like_url_path")
    return signals


def annotate_indexability_quality(page: dict) -> dict:
    original_state = str(page.get("indexability_state") or "")
    page["indexability_quality_version"] = INDEXABILITY_QUALITY_VERSION
    page["indexability_state_before_quality"] = original_state

    target_state = str(page.get("canonical_target_state") or "")
    canonicalized = (
        str(page.get("canonical_status") or "") == "canonical_to_different_url"
        and target_state in {"valid", "canonical_chain"}
        and original_state == "Indexable"
    )
    page["canonicalized_by_valid_target"] = canonicalized
    if canonicalized:
        page["indexable"] = False
        page["indexability_state"] = "Canonicalized"
        page["robots_indexability_status"] = "canonicalized"

    sources = _directive_sources(page)
    index_sources = [label for label, directives in sources if "index" in directives]
    noindex_sources = [label for label, directives in sources if {"noindex", "none"} & directives]

    conflicts: list[str] = []
    conflict_signals: list[str] = []
    if index_sources and noindex_sources:
        conflicts.append("robots_directive_conflict")
        conflict_signals.append(
            f"index from {', '.join(index_sources)}; noindex from {', '.join(noindex_sources)}"
        )

    effective = {str(item).lower() for item in (page.get("effective_search_robots_directives") or [])}
    if {"noindex", "none"} & effective and str(page.get("canonical_status") or "") == "canonical_to_different_url":
        conflicts.append("noindex_with_canonical")
        conflict_signals.append("noindex is combined with a canonical to a different URL")

    page["indexability_conflicts"] = list(dict.fromkeys(conflicts))
    page["indexability_conflict_signals"] = list(dict.fromkeys(conflict_signals))

    soft_404_signals = _soft_404_signals(page)
    page["soft_404_suspected"] = bool(soft_404_signals)
    page["soft_404_signals"] = soft_404_signals
    page["soft_404_confidence"] = 92 if soft_404_signals else 0
    if soft_404_signals and str(page.get("indexability_state") or "") in {"Indexable", "Canonicalized"}:
        page["indexable"] = False
        page["indexability_state"] = "Soft 404"
        page["robots_indexability_status"] = "soft_404"

    return page


def build_indexability_quality_findings(page: dict, create_finding) -> list[dict]:
    findings: list[dict] = []
    path = str(page.get("path") or "/")
    sources = set(page.get("discovered_from") or [])

    if page.get("soft_404_suspected"):
        priority = "high" if "sitemap" in sources else "medium"
        finding = create_finding(
            rule="soft_404",
            category="indexability",
            priority=priority,
            title="Return a real 404 or 410 for a missing page",
            page_url=path,
            current_value="; ".join(page.get("soft_404_signals") or []),
            explanation=(
                "This URL returned HTTP 200, but its title or main heading says the page is missing and the page contains very little content. "
                "Search engines may treat it as a soft 404."
            ),
            recommendation=(
                "Return HTTP 404 or 410 when the page is genuinely gone, or restore substantial page content when the URL should exist. "
                "Remove missing URLs from sitemaps and update internal links."
            ),
            difficulty="developer",
            source_pages=page.get("source_pages", []),
            link_text_samples=page.get("link_text_samples", []),
        )
        finding.update({
            "soft_404_signals": list(page.get("soft_404_signals") or []),
            "soft_404_confidence": int(page.get("soft_404_confidence") or 0),
            "evidence_status": "confirmed_by_high_confidence_heuristic",
            "verification_state": "verified",
            "confidence_score": int(page.get("soft_404_confidence") or 92),
        })
        findings.append(finding)

    conflicts = set(page.get("indexability_conflicts") or [])
    signals = list(page.get("indexability_conflict_signals") or [])
    if "robots_directive_conflict" in conflicts:
        finding = create_finding(
            rule="robots_directive_conflict",
            category="indexability",
            priority="high" if "sitemap" in sources else "medium",
            title="Resolve conflicting index and noindex directives",
            page_url=path,
            current_value="; ".join(signals),
            explanation=(
                "Different robots meta or X-Robots-Tag sources explicitly request both index and noindex behavior for Google search."
            ),
            recommendation=(
                "Choose one intended indexing policy and make the generic robots, Googlebot meta, and X-Robots-Tag directives agree."
            ),
            difficulty="developer",
            source_pages=page.get("source_pages", []),
            link_text_samples=page.get("link_text_samples", []),
        )
        finding.update({
            "indexability_conflicts": sorted(conflicts),
            "indexability_conflict_signals": signals,
            "evidence_status": "confirmed",
            "verification_state": "verified",
            "confidence_score": 96,
        })
        findings.append(finding)

    if "noindex_with_canonical" in conflicts:
        finding = create_finding(
            rule="noindex_canonical_conflict",
            category="indexability",
            priority="high" if "sitemap" in sources else "medium",
            title="Choose between noindex and canonical consolidation",
            page_url=path,
            current_value=f"noindex with canonical {page.get('canonical') or ''}",
            explanation=(
                "The page combines a noindex instruction with a canonical pointing to another URL. Search engines can interpret these signals inconsistently."
            ),
            recommendation=(
                "Use noindex when the page should disappear from search, or use a crawlable canonical when signals should consolidate to an equivalent URL. Avoid combining both."
            ),
            difficulty="developer",
            source_pages=page.get("source_pages", []),
            link_text_samples=page.get("link_text_samples", []),
        )
        finding.update({
            "indexability_conflicts": sorted(conflicts),
            "indexability_conflict_signals": signals,
            "evidence_status": "confirmed",
            "verification_state": "verified",
            "confidence_score": 94,
        })
        findings.append(finding)

    if page.get("canonicalized_by_valid_target") and "sitemap" in sources:
        finding = create_finding(
            rule="sitemap_canonicalized_url",
            category="indexability",
            priority="medium",
            title="Replace a canonicalized URL in the sitemap",
            page_url=path,
            current_value=str(page.get("canonical") or "Canonicalized"),
            explanation=(
                "The sitemap lists a URL whose validated canonical points to a different usable preferred URL."
            ),
            recommendation=(
                "Replace this sitemap entry with the final canonical URL and keep only indexable preferred URLs in XML sitemaps."
            ),
            difficulty="developer",
            source_pages=page.get("source_pages", []),
            link_text_samples=page.get("link_text_samples", []),
        )
        finding.update({
            "canonical_target_state": page.get("canonical_target_state"),
            "canonical_target_url": page.get("canonical_target_url") or page.get("canonical"),
            "evidence_status": "confirmed",
            "verification_state": "verified",
            "confidence_score": 95,
        })
        findings.append(finding)

    return findings


def summarize_indexability_quality(pages: list[dict]) -> dict:
    state_counts = Counter(str(page.get("indexability_state") or "Unknown") for page in pages)
    conflict_counts = Counter(
        conflict
        for page in pages
        for conflict in (page.get("indexability_conflicts") or [])
    )
    soft_404_pages = [page for page in pages if page.get("soft_404_suspected")]
    canonicalized_pages = [page for page in pages if page.get("canonicalized_by_valid_target")]
    return {
        "version": INDEXABILITY_QUALITY_VERSION,
        "state_counts": dict(sorted(state_counts.items())),
        "soft_404_count": len(soft_404_pages),
        "canonicalized_count": len(canonicalized_pages),
        "conflict_counts": dict(sorted(conflict_counts.items())),
        "representative_soft_404s": [
            page.get("path") or page.get("url") for page in soft_404_pages[:20]
        ],
        "representative_conflicts": [
            {
                "page": page.get("path") or page.get("url"),
                "conflicts": list(page.get("indexability_conflicts") or []),
            }
            for page in pages
            if page.get("indexability_conflicts")
        ][:20],
    }
