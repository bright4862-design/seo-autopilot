import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from .artifact_filter import is_artifact_url, record_artifact

MAX_SITEMAP_FETCHES = 20


async def load_sitemap_urls(client: httpx.AsyncClient, origin: str, path_prefix: str, limit: int, artifacts: list[dict]) -> list[str]:
    roots: list[str] = []
    robots_url = f"{origin}/robots.txt"
    try:
        robots = await client.get(robots_url)
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
                urls.append(loc)

    for child in rank_child_sitemaps(child_sitemaps, path_prefix):
        if len(fetched) >= MAX_SITEMAP_FETCHES or len(urls) >= limit:
            break
        if child.lower().endswith(".gz"):
            continue
        locs = await fetch_sitemap_locs(client, child, fetched, artifacts)
        for loc in locs:
            if len(urls) >= limit:
                break
            if not is_sitemap_url(loc) and is_same_prefix(loc, path_prefix):
                urls.append(loc)

    return dedupe(urls)[:limit]


async def fetch_sitemap_locs(client: httpx.AsyncClient, sitemap_url: str, fetched: set[str], artifacts: list[dict]) -> list[str]:
    if not sitemap_url or sitemap_url in fetched:
        return []
    fetched.add(sitemap_url)
    try:
        response = await client.get(sitemap_url)
        if response.status_code >= 400:
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


def rank_child_sitemaps(children: list[str], path_prefix: str) -> list[str]:
    tokens = [token for token in (path_prefix or "").lower().split("/") if token]

    def score(url: str) -> int:
        target = url.lower()
        value = 0
        if tokens and all(token in target for token in tokens):
            value += 40
        elif tokens and any(token in target for token in tokens):
            value += 20
        if re.search(r"page|product|categor|service|listing|collection|post|article|guide", target):
            value += 8
        if re.search(r"tag|author|archive|image|video", target):
            value -= 15
        return value

    return sorted(dedupe(children), key=score, reverse=True)


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output
