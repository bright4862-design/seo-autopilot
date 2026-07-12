import re
from urllib.parse import urlparse


MARKET_SEGMENT_RE = re.compile(r"^[a-z]{2}(?:-[a-z]{2})?$", re.I)


def normalize_scope_prefix(value: str) -> str:
    raw = str(value or "").strip()
    if raw.startswith(("http://", "https://")):
        raw = urlparse(raw).path or "/"
    clean = "/" + raw.strip("/") if raw and raw != "/" else "/"
    return clean.rstrip("/") if clean != "/" else "/"


def path_within_scope(path: str, scope_prefix: str) -> bool:
    prefix = normalize_scope_prefix(scope_prefix)
    if prefix == "/":
        return True
    candidate = normalize_scope_prefix(path)
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
