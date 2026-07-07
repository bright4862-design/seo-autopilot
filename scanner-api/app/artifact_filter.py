import re
from urllib.parse import unquote, urlparse

MAX_ARTIFACT_EVIDENCE = 50
_BASE64_SEGMENT = re.compile(r"/(?:L2|aHR0|[A-Za-z0-9+/_=-]{36,}={0,2})(?:/|$)")


def is_artifact_url(url: str) -> bool:
    text = str(url or "").strip()
    if not text:
        return False

    try:
        path = urlparse(text).path or text
    except Exception:
        path = text

    decoded = unquote(path)
    lowered = path.lower()

    if _BASE64_SEGMENT.search(path):
        return True

    if "%2f" in lowered and ("%3a" in lowered or "http" in decoded.lower()):
        return True

    for segment in [s for s in path.split("/") if s]:
        if len(segment) >= 32 and re.fullmatch(r"[A-Za-z0-9+/_=-]+={0,2}", segment):
            return True

    return False


def record_artifact(target: list[dict], url: str, discovered_from: str, source_page: str = "", link_text: str = "") -> None:
    if len(target) >= MAX_ARTIFACT_EVIDENCE:
        return
    target.append({
        "url": str(url or "")[:500],
        "path": urlparse(str(url or "")).path[:500],
        "url_confidence": "crawler_artifact",
        "url_suspicion_reasons": ["encoded_or_base64_like_path"],
        "discovered_from": [discovered_from or "unknown"],
        "source_pages": [source_page] if source_page else [],
        "link_text_samples": [link_text[:160]] if link_text else [],
        "suppressed_from_crawl": True,
    })
