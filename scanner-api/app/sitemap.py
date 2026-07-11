import re
from urllib.parse import urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

from .artifact_filter import is_artifact_url, record_artifact
from .security import safe_get

MAX_SITEMAP_FETCHES = 60


async def load_sitemap_urls(client: httpx.AsyncClient, origin: str, path_prefix: str, limit: int, artifacts: list[dict]) -> list[str]:
    roots: list[str] = []
    robots_url = f"{origin}/robots.txt"
    try:
        robots = await safe_get(client, robots_url)
        if robots is not None:
            for line in robots.text.splitlines():
                if line.lower().startswith("sitemap:"):
                    roots.append(line.split(":", 1)[1].strip())
    except Exception:
        pass

    roots.append(f"{origin}/sitemap.xml")

    urls: list[str] = []
    child_sitemaps: list[str] = []
    fetched: set[str] = set()

    for root in dedupe(roots):
        if len(fetched) >= MAX_SITEMAP_FETCHES or len(urls) >= limit:
            break
        locs = await fetch_sitemap_locs(client, root, fetched, artifacts)
        for loc in locs:
            if is_sitemap_url(loc):
                child_sitemaps.append(loc)
            elif is_same_prefix(loc, path_prefix):
                urls.append(normalize_sitemap_page_url(loc, origin))

    # Collect child-sitemap URLs into per-family buckets, then interleave before
    # applying the global limit. Otherwise one huge child sitemap can consume
    # every discovery slot before booking, collection, or trust families appear.
    family_urls: dict[str, list[str]] = {}
    for child in rank_child_sitemaps(child_sitemaps, path_prefix):
        if len(fetched) >= MAX_SITEMAP_FETCHES:
            break
        if child.lower().endswith(".gz"):
            continue
        bucket = family_urls.setdefault(sitemap_family_key(child), [])
        locs = await fetch_sitemap_locs(client, child, fetched, artifacts)
        for loc in locs:
            if len(bucket) >= limit:
                break
            if not is_sitemap_url(loc) and is_same_prefix(loc, path_prefix):
                bucket.append(normalize_sitemap_page_url(loc, origin))

    # Root-level URLs keep priority, followed by child URLs round-robined across
    # sitemap families so the discovery cap retains a representative universe.
    return dedupe(urls + interleave_url_families(family_urls))[:limit]


def interleave_url_families(family_urls: dict[str, list[str]]) -> list[str]:
    """Round-robin URLs across sitemap families in deterministic family order."""
    output: list[str] = []
    total = sum(len(values) for values in family_urls.values())
    index = 0
    while len(output) < total:
        progressed = False
        for values in family_urls.values():
            if index < len(values):
                output.append(values[index])
                progressed = True
        if not progressed:
            break
        index += 1
    return output


async def fetch_sitemap_locs(client: httpx.AsyncClient, sitemap_url: str, fetched: set[str], artifacts: list[dict]) -> list[str]:
    if not sitemap_url or sitemap_url in fetched:
        return []
    fetched.add(sitemap_url)
    try:
        response = await safe_get(client, sitemap_url)
        if response is None or response.status_code >= 400:
            return []
    except Exception:
        return []

    soup = BeautifulSoup(response.text or "", "xml")
    locs: list[str] = []
    for tag in soup.find_all("loc"):
        loc = (tag.get_text() or "").strip()
        if not loc:
            continue
        if is_artifact_url(loc):
            record_artifact(artifacts, loc, "sitemap", sitemap_url, "")
            continue
        locs.append(loc)
    return locs


def is_sitemap_url(url: str) -> bool:
    return bool(re.search(r"\.xml(?:\.gz)?(?:$|[?#])", url, re.I))


def is_same_prefix(url: str, path_prefix: str) -> bool:
    if not path_prefix or path_prefix == "/":
        return True
    try:
        return (urlparse(url).path or "/").startswith(path_prefix.rstrip("/"))
    except Exception:
        return False


def normalize_sitemap_page_url(url: str, origin: str) -> str:
    """Keep sitemap page URLs on the scanner's accepted origin.

    Many sites redirect apex -> www or www -> apex, while their sitemap uses the
    canonical host. The scanner's same-origin guard is intentionally strict, so
    normal sitemap page URLs can be dropped after a harmless www/apex mismatch.
    When the hosts match after stripping a leading www., rewrite only the scheme
    and netloc to the scanner origin while preserving path/query/fragment.
    """
    try:
        parsed = urlparse(url)
        origin_parsed = urlparse(origin)
        if not parsed.scheme or not parsed.netloc or not origin_parsed.scheme or not origin_parsed.netloc:
            return url
        if comparable_host(parsed.hostname or "") == comparable_host(origin_parsed.hostname or ""):
            return urlunparse(parsed._replace(scheme=origin_parsed.scheme, netloc=origin_parsed.netloc))
    except Exception:
        return url
    return url


def comparable_host(host: str) -> str:
    value = str(host or "").lower().strip(".")
    return value[4:] if value.startswith("www.") else value


def rank_child_sitemaps(children: list[str], path_prefix: str) -> list[str]:
    tokens = [token for token in (path_prefix or "").lower().split("/") if token]

    def score(url: str) -> int:
        target = url.lower()
        value = 0
        if tokens and all(token in target for token in tokens):
            value += 40
        elif tokens and any(token in target for token in tokens):
            value += 20
        if re.search(r"page|product|categor|service|listing|collection|loan|location|reservation|booking|checkout|cart|panier|billet|ticket|devis|quote|apply|contact|trust|legal|privacy|mentions", target):
            value += 18
        if re.search(r"post|article|blog|guide", target):
            value += 4
        if re.search(r"tag|author|archive|image|video", target):
            value -= 15
        return value

    ranked = sorted(dedupe(children), key=score, reverse=True)
    return interleave_by_family(ranked)


def sitemap_family_key(url: str) -> str:
    """Collapse numbered sibling sitemap files into one stable family."""
    try:
        name = (urlparse(url).path.rsplit("/", 1)[-1] or "sitemap").lower()
    except Exception:
        name = str(url or "").lower().rsplit("/", 1)[-1]
    name = re.sub(r"\.xml(?:\.gz)?$", "", name)
    return re.sub(r"[-_]?\d+$", "", name) or "sitemap"


def interleave_by_family(children: list[str]) -> list[str]:
    """Round-robin child sitemaps so one large family cannot starve others."""
    families: dict[str, list[str]] = {}
    for child in children:
        families.setdefault(sitemap_family_key(child), []).append(child)
    output: list[str] = []
    while any(families.values()):
        for family in list(families):
            if families[family]:
                output.append(families[family].pop(0))
    return output


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output
