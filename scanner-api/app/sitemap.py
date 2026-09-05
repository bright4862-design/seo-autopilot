import asyncio
import gzip
import io
import re
import time
from urllib.parse import urlparse, urlunparse

import httpx

from .artifact_filter import is_artifact_url, record_artifact
from .market_scope import market_pair_prefix, path_within_scope
from .security import ResponseBodyTooLarge, safe_get

MAX_SITEMAP_FETCHES = 60
MAX_SITEMAP_DECODED_BYTES = 5_000_000
SITEMAP_PARSER_VERSION = "sitemap_parser_v1_xml_identity"

SITEMAP_LOC_RE = re.compile(
    r"<(?:[A-Za-z_][\w.-]*:)?loc\b[^>]*>(.*?)</(?:[A-Za-z_][\w.-]*:)?loc\s*>",
    re.I | re.S,
)
SITEMAP_XML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
XML_ENTITY_RE = re.compile(
    r"&(?:(amp|lt|gt|quot|apos)|#([0-9]+)|#x([0-9A-Fa-f]+));"
)
XML_ENTITIES = {
    "amp": "&",
    "lt": "<",
    "gt": ">",
    "quot": '"',
    "apos": "'",
}


def _unescape_xml(value: str) -> str:
    def replace(match: re.Match) -> str:
        named, decimal, hexadecimal = match.groups()
        if named:
            return XML_ENTITIES[named]
        codepoint = int(decimal, 10) if decimal else int(hexadecimal, 16)
        if (
            codepoint in {0x9, 0xA, 0xD}
            or 0x20 <= codepoint <= 0xD7FF
            or 0xE000 <= codepoint <= 0xFFFD
            or 0x10000 <= codepoint <= 0x10FFFF
        ):
            return chr(codepoint)
        return match.group(0)

    return XML_ENTITY_RE.sub(replace, value)


def parse_sitemap_locs(body: str) -> list[str]:
    """Extract sitemap <loc> values without building a full XML DOM.

    Large sitemap urlsets commonly contain tens of thousands of entries. The
    HTTP response body is already bounded by the request layer, so building a
    second BeautifulSoup XML tree only increases peak memory/CPU. Sitemap <loc>
    elements contain text values; extracting those values directly preserves
    discovery order, namespace prefixes, CDATA, and normal XML entities without
    retaining a DOM.
    """
    locs: list[str] = []
    source = SITEMAP_XML_COMMENT_RE.sub("", str(body or ""))
    for match in SITEMAP_LOC_RE.finditer(source):
        value = match.group(1).strip()
        if value.startswith("<![CDATA[") and value.endswith("]]>"):
            value = value[9:-3].strip()
        else:
            value = _unescape_xml(value).strip()
        if value:
            locs.append(value)
    return locs


class _SitemapRequestPacer:
    """Space sequential sitemap-discovery requests for burst-sensitive origins.

    The default zero interval is a no-op, so normal sites keep the existing fast
    discovery path.
    """

    def __init__(self, min_interval_seconds: float = 0.0):
        self.min_interval_seconds = max(0.0, float(min_interval_seconds or 0.0))
        self.next_request_at = 0.0

    async def wait_for_slot(self, deadline: float | None = None) -> bool:
        if self.min_interval_seconds <= 0:
            return True
        now = time.monotonic()
        wait_seconds = max(0.0, self.next_request_at - now)
        if deadline is not None and now + wait_seconds >= deadline:
            return False
        if wait_seconds:
            await asyncio.sleep(wait_seconds)
        now = time.monotonic()
        if deadline is not None and now >= deadline:
            return False
        self.next_request_at = now + self.min_interval_seconds
        return True


async def load_sitemap_urls(client: httpx.AsyncClient, origin: str, path_prefix: str, limit: int, artifacts: list[dict], scope_evidence: dict | None = None, *, deadline: float | None = None, max_fetches: int | None = None, diagnostics: dict | None = None, min_request_interval_seconds: float = 0.0) -> list[str]:
    scope_evidence = scope_evidence if scope_evidence is not None else {}
    diagnostics = diagnostics if diagnostics is not None else {}
    diagnostics.setdefault("sitemap_fetch_count", 0)
    diagnostics.setdefault("sitemap_fetch_limit_reached", False)
    diagnostics.setdefault("sitemap_budget_exhausted", False)
    diagnostics.setdefault("sitemap_failure_reason_buckets", {})
    # Per-source outcomes. Inventory proof is judged per source: a failed
    # speculative /sitemap.xml probe must not invalidate a robots-declared
    # sitemap that actually worked, so both observations are preserved.
    diagnostics.setdefault("sitemap_sources", [])
    request_interval = max(0.0, float(min_request_interval_seconds or 0.0))
    diagnostics["sitemap_request_interval_seconds"] = request_interval
    request_pacer = _SitemapRequestPacer(request_interval)
    scope_evidence.setdefault("sitemap_urls_excluded_outside_scope", 0)
    scope_evidence.setdefault("market_prefixes_detected", [])
    scope_evidence.setdefault("multimarket_detected", False)
    scope_evidence.setdefault("market_scope_required", False)

    fetch_limit = max(1, min(MAX_SITEMAP_FETCHES, int(max_fetches or MAX_SITEMAP_FETCHES)))
    roots: list[str] = []
    robots_url = f"{origin}/robots.txt"
    try:
        robots = await _safe_get_before_deadline(client, robots_url, deadline, pacer=request_pacer)
        if robots is not None:
            for line in robots.text.splitlines():
                if line.lower().startswith("sitemap:"):
                    roots.append(line.split(":", 1)[1].strip())
    except Exception:
        pass

    declared_roots = set(dedupe(roots))
    roots.append(f"{origin}/sitemap.xml")

    child_sitemaps: list[str] = []
    fetched: set[str] = set()
    family_urls: dict[str, list[str]] = {}

    # Root urlsets are buckets too. Do not let one large direct-root sitemap fill
    # the global discovery cap before later sitemap indexes and child families are
    # even fetched.
    for root in dedupe(roots):
        if _stop_sitemap_discovery(fetched, fetch_limit, deadline, diagnostics):
            break
        failures_before = _sitemap_failure_total(diagnostics)
        locs = await fetch_sitemap_locs(
            client,
            root,
            fetched,
            artifacts,
            deadline=deadline,
            diagnostics=diagnostics,
            pacer=request_pacer,
        )
        _record_sitemap_source(
            diagnostics,
            url=root,
            declared=root in declared_roots,
            loc_count=len(locs),
            failed=_sitemap_failure_total(diagnostics) > failures_before,
        )
        bucket = family_urls.setdefault(f"root:{sitemap_family_key(root)}", [])
        for loc in locs:
            if is_sitemap_url(loc):
                child_sitemaps.append(loc)
            elif len(bucket) < limit:
                normalized = normalize_sitemap_page_url(loc, origin)
                record_market_prefix(scope_evidence, normalized)
                if is_scannable_sitemap_url(normalized, origin) and is_same_prefix(normalized, path_prefix):
                    bucket.append(normalized)
                else:
                    scope_evidence["sitemap_urls_excluded_outside_scope"] += 1

    # Collect child-sitemap URLs into per-family buckets, then interleave before
    # applying the global limit. Otherwise one huge child sitemap can consume
    # every discovery slot before booking, collection, or trust families appear.
    for child in rank_child_sitemaps(child_sitemaps, path_prefix):
        if _stop_sitemap_discovery(fetched, fetch_limit, deadline, diagnostics):
            break
        bucket = family_urls.setdefault(f"child:{sitemap_family_key(child)}", [])
        locs = await fetch_sitemap_locs(
            client,
            child,
            fetched,
            artifacts,
            deadline=deadline,
            diagnostics=diagnostics,
            pacer=request_pacer,
        )
        for loc in locs:
            if len(bucket) >= limit:
                break
            if not is_sitemap_url(loc):
                normalized = normalize_sitemap_page_url(loc, origin)
                record_market_prefix(scope_evidence, normalized)
                if is_scannable_sitemap_url(normalized, origin) and is_same_prefix(normalized, path_prefix):
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
    output = output[:limit]
    diagnostics["sitemap_fetch_count"] = len(fetched)
    diagnostics["sitemap_urls_discovered"] = len(output)
    diagnostics["sitemap_child_url_count"] = len(dedupe(child_sitemaps))
    return output


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


def _record_sitemap_failure(diagnostics: dict | None, reason: str) -> None:
    if diagnostics is None:
        return
    buckets = diagnostics.setdefault("sitemap_failure_reason_buckets", {})
    buckets[reason] = int(buckets.get(reason, 0)) + 1


def _sitemap_failure_total(diagnostics: dict | None) -> int:
    if diagnostics is None:
        return 0
    buckets = diagnostics.get("sitemap_failure_reason_buckets") or {}
    return sum(int(value) for value in buckets.values())


def _record_sitemap_source(
    diagnostics: dict | None,
    *,
    url: str,
    declared: bool,
    loc_count: int,
    failed: bool,
) -> None:
    """One observation per inventory source, kept whatever the others did."""
    if diagnostics is None:
        return
    if failed:
        outcome = "failed"
    elif loc_count > 0:
        outcome = "urls"
    else:
        outcome = "empty"
    diagnostics.setdefault("sitemap_sources", []).append({
        "url": str(url),
        "source": "robots_declared" if declared else "speculative_default",
        "outcome": outcome,
        "loc_count": int(loc_count),
    })


def _stop_sitemap_discovery(fetched: set[str], fetch_limit: int, deadline: float | None, diagnostics: dict | None) -> bool:
    if len(fetched) >= fetch_limit:
        if diagnostics is not None:
            diagnostics["sitemap_fetch_limit_reached"] = True
        return True
    if _deadline_reached(deadline):
        if diagnostics is not None:
            diagnostics["sitemap_budget_exhausted"] = True
        _record_sitemap_failure(diagnostics, "sitemap_deadline_reached")
        return True
    return False


async def fetch_sitemap_locs(client: httpx.AsyncClient, sitemap_url: str, fetched: set[str], artifacts: list[dict], *, deadline: float | None = None, diagnostics: dict | None = None, pacer: _SitemapRequestPacer | None = None) -> list[str]:
    if not sitemap_url or sitemap_url in fetched:
        return []
    if _deadline_reached(deadline):
        if diagnostics is not None:
            diagnostics["sitemap_budget_exhausted"] = True
        _record_sitemap_failure(diagnostics, "sitemap_deadline_reached")
        return []
    fetched.add(sitemap_url)
    if diagnostics is not None:
        diagnostics["sitemap_fetch_count"] = len(fetched)
    try:
        response = (
            await _safe_get_before_deadline(client, sitemap_url, deadline, pacer=pacer)
            if pacer is not None
            else await _safe_get_before_deadline(client, sitemap_url, deadline)
        )
        if response is None:
            if _deadline_reached(deadline) and diagnostics is not None:
                diagnostics["sitemap_budget_exhausted"] = True
                _record_sitemap_failure(diagnostics, "sitemap_deadline_reached")
            else:
                _record_sitemap_failure(diagnostics, "no_response")
            return []
        if response.status_code >= 400:
            _record_sitemap_failure(diagnostics, f"http_{response.status_code}")
            return []
    except asyncio.TimeoutError:
        if diagnostics is not None:
            diagnostics["sitemap_budget_exhausted"] = True
        _record_sitemap_failure(diagnostics, "sitemap_timeout")
        return []
    except ResponseBodyTooLarge:
        _record_sitemap_failure(diagnostics, "sitemap_body_too_large")
        return []
    except Exception:
        _record_sitemap_failure(diagnostics, "sitemap_fetch_exception")
        return []

    try:
        body = decode_sitemap_body(response, sitemap_url)
    except ResponseBodyTooLarge:
        _record_sitemap_failure(diagnostics, "sitemap_body_too_large")
        return []
    if not body:
        _record_sitemap_failure(diagnostics, "empty_sitemap_body")
        return []
    locs: list[str] = []
    for loc in parse_sitemap_locs(body):
        if is_artifact_url(loc):
            record_artifact(artifacts, loc, "sitemap", sitemap_url, "")
            continue
        locs.append(loc)
    return locs


def _deadline_reached(deadline: float | None) -> bool:
    return deadline is not None and time.monotonic() >= deadline


async def _safe_get_before_deadline(client: httpx.AsyncClient, url: str, deadline: float | None, *, pacer: _SitemapRequestPacer | None = None):
    if pacer is not None and not await pacer.wait_for_slot(deadline):
        return None
    if deadline is None:
        return await safe_get(
            client,
            url,
            max_decoded_bytes=MAX_SITEMAP_DECODED_BYTES,
        )
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return None
    try:
        return await asyncio.wait_for(
            safe_get(
                client,
                url,
                max_decoded_bytes=MAX_SITEMAP_DECODED_BYTES,
            ),
            timeout=max(0.05, remaining),
        )
    except asyncio.TimeoutError:
        return None


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
            with gzip.GzipFile(fileobj=io.BytesIO(raw), mode="rb") as stream:
                decoded = stream.read(MAX_SITEMAP_DECODED_BYTES + 1)
            if len(decoded) > MAX_SITEMAP_DECODED_BYTES:
                raise ResponseBodyTooLarge(
                    f"decoded_sitemap_body_exceeded_{MAX_SITEMAP_DECODED_BYTES}_bytes"
                )
            raw = decoded
        except ResponseBodyTooLarge:
            raise
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


def is_scannable_sitemap_url(url: str, origin: str) -> bool:
    """True when a sitemap URL names a page this scan can actually fetch.

    A sitemap index routinely lists other subdomains -- blog., shop., docs. --
    and `normalize_sitemap_page_url` deliberately leaves those on their own
    host, because rewriting them onto the scanned origin would invent pages
    that do not exist there. Nothing downstream then re-checked the host:
    `is_same_prefix` compares the path only, so a foreign-subdomain URL whose
    path happened to sit inside the scope was accepted into the discovery
    inventory.

    The crawler's own `same_origin` guard is strict, so those URLs were never
    fetched. They only ever reached `pages_found`, which is how a site could
    report thousands of pages discovered against a hundred and fifty crawled --
    and how a 600-page subdomain inflated a 5,000-page total for a site that
    does not have 5,000 pages on the host being scanned.

    Counting a page the scan cannot reach is not caution, it is a wrong number:
    it overstates the site, understates coverage, and drags the score's coverage
    ceiling down for a shortfall that never existed.
    """
    try:
        parsed = urlparse(str(url or ""))
        origin_parsed = urlparse(str(origin or ""))
        if not origin_parsed.hostname:
            return True
        if not parsed.hostname:
            # A relative or malformed entry carries no competing host, so the
            # path check downstream is the honest arbiter.
            return True
        return comparable_host(parsed.hostname) == comparable_host(origin_parsed.hostname)
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
