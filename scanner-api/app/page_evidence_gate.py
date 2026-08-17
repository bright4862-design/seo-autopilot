"Shared page-evidence classification for scanner and review finding gates."

from __future__ import annotations

import re
from typing import Any

PAGE_EVIDENCE_GATE_VERSION = "page_evidence_gate_v1"
PAGE_EVIDENCE_CLASSES = {
    "usable_html",
    "failed_access",
    "redirected_terminal",
    "non_html",
    "incomplete_html",
}

_CHALLENGE_MARKERS = (
    "cf-chl-",
    "cloudflare ray id",
    "checking your browser",
    "connection verification",
    "enable javascript and cookies to continue",
    "verify you are human",
)

# Some legitimate storefronts embed bot-blocker configuration in script/JSON
# that contains the literal phrase "Access Denied". Treat that phrase as a
# challenge only when it is rendered as page content, rather than matching an
# incidental configuration string anywhere in a large HTML document.
_VISIBLE_ACCESS_DENIED = re.compile(r">\s*access\s+denied(?:\s*[.!:–—-]*)?\s*<", re.I)

def _status(page_or_status: Any) -> int:
    if isinstance(page_or_status, dict):
        value = page_or_status.get("status_code") or page_or_status.get("status") or 0
    else:
        value = page_or_status or 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0

def _looks_like_html(source: str) -> bool:
    return bool(re.search(r"<(?:!doctype\s+html|html|head|body)(?:\s|>)", source, re.I))

def _looks_like_challenge(source: str) -> bool:
    lowered = source.lower()
    return any(marker in lowered for marker in _CHALLENGE_MARKERS) or bool(_VISIBLE_ACCESS_DENIED.search(source))

def classify_page_evidence(
    *,
    status_code: int,
    content_type: str = "",
    fetch_error: str = "",
    html: str = "",
    body_truncated: bool = False,
) -> str:
    status = _status(status_code)
    error = str(fetch_error or "").strip()
    source = str(html or "")
    content_type_lower = str(content_type or "").lower()

    if error or status == 0 or status >= 400:
        return "failed_access"
    if 300 <= status < 400:
        return "redirected_terminal"
    if status != 200:
        return "incomplete_html"
    if content_type_lower and "html" not in content_type_lower and "xhtml" not in content_type_lower:
        return "non_html"
    if body_truncated or not source.strip():
        return "incomplete_html"
    if _looks_like_challenge(source):
        return "failed_access"
    if not content_type_lower and not _looks_like_html(source):
        return "non_html"
    return "usable_html"

def page_evidence_class(page: dict[str, Any]) -> str:
    stamped = str(page.get("page_evidence_class") or "")
    if stamped in PAGE_EVIDENCE_CLASSES:
        return stamped
    status = _status(page)
    error = str(page.get("fetch_error") or page.get("error") or "")
    content_type = str(page.get("content_type") or "")
    html_size = int(page.get("html_size") or 0)
    if error or status == 0 or status >= 400:
        return "failed_access"
    if 300 <= status < 400:
        return "redirected_terminal"
    if status != 200:
        return "incomplete_html"
    if content_type and "html" not in content_type.lower() and "xhtml" not in content_type.lower():
        return "non_html"
    if page.get("raw_html_truncated") is True or page.get("html_truncated") is True:
        return "incomplete_html"
    if html_size <= 0 and not any(page.get(key) for key in ("title", "h1", "meta_description", "canonical")):
        return "incomplete_html"
    return "usable_html"

def page_has_usable_html(page: dict[str, Any]) -> bool:
    return page_evidence_class(page) == "usable_html"
