import gzip
import re
from urllib.parse import urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

from .artifact_filter import is_artifact_url, record_artifact
from .market_scope import market_pair_prefix, path_within_scope
from .security import safe_get

MAX_SITEMAP_FETCHES = 60


async def load_sitemap_urls(client: httpx.AsyncClient, origin: str, path_prefix: str, limit: int, artifacts: list[dict], scope_evidence: dict | None = None) -> list[str]:
    scope_evidence = scope_evidence if scope_evidence is not None else {}
    scope_evidence.setdefault("sitemap_urls_excluded_outside_scope", 0)
    scope_evidence.setdefault("market_prefixes_detected", [])
    scope_evidence.setdefault("multimarket_detected", False)
    scope_evidence.setdefault("market_scope_required", False)

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

    child_sitemaps: list[str] = []
    fetched: set[str] = set()
    family_urls: dict[str, list[str]] = {}

    # Root urlsets are buckets too. Do not let one large direct-root sitemap fill
    # the global discovery cap before later sitemap indexes and child families are
    # even fetched.
    for root in dedupe(roots):
        if len(fetched) >= MAX_SITEMAP_FETCHES:
            break
        locs = await fetch_sitemap_locs(client, root, fetched, artifacts)
        bucket = family_urls.setdefault(f"root:{sitemap_family_key(root)}", [])
        for loc in locs:
            if is_sitemap_url(loc):
                child_sitemaps.append(loc)
            elif len(bucket) < limit:
                normalized = normalize_sitemap_page_url(loc, origin)
                record_market_prefix(scope_evidence, normalized)
                if is_same_prefix(normalized, path_prefix):
                    bucket.append(normalized)
                else:
                    scope_evidence["sitemap_urls_excluded_outside_scope"] += 1

    # Collect child-sitemap URLs into per-family buckets, then interleave before
    # applying the global limit. Otherwise one huge child sitemap can consume
    # every discovery slot before booking, collection, or trust families appear.
    for child in rank_child_sitemaps(child_sitemaps, path_prefix):
        if len(fetched) >= MAX_SITEMAP_FETCHES:
            break
        bucket = family_urls.setdefault(f"child:{sitemap_family_key(child)}", [])
        locs = await fetch_sitemap_locs(client, child, fetched, artifacts)
        for loc in locs:
            if len(bucket) >= limit:
                break
            if not is_sitemap_url(loc):
                normalized = normalize_sitemap_page_url(loc, origin)
                record_market_prefix(scope_evidence, normalized)
                if is_same_prefix(normalized, path_prefix):
                    bucket.append(normalized)
                else:
                    scope_evidence["sitemap_urls_excluded_outside_scope"] += 1

    # Round-robin root and child urlsets together. Root pages keep deterministic
    # first position, but cannot starve later child families at the global cap.
    output = dedupe(interleave_url_families(family_urls))
    detected = sorted(set(scope_evidence.get("market_prefixes_detected", [])))
    scope_evidence["market_prefixes_detected"] = detected[:50]
    if (not path_prefix or path_prefix == "/") and len(detected) > 1:
        market_urls = [url for url in output if market_pair_prefix(url)]
        scope_evidence["multimarket_detected"] = True
        scope_evidence["market_scope_required"] = True
        scope_evidence["sitemap_urls_excluded_outside_scope"] += len(market_urls)
        output = [url for url in output if not market_pair_prefix(url)]
    elif len(detected) > 1:
        scope_evidence["multimarket_detected"] = True
    return output[:limit]


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

    body = decode_sitemap_body(response, sitemap_url)
    if not body:
        return []
    soup = BeautifulSoup(body, "xml")
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


def decode_sitemap_body(response: httpx.Response, sitemap_url: str) -> str:
    """Decode plain XML and .xml.gz sitemap bodies.

    HTTP clients normally decode Content-Encoding automatically, but many sitemap
    files use a .gz extension with raw gzip bytes and no Content-Encoding header.
    Detect both the gzip magic bytes and the URL suffix, while tolerating servers
    that already decompressed a .gz response.
    """
    raw = bytes(getattr(response, "content", b"") or b"")
    path = urlparse(str(sitemap_url or "")).path.lower()
    gzip_candidate = raw.startswith(b"\x1f\x8b") or path.endswith(".gz")
    if gzip_candidate and raw:
        try:
            raw = gzip.decompress(raw)
        except (OSError, EOFError):
            # A proxy or HTTP Content-Encoding layer may already have decoded a
            # .gz URL. In that case the bytes are plain XML and can be decoded.
            pass

    if raw:
        encoding = getattr(response, "encoding", None) or "utf-8"
        try:
            return raw.decode(encoding, errors="replace")
        except LookupError:
            return raw.decode("utf-8", errors="replace")
    return str(getattr(response, "text", "") or "")


def is_sitemap_url(url: str) -> bool:
    return bool(re.search(r"\.xml(?:\.gz)?(?:$|[?#])", url, re.I))


def is_same_prefix(url: str, path_prefix: str) -> bool:
    try:
        return path_within_scope(urlparse(url).path or "/", path_prefix)
    except Exception:
        return False


def record_market_prefix(scope_evidence: dict, url: str) -> None:
    prefix = market_pair_prefix(url)
    if prefix and prefix not in scope_evidence["market_prefixes_detected"]:
        scope_evidence["market_prefixes_detected"].append(prefix)


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
