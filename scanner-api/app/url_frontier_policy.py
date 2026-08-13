from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


FRONTIER_POLICY_VERSION = "url_frontier_policy_v1_conservative_trap_guard"

# Parameters whose value never changes the underlying document and should not
# create a second crawl identity.
TRACKING_PARAMS = {
    "fbclid", "gclid", "dclid", "msclkid", "yclid", "gbraid", "wbraid",
    "mc_cid", "mc_eid", "igshid", "srsltid", "gad_source",
}

# Stateful/session identifiers should not multiply crawl identities. They are
# stripped rather than causing the URL to be skipped.
SESSION_PARAMS = {
    "phpsessid", "jsessionid", "sessionid", "session_id", "sid",
}

# Known frontend/page-builder controls that can expose effectively unbounded
# URL sequences. These are blocked before enqueue.
EXACT_TRAP_PARAMS = {
    "infinity",       # Jetpack infinite-scroll cursor
}
TRAP_PARAM_PREFIXES = (
    "e-page-",        # Elementor loop/posts pagination widgets
    "e-filter-",      # Elementor filter widgets
)


@dataclass(frozen=True)
class FrontierDecision:
    url: str
    allowed: bool
    changed: bool
    reason: str = ""
    removed_params: tuple[str, ...] = ()


def _is_locale_segment(segment: str) -> bool:
    value = segment.lower().strip()
    # Keep paths such as /fr/fr/, /en/us/, and locale tokens intact. These are
    # common on multi-market sites and must not be mistaken for crawler loops.
    return len(value) in {2, 5} and (
        (len(value) == 2 and value.isalpha())
        or (len(value) == 5 and value[2] in {"-", "_"})
    )


def _repeating_path_trap(path: str) -> bool:
    segments = [part.lower() for part in path.split("/") if part]
    if len(segments) < 2:
        return False

    # Conservative adjacent-repeat guard: /our-team/our-team/. Ignore locale
    # segments so legitimate /fr/fr/ market structures remain crawlable.
    for left, right in zip(segments, segments[1:]):
        if left == right and len(left) >= 4 and not _is_locale_segment(left):
            return True

    # Repeated two-segment cycle: /case-studies/team/case-studies/team/.
    if len(segments) >= 4:
        for idx in range(len(segments) - 3):
            a, b, c, d = segments[idx : idx + 4]
            if a == c and b == d and min(len(a), len(b)) >= 3:
                if not (_is_locale_segment(a) or _is_locale_segment(b)):
                    return True
    return False


def classify_frontier_url(url: str) -> FrontierDecision:
    """Normalize crawl identity and reject only high-confidence URL traps.

    This function is intentionally narrower than an SEO canonicalizer. It does
    not remove ordinary business/query parameters and does not guess whether a
    faceted URL should be indexable. Its job is only to keep obvious crawler
    traps and pure tracking/session noise out of the frontier.
    """
    raw = str(url or "").strip()
    if not raw:
        return FrontierDecision(url=raw, allowed=False, changed=False, reason="empty_url")

    try:
        parts = urlsplit(raw)
    except ValueError:
        return FrontierDecision(url=raw, allowed=False, changed=False, reason="malformed_url")

    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        return FrontierDecision(url=raw, allowed=False, changed=False, reason="non_http_url")

    if _repeating_path_trap(parts.path or "/"):
        return FrontierDecision(url=raw, allowed=False, changed=False, reason="repeating_path_cycle")

    kept: list[tuple[str, str]] = []
    removed: list[str] = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        normalized_key = key.lower().strip()
        if normalized_key.startswith("utm_") or normalized_key in TRACKING_PARAMS or normalized_key in SESSION_PARAMS:
            removed.append(key)
            continue
        if normalized_key in EXACT_TRAP_PARAMS or any(normalized_key.startswith(prefix) for prefix in TRAP_PARAM_PREFIXES):
            return FrontierDecision(
                url=raw,
                allowed=False,
                changed=False,
                reason=f"crawler_trap_param:{normalized_key}",
            )
        kept.append((key, value))

    # Nothing was stripped, so return the URL byte-for-byte. Re-serializing an
    # unchanged URL is not free: urlunsplit would rewrite an empty path to "/",
    # collapsing https://example.com and https://example.com/ into one crawl
    # identity. normalize_url() deliberately keeps those distinct (it rstrips
    # only when path != "/"), and the final-URL dedup layer counts them as a
    # duplicate pair when both resolve to the same final URL. Collapsing here
    # would silently zero final_url_duplicates_deduped.
    if not removed:
        return FrontierDecision(url=raw, allowed=True, changed=False)

    # Only the query is rewritten. The path is preserved exactly as received so
    # trailing-slash identity, and every accounting layer downstream that
    # depends on it, is unaffected.
    normalized = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept, doseq=True), ""))
    return FrontierDecision(
        url=normalized,
        allowed=True,
        changed=normalized != raw,
        removed_params=tuple(dict.fromkeys(removed)),
    )
