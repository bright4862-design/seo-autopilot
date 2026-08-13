from __future__ import annotations

from collections import Counter
from urllib.parse import parse_qsl, unquote, urlparse

from . import artifact_filter as _artifact_filter

CRAWL_TRAP_GUARD_VERSION = "crawl_trap_guard_v1_high_confidence_single_url"

# Deliberately conservative. These thresholds suppress only pathological URLs
# that are already poor candidates for page-level SEO evidence. Normal filters,
# pagination, long human slugs and ordinary faceted navigation remain crawlable.
MAX_CRAWLABLE_URL_LENGTH = 4096
MAX_CRAWLABLE_PATH_SEGMENTS = 40
MAX_REPEATED_PATH_SEGMENT = 8
MAX_QUERY_PAIRS = 20
MAX_REPEATED_QUERY_KEY = 6

_ORIGINAL_IS_ARTIFACT_URL = _artifact_filter.is_artifact_url
_ORIGINAL_RECORD_ARTIFACT = _artifact_filter.record_artifact
_INSTALLED = False


def crawl_trap_reason(url: str) -> str:
    """Return a reason only for high-confidence pathological URL shapes."""
    text = str(url or "").strip()
    if not text:
        return ""
    if len(text) > MAX_CRAWLABLE_URL_LENGTH:
        return "crawler_trap_oversized_url"

    try:
        parsed = urlparse(text)
        decoded_path = unquote(parsed.path or "/")
        segments = [segment for segment in decoded_path.split("/") if segment]
        query_pairs = parse_qsl(parsed.query or "", keep_blank_values=True)
    except Exception:
        return ""

    if len(segments) > MAX_CRAWLABLE_PATH_SEGMENTS:
        return "crawler_trap_path_depth"

    normalized_segments = [segment.strip().lower() for segment in segments if segment.strip()]
    if normalized_segments:
        counts = Counter(normalized_segments)
        if max(counts.values(), default=0) > MAX_REPEATED_PATH_SEGMENT:
            return "crawler_trap_repeated_path_segment"

    if len(query_pairs) > MAX_QUERY_PAIRS:
        return "crawler_trap_query_pair_explosion"

    query_key_counts = Counter(
        str(key or "").strip().lower()
        for key, _ in query_pairs
        if str(key or "").strip()
    )
    if max(query_key_counts.values(), default=0) > MAX_REPEATED_QUERY_KEY:
        return "crawler_trap_repeated_query_key"

    return ""


def is_crawl_trap_url(url: str) -> bool:
    return bool(crawl_trap_reason(url))


def _guarded_is_artifact_url(url: str) -> bool:
    return _ORIGINAL_IS_ARTIFACT_URL(url) or is_crawl_trap_url(url)


def _guarded_record_artifact(
    target: list[dict],
    url: str,
    discovered_from: str,
    source_page: str = "",
    link_text: str = "",
) -> None:
    if _ORIGINAL_IS_ARTIFACT_URL(url):
        _ORIGINAL_RECORD_ARTIFACT(target, url, discovered_from, source_page, link_text)
        return

    reason = crawl_trap_reason(url)
    if not reason:
        return
    if len(target) >= _artifact_filter.MAX_ARTIFACT_EVIDENCE:
        return

    target.append({
        "url": str(url or "")[:500],
        "path": urlparse(str(url or "")).path[:500],
        "url_confidence": "crawler_artifact",
        "url_suspicion_reasons": [reason],
        "discovered_from": [discovered_from or "unknown"],
        "source_pages": [source_page] if source_page else [],
        "link_text_samples": [link_text[:160]] if link_text else [],
        "suppressed_from_crawl": True,
        "guard_version": CRAWL_TRAP_GUARD_VERSION,
    })


def install() -> None:
    """Install once before scanner.py binds artifact-filter functions locally."""
    global _INSTALLED
    if _INSTALLED:
        return
    _artifact_filter.is_artifact_url = _guarded_is_artifact_url
    _artifact_filter.record_artifact = _guarded_record_artifact
    _INSTALLED = True
