from __future__ import annotations

import asyncio
import re
from urllib.parse import urljoin, urlparse

import httpx

from .extract import extract_links, extract_page
from .security import is_public_http_url, safe_get

TRUST_DISCOVERY_VERSION = "trust_page_discovery_v1"

# Keep this list intentionally small and high-confidence. These probes are a
# site-level evidence check, so they may run even when the requested crawl is
# scoped to a subdirectory such as /pret-immobilier.
TRUST_PATH_CANDIDATES = (
    "/contact",
    "/contact-us",
    "/contactez-nous",
    "/nous-contacter",
    "/about",
    "/about-us",
    "/a-propos",
    "/qui-sommes-nous",
    "/privacy",
    "/privacy-policy",
    "/politique-de-confidentialite",
    "/confidentialite",
    "/legal",
    "/mentions-legales",
    "/terms",
    "/terms-of-service",
    "/conditions",
    "/conditions-generales",
    "/cgv",
    "/security",
    "/securite",
)

TRUST_SEGMENTS = {path.strip("/") for path in TRUST_PATH_CANDIDATES}
TRUST_LINK_TEXT = re.compile(
    r"\b(about|contact|privacy|legal|terms|security|"
    r"a\s+propos|qui\s+sommes[- ]nous|mentions?\s+l[eé]gales?|"
    r"confidentialit[eé]|conditions?\s+g[eé]n[eé]rales?|s[eé]curit[eé])\b",
    re.I,
)
LOCALE_SEGMENT = re.compile(r"^[a-z]{2}(?:-[a-z]{2})?$", re.I)


def is_trust_candidate(url: str, link_text: str = "") -> bool:
    try:
        path = urlparse(str(url or "")).path.lower()
    except Exception:
        path = str(url or "").lower().split("?", 1)[0]
    parts = [part for part in path.split("/") if part]
    if parts and LOCALE_SEGMENT.match(parts[0]):
        parts = parts[1:]
    if any(part in TRUST_SEGMENTS for part in parts[:2]):
        return True
    return bool(TRUST_LINK_TEXT.search(str(link_text or "")))


def _page_url(page: dict) -> str:
    return str(page.get("final_url") or page.get("url") or page.get("path") or "")


def _page_is_trust(page: dict) -> bool:
    if is_trust_candidate(_page_url(page)):
        return True
    return (
        str(page.get("page_template_family") or "") == "legal_info"
        or str(page.get("estimated_page_intent") or "") == "trust_or_legal"
    )


def _same_origin(url: str, origin: str) -> bool:
    try:
        left = urlparse(url)
        right = urlparse(origin)
        return left.scheme == right.scheme and left.netloc.lower() == right.netloc.lower()
    except Exception:
        return False


async def _fetch_page(client: httpx.AsyncClient, url: str, source: str, source_page: str = "") -> tuple[dict | None, dict]:
    evidence = {
        "url": url,
        "source": source,
        "status_code": 0,
        "final_url": "",
        "error": "",
    }
    try:
        response = await safe_get(client, url)
        if response is None:
            evidence["error"] = "blocked_or_non_public_redirect"
            return None, evidence
        evidence["status_code"] = int(response.status_code or 0)
        evidence["final_url"] = str(response.url)
        if not 200 <= response.status_code < 400:
            return None, evidence
        content_type = response.headers.get("content-type", "")
        html = response.text if "html" in content_type or not content_type else ""
        page = extract_page(
            html,
            url,
            str(response.url),
            response.status_code,
            content_type,
            {
                "discovered_from": [source],
                "source_pages": [source_page] if source_page else [],
                "link_text_samples": [],
            },
        )
        page["trust_discovery_probe"] = True
        page["_trust_html"] = html
        return page, evidence
    except Exception as exc:
        evidence["error"] = str(exc)[:180]
        return None, evidence


async def enrich_scan_with_trust_pages(scan_result: dict) -> dict:
    """Add confirmed trust-page evidence to a successful Python scan response.

    The normal 150-page crawl is representative, not exhaustive. This bounded
    discovery step prevents a sampled finance/SaaS crawl from claiming that
    trust pages are missing merely because they fell outside the sample.
    """
    if not isinstance(scan_result, dict) or not scan_result.get("success"):
        return scan_result

    website_url = str(scan_result.get("website_url") or scan_result.get("normalized_url") or "")
    if not website_url or not is_public_http_url(website_url):
        return scan_result

    parsed = urlparse(website_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    pages = list(scan_result.get("crawled_pages") or scan_result.get("pages") or [])
    existing_found = [page for page in pages if _page_is_trust(page)]

    checked: list[dict] = []
    discovered_pages: list[dict] = []
    candidate_urls: list[tuple[str, str, str]] = []

    async with httpx.AsyncClient(
        timeout=6,
        follow_redirects=False,
        headers={"User-Agent": "Mozilla/5.0 (compatible; FixListTrustDiscovery/1.0)"},
    ) as client:
        # Read the homepage first so custom trust URLs such as /company can be
        # discovered from navigation/footer text even when their slug is unusual.
        homepage, homepage_evidence = await _fetch_page(client, origin + "/", "trust_homepage_probe")
        checked.append(homepage_evidence)
        homepage_html = homepage.pop("_trust_html", "") if homepage else ""
        for link in extract_links(homepage_html, origin + "/") if homepage_html else []:
            href = str(link.get("href") or "")
            text = str(link.get("text") or "")
            if _same_origin(href, origin) and is_trust_candidate(href, text):
                candidate_urls.append((href, "trust_homepage_link", "/"))

        for path in TRUST_PATH_CANDIDATES:
            candidate_urls.append((urljoin(origin + "/", path.lstrip("/")), "trust_standard_probe", ""))

        unique_candidates: list[tuple[str, str, str]] = []
        seen_candidates: set[str] = set()
        existing_urls = {_page_url(page).rstrip("/") for page in existing_found}
        for url, source, source_page in candidate_urls:
            normalized = url.rstrip("/")
            if not normalized or normalized in seen_candidates or normalized in existing_urls:
                continue
            seen_candidates.add(normalized)
            unique_candidates.append((url, source, source_page))

        results = await asyncio.gather(*[
            _fetch_page(client, url, source, source_page)
            for url, source, source_page in unique_candidates
        ])
        for page, evidence in results:
            checked.append(evidence)
            if not page:
                continue
            page.pop("_trust_html", None)
            # A live URL selected from a trust-labelled homepage link is valid
            # evidence even when its path is custom, e.g. /company.
            if evidence.get("source") == "trust_homepage_link" or _page_is_trust(page):
                discovered_pages.append(page)

    combined = list(pages)
    seen_pages = {_page_url(page).rstrip("/") for page in combined if _page_url(page)}
    for page in existing_found + discovered_pages:
        key = _page_url(page).rstrip("/")
        if key and key not in seen_pages:
            seen_pages.add(key)
            combined.append(page)

    found_pages = [page for page in combined if _page_is_trust(page) or page.get("trust_discovery_probe")]
    found_paths = []
    found_urls = []
    for page in found_pages:
        url = _page_url(page)
        path = urlparse(url).path or "/"
        if path not in found_paths:
            found_paths.append(path)
        if url not in found_urls:
            found_urls.append(url)

    responses_received = sum(1 for item in checked if int(item.get("status_code") or 0) > 0)
    discovery = {
        "version": TRUST_DISCOVERY_VERSION,
        "attempted": True,
        "conclusive": bool(existing_found or responses_received),
        "checked": len(checked),
        "responses_received": responses_received,
        "found": found_paths,
        "found_urls": found_urls,
        "evidence": checked[:40],
    }

    scan_result["pages"] = combined
    scan_result["crawled_pages"] = combined
    scan_result["pages_crawled"] = len(combined)
    scan_result["pages_found"] = max(int(scan_result.get("pages_found") or 0), len(combined))
    scan_result["trust_page_discovery"] = discovery

    scan_summary = scan_result.get("scan_summary")
    if isinstance(scan_summary, dict):
        scan_summary["pages_crawled"] = len(combined)
        scan_summary["trust_page_discovery"] = discovery

    technical = scan_result.get("technical_audit_summary")
    if isinstance(technical, dict):
        technical["pages_crawled"] = len(combined)
        technical["trust_page_discovery"] = discovery

    return scan_result
