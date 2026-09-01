import re
from urllib.parse import unquote, urlparse


MARKET_SCOPE_VERSION = "market_scope_v2_traversal_safe_path_prefix"
MARKET_SEGMENT_RE = re.compile(r"^[a-z]{2}(?:-[a-z]{2})?$", re.I)


def normalize_scope_prefix(value: str) -> str:
    raw = str(value or "").strip()
    if raw.startswith(("http://", "https://")):
        raw = urlparse(raw).path or "/"
    clean = "/" + raw.strip("/") if raw and raw != "/" else "/"
    return clean.rstrip("/") if clean != "/" else "/"


def _safe_scope_path(path: str) -> str:
    """Return a normalized path only when no segment can escape after decoding."""
    raw = str(path or "/").split("?", 1)[0].split("#", 1)[0]
    segments = [segment for segment in raw.split("/") if segment]
    for segment in segments:
        decoded = segment
        for _ in range(3):
            try:
                next_decoded = unquote(decoded)
            except Exception:
                return ""
            if next_decoded == decoded:
                break
            decoded = next_decoded
        if decoded in {".", ".."} or "/" in decoded or "\\" in decoded:
            return ""
    return "/" + "/".join(segments) if segments else "/"


def path_within_scope(path: str, scope_prefix: str) -> bool:
    prefix = normalize_scope_prefix(scope_prefix)
    candidate = _safe_scope_path(path)
    if not candidate:
        return False
    if prefix == "/":
        return True
    return candidate == prefix or candidate.startswith(prefix + "/")


def market_pair_prefix(value: str) -> str:
    raw = str(value or "")
    path = urlparse(raw).path if raw.startswith(("http://", "https://")) else raw
    segments = [segment.lower() for segment in str(path or "").split("/") if segment]
    if len(segments) >= 2 and MARKET_SEGMENT_RE.fullmatch(segments[0]) and MARKET_SEGMENT_RE.fullmatch(segments[1]):
        return f"/{segments[0]}/{segments[1]}"
    return ""


def strip_market_locale_prefix(value: str) -> str:
    raw = str(value or "")
    path = urlparse(raw).path if raw.startswith(("http://", "https://")) else raw
    segments = [segment for segment in str(path or "").split("/") if segment]
    remove = 0
    if len(segments) >= 2 and MARKET_SEGMENT_RE.fullmatch(segments[0]) and MARKET_SEGMENT_RE.fullmatch(segments[1]):
        remove = 2
    elif segments and MARKET_SEGMENT_RE.fullmatch(segments[0]):
        remove = 1
    remaining = segments[remove:]
    return "/" + "/".join(remaining) if remaining else "/"
