"""Versioned metadata and search-title evidence helpers.

This module records extraction state without changing health-score calibration.
It intentionally separates evidence collection from scoring.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

METADATA_EVIDENCE_VERSION = "metadata_evidence_v1_description_states"
TITLE_EVIDENCE_VERSION = "title_evidence_v1_contextual_duplicates"
TITLE_PIXEL_LIMIT = 561

_GENERIC_TITLES = {
    "home", "homepage", "page", "site", "website", "welcome", "untitled",
    "untitled page", "default title", "new page", "document",
}
_GENERIC_TITLE_PATTERNS = (
    re.compile(r"^sites?[-_].+[-_]site$", re.I),
)
_LOCALE_PAIR_RE = re.compile(r"^[a-z]{2}[-_][a-z]{2}$", re.I)
_MARKET_SEGMENTS = {
    "us", "uk", "gb", "fr", "de", "es", "it", "nl", "be", "ca", "au", "nz",
    "pt", "br", "mx", "jp", "kr", "cn", "hk", "sg", "in", "ie", "ch", "at",
    "se", "no", "dk", "fi", "pl", "cz", "ae", "sa",
}


def normalize_title_key(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def estimate_title_pixel_width(value: str) -> int:
    """Return a deterministic SERP-width estimate without adding font dependencies."""
    width = 0.0
    for char in str(value or ""):
        if char in " ilI1'`|.,:;![](){}":
            width += 4.0
        elif char in "MW@#%&QO":
            width += 10.0
        elif char.isupper():
            width += 8.0
        elif char.isdigit():
            width += 7.0
        elif ord(char) > 127:
            width += 8.0
        else:
            width += 6.8
    return round(width)


def title_width_state(value: str) -> str:
    if not str(value or "").strip():
        return "missing"
    return "over_pixel_limit" if estimate_title_pixel_width(value) > TITLE_PIXEL_LIMIT else "within_guideline"


def is_generic_fallback_title(value: str) -> bool:
    normalized = normalize_title_key(value)
    if not normalized:
        return False
    return normalized in _GENERIC_TITLES or any(pattern.match(normalized) for pattern in _GENERIC_TITLE_PATTERNS)


def describe_meta_description(soup, html: str, status_code: int, content_type: str, fetch_error: str) -> dict:
    """Return an explicit, mutually exclusive existence state.

    Metadata claims are made only for a successful final HTTP 200 HTML response.
    Redirect, partial-content, empty-body, blocked and non-HTML records remain
    inconclusive rather than being converted into missing-tag findings.
    """
    status = int(status_code or 0)
    content_type_lower = str(content_type or "").lower()
    source = str(html or "")

    if fetch_error or status != 200:
        state, elements = "access_inconclusive", []
    elif content_type_lower and "html" not in content_type_lower and "xhtml" not in content_type_lower:
        state, elements = "access_inconclusive", []
    elif not source.strip():
        state, elements = "raw_html_incomplete", []
    elif not re.search(r"<head(?:\s|>)", source, re.I):
        state = "head_parse_boundary"
        elements = soup.find_all("meta", attrs={"name": re.compile(r"^description$", re.I)})
    else:
        elements = soup.find_all("meta", attrs={"name": re.compile(r"^description$", re.I)})
        if not elements:
            state = "missing"
        else:
            values = [
                re.sub(r"\s+", " ", str(element.get("content", ""))).strip()
                for element in elements if element.has_attr("content")
            ]
            if any(values):
                state = "present_valid"
            elif any(not element.has_attr("content") for element in elements):
                state = "malformed"
            else:
                state = "present_empty"

    values = [
        re.sub(r"\s+", " ", str(element.get("content", ""))).strip()
        for element in elements if element.has_attr("content")
    ]
    return {
        "version": METADATA_EVIDENCE_VERSION,
        "state": state,
        "selected_value": next((value for value in values if value), ""),
        "element_count": len(elements),
        "values": values[:8],
        "duplicate": len(elements) > 1,
        "head_parse_boundary_has_description": state == "head_parse_boundary" and bool(elements),
    }


def relative_evidence_url(page: dict) -> str:
    value = str(page.get("final_url") or page.get("url") or page.get("path") or "/")
    parsed = urlparse(value)
    path = parsed.path or str(page.get("path") or "/")
    return f"{path}?{parsed.query}" if parsed.query else path


def is_html_page_evidence(page: dict) -> bool:
    content_type = str(page.get("content_type") or "").lower()
    if content_type and "html" not in content_type and "xhtml" not in content_type:
        return False
    path = urlparse(str(page.get("final_url") or page.get("url") or "")).path.lower()
    return not re.search(
        r"\.(?:avif|bmp|css|csv|docx?|eot|gif|ico|jpe?g|js|json|map|md|markdown|mp3|mp4|pdf|png|pptx?|svg|tiff?|ttf|txt|wav|webm|webp|woff2?|xlsx?|xml|zip)$",
        path,
        re.I,
    )


def _locale_parts(value: str) -> tuple[str, str]:
    path = urlparse(value).path or "/"
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return "", "/"
    first = segments[0].lower()
    if first in _MARKET_SEGMENTS or _LOCALE_PAIR_RE.fullmatch(first):
        stripped = "/" + "/".join(segments[1:])
        return first, stripped or "/"
    return "", path


def classify_duplicate_title_context(title: str, urls: list[str]) -> str:
    if is_generic_fallback_title(title):
        return "generic_fallback"
    parsed = [urlparse(url) for url in urls]
    base_paths = {item.path or "/" for item in parsed}
    if len(base_paths) == 1 and len(set(urls)) > 1 and any(item.query for item in parsed):
        return "query_parameter_variants"
    locale_pairs = [_locale_parts(url) for url in urls]
    locales = {locale for locale, _ in locale_pairs if locale}
    stripped_paths = {stripped for _, stripped in locale_pairs}
    if len(locales) >= 2 and len(stripped_paths) == 1:
        return "localized_pages"
    return "true_template_duplicates"
