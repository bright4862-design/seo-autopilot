"Shared page-evidence classification for scanner and review finding gates."

from __future__ import annotations

import re
from typing import Any, Mapping

from .transport_evidence import TRANSFER_BODY_BYTES_HEADER

PAGE_EVIDENCE_GATE_VERSION = "page_evidence_gate_v2_vendor_access_block"
PAGE_EVIDENCE_CLASSES = {
    "usable_html",
    "failed_access",
    "redirected_terminal",
    "non_html",
    "incomplete_html",
}

# The scanner forwards this bounded set from the in-memory response to the
# extraction seam. The transfer-body header is internal scanner evidence and is
# deliberately excluded from persisted access-block vendor evidence below.
PERSISTED_ACCESS_BLOCK_HEADER_ALLOWLIST = (
    "server",
    "cf-ray",
    "cf-mitigated",
    "sg-captcha",
    "x-datadome",
    "x-iinfo",
    "x-sucuri-id",
)
ACCESS_BLOCK_HEADER_ALLOWLIST = (
    *PERSISTED_ACCESS_BLOCK_HEADER_ALLOWLIST,
    TRANSFER_BODY_BYTES_HEADER,
)

_CHALLENGE_MARKERS = (
    "cf-chl-",
    "cloudflare ray id",
    "checking your browser",
    "connection verification",
    "enable javascript and cookies to continue",
    "verify you are human",
    "performing security verification",
)

# Some legitimate storefronts embed bot-blocker configuration in script/JSON
# that contains the literal phrase "Access Denied". Treat that phrase as a
# challenge only when it is rendered as page content, rather than matching an
# incidental configuration string anywhere in a large HTML document.
_VISIBLE_ACCESS_DENIED = re.compile(r">\s*access\s+denied(?:\s*[.!:–—-]*)?\s*<", re.I)
_SITEGROUND_META_REFRESH = re.compile(
    r"<meta\b(?=[^>]*\bhttp-equiv\s*=\s*['\"]?\s*refresh\b)"
    r"(?=[^>]*\/\.well-known\/sgcaptcha\/)[^>]*>",
    re.I,
)


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


def _headers_lower(headers: Mapping[str, Any] | None) -> dict[str, str]:
    if not headers:
        return {}
    normalized: dict[str, str] = {}
    for key, raw in headers.items():
        name = str(key or "").strip().lower()
        if not name:
            continue
        values = raw if isinstance(raw, (list, tuple)) else [raw]
        text = ", ".join(str(value or "").strip() for value in values if str(value or "").strip())
        if text:
            normalized[name] = text
    return normalized


def access_block_header_evidence(
    headers: Mapping[str, Any] | None,
    *,
    max_value_length: int = 180,
) -> dict[str, str]:
    """Return only the bounded vendor/header evidence safe to persist."""
    normalized = _headers_lower(headers)
    return {
        name: normalized[name][:max_value_length]
        for name in PERSISTED_ACCESS_BLOCK_HEADER_ALLOWLIST
        if normalized.get(name)
    }


def _vendor_hint(headers: dict[str, str], source_lower: str) -> str:
    server = headers.get("server", "").lower()
    if headers.get("x-datadome") or "captcha-delivery.com" in source_lower:
        return "datadome"
    if headers.get("x-iinfo") or "_incapsula_resource" in source_lower:
        return "imperva"
    if headers.get("x-sucuri-id") or "sucuri website firewall" in source_lower:
        return "sucuri"
    if "akamaighost" in server:
        return "akamai"
    if headers.get("cf-ray") or "cloudflare" in server:
        return "cloudflare"
    if "your access to this site has been limited" in source_lower:
        return "wordfence"
    return ""


def detect_access_block(
    status_code: int,
    headers: Mapping[str, Any] | None = None,
    body: str = "",
) -> dict[str, str] | None:
    """Identify explicit vendor access challenges without treating CDN presence as a block."""
    status = _status(status_code)
    normalized = _headers_lower(headers)
    source = str(body or "")
    lowered = source.lower()

    if normalized.get("cf-mitigated", "").strip().lower() == "challenge":
        return {"vendor": "cloudflare", "kind": "challenge", "signal": "cf-mitigated"}
    if normalized.get("sg-captcha"):
        return {"vendor": "siteground", "kind": "challenge", "signal": "sg-captcha"}
    if _SITEGROUND_META_REFRESH.search(source):
        return {"vendor": "siteground", "kind": "challenge", "signal": "sgcaptcha_meta_refresh"}

    # Cloudflare sometimes exposes the challenge only in the HTML. Require a
    # Cloudflare response identity as well so an article quoting challenge text
    # is not attributed to Cloudflare.
    if _vendor_hint(normalized, lowered) == "cloudflare" and _looks_like_challenge(source):
        return {"vendor": "cloudflare", "kind": "challenge", "signal": "cloudflare_challenge_body"}

    vendor = _vendor_hint(normalized, lowered)
    if status == 429:
        return {"vendor": vendor or "origin", "kind": "rate_limit", "signal": "http_429"}

    if "captcha-delivery.com" in lowered:
        return {"vendor": "datadome", "kind": "block", "signal": "datadome_block_page"}
    if "_incapsula_resource" in lowered:
        return {"vendor": "imperva", "kind": "block", "signal": "imperva_block_page"}
    if "sucuri website firewall" in lowered:
        return {"vendor": "sucuri", "kind": "block", "signal": "sucuri_block_page"}
    if "your access to this site has been limited" in lowered:
        return {"vendor": "wordfence", "kind": "block", "signal": "wordfence_block_page"}
    if vendor == "akamai" and _VISIBLE_ACCESS_DENIED.search(source):
        return {"vendor": "akamai", "kind": "block", "signal": "akamai_access_denied"}

    # A vendor identity by itself is normal on a 2xx page. Only error statuses
    # that can represent an access decision turn that identity into a block.
    if vendor and status in {401, 403, 503}:
        return {"vendor": vendor, "kind": "block", "signal": f"vendor_http_{status}"}
    return None


def classify_page_evidence(
    *,
    status_code: int,
    content_type: str = "",
    fetch_error: str = "",
    html: str = "",
    body_truncated: bool = False,
    response_headers: Mapping[str, Any] | None = None,
) -> str:
    status = _status(status_code)
    error = str(fetch_error or "").strip()
    source = str(html or "")
    content_type_lower = str(content_type or "").lower()

    if detect_access_block(status, response_headers, source):
        return "failed_access"
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
    access_kind = str(page.get("access_block_kind") or "").strip().lower()
    if access_kind in {"challenge", "block", "rate_limit"}:
        return "failed_access"
    stamped = str(page.get("page_evidence_class") or "")
    if stamped in PAGE_EVIDENCE_CLASSES:
        return stamped

    status = _status(page)
    error = str(page.get("fetch_error") or page.get("error") or "")
    content_type = str(page.get("content_type") or "")
    html_size = int(page.get("html_size") or 0)
    body = page.get("_html") or page.get("html") or page.get("raw_html") or ""
    carried_headers = page.get("access_block_headers")
    if not isinstance(carried_headers, Mapping):
        carried_headers = {}

    if detect_access_block(status, carried_headers, body if isinstance(body, str) else ""):
        return "failed_access"
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
    # A security challenge served as an apparent 200 must never regain authority
    # by being re-derived from a page dict that lost its stamp.
    if isinstance(body, str) and body and _looks_like_challenge(body):
        return "failed_access"
    return "usable_html"


def page_has_usable_html(page: dict[str, Any]) -> bool:
    return page_evidence_class(page) == "usable_html"
