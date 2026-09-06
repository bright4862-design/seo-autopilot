"""Deterministic, balanced sitemap-bucket sampling."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Callable, Iterable
from urllib.parse import urlparse

from .extract import is_legal_page_path

SAMPLING_VERSION = "balanced_sitemap_buckets_v6_selected_and_checked_split"
TRUST_PREFIXES = (
    "/about", "/contact", "/privacy", "/terms", "/legal", "/mentions-legales",
    "/cgv", "/security", "/impressum", "/conditions", "/a-propos",
)
TRUST_ROUTE_SEGMENTS = {
    "about", "about-us", "a-propos", "contact", "contact-us", "security",
    "trust", "conditions", "privacy", "terms", "legal", "mentions-legales",
    "cgu", "cgv", "impressum",
}
LOCALE_SEGMENT_RE = re.compile(r"^[a-z]{2}(?:-[a-z]{2})?$", re.I)
MONEY_FAMILIES = {
    "loan_program", "conversion", "product_page", "collection_page",
    "booking_or_checkout", "activity_detail", "location_landing",
    "calculator", "comparison_page",
}
MIN_PER_MATERIAL_FAMILY = 3
MATERIAL_THRESHOLD = 2
TRUST_RESERVE = 5
MONEY_WEIGHT = 1.5
SMALL_BUDGET = 25
# Slots held for the routes that prove what the business actually does. The
# 35-site production audit reported IKEA as a publisher because its sample was
# corporate pages, and Musement and Tiqets as publishers because theirs were
# city and editorial pages: in each case the commercial identity of the site
# was never fetched, so no classifier could have seen it.
IDENTITY_RESERVE = 24


def strip_locale_prefix(path: str) -> str:
    """Drop a leading locale or market segment: /de-at/team -> /team."""
    clean = str(path or "/").split("?", 1)[0].split("#", 1)[0]
    segments = [segment for segment in clean.split("/") if segment]
    if segments and LOCALE_SEGMENT_RE.match(segments[0]):
        segments = segments[1:]
    return "/" + "/".join(segments)


def route_signature(path: str) -> str:
    """The route a path represents once its market prefix is removed.

    Translated copies of one route are one route pattern, not independent
    votes for how the budget should be spent. Wise spent five of its sampled
    pages on `/plug-types/democratic-republic-of-congo` in three languages and
    two `/about/our-story` markets; those are one page to fix and one page to
    sample.
    """
    return strip_locale_prefix(path).rstrip("/").lower() or "/"


def is_trust_path(path: str) -> bool:
    value = str(path or "").strip()
    if "://" in value:
        value = urlparse(value).path or "/"
    clean = value.lower().split("?", 1)[0].split("#", 1)[0].rstrip("/") or "/"

    # Use the scanner's canonical, bounded legal-path matcher so locale-prefixed
    # CMS routes such as /fr/page/cgu and /fr/page/mentions-legales count as trust
    # pages without reintroducing substring leaks such as lo(cgu)enole.
    if is_legal_page_path(clean) or clean.startswith(TRUST_PREFIXES):
        return True

    segments = [segment for segment in clean.split("/") if segment]
    if segments and LOCALE_SEGMENT_RE.match(segments[0]):
        segments = segments[1:]
    if segments and segments[0] in {"page", "pages"}:
        segments = segments[1:]
    return bool(segments and segments[0] in TRUST_ROUTE_SEGMENTS)


def select_balanced_urls(
    urls: Iterable[str],
    family_of: Callable[[str], str],
    path_of: Callable[[str], str],
    budget: int,
) -> list[str]:
    urls = list(urls)
    if budget <= 0:
        return []
    if len(urls) <= budget:
        return urls

    buckets: dict[str, list[str]] = defaultdict(list)
    for url in urls:
        buckets[family_of(url)].append(url)

    selected: list[str] = []
    chosen: set[str] = set()
    seen_signatures: set[str] = set()

    def take(url: str) -> bool:
        if url in chosen or len(selected) >= budget:
            return False
        chosen.add(url)
        seen_signatures.add(route_signature(path_of(url)))
        selected.append(url)
        return True

    def fresh_first(candidates: Iterable[str]) -> list[str]:
        """Unseen route signatures first, original order preserved within each.

        Proportional fill used to walk a family in sitemap order, so a route
        published in twelve markets could consume twelve slots before a
        different route was reached.
        """
        fresh, repeats = [], []
        pending: set[str] = set()
        for url in candidates:
            signature = route_signature(path_of(url))
            if signature in seen_signatures or signature in pending:
                repeats.append(url)
            else:
                pending.add(signature)
                fresh.append(url)
        return fresh + repeats

    for url in fresh_first(u for u in urls if is_trust_path(path_of(u)))[:TRUST_RESERVE]:
        take(url)

    # Identity and commercial routes are reserved before proportional fill, so
    # a large multi-market site cannot spend its whole budget on whichever
    # surface happens to publish the most URLs.
    identity_candidates = [url for url in urls if family_of(url) in MONEY_FAMILIES]
    for url in fresh_first(identity_candidates)[:IDENTITY_RESERVE]:
        take(url)

    min_per_family = 1 if budget < SMALL_BUDGET else MIN_PER_MATERIAL_FAMILY
    for family in sorted(f for f, values in buckets.items() if len(values) >= MATERIAL_THRESHOLD):
        want = min(min_per_family, len(buckets[family]))
        have = sum(1 for url in selected if family_of(url) == family)
        for url in fresh_first(buckets[family]):
            if have >= want or len(selected) >= budget:
                break
            if take(url):
                have += 1

    for family, family_urls in sorted(buckets.items()):
        if len(family_urls) < MATERIAL_THRESHOLD:
            take(family_urls[0])

    remaining = budget - len(selected)
    if remaining > 0:
        pool = {family: [url for url in values if url not in chosen] for family, values in buckets.items()}
        weights = {
            family: len(values) * (MONEY_WEIGHT if family in MONEY_FAMILIES else 1.0)
            for family, values in pool.items() if values
        }
        total = sum(weights.values())
        if total > 0:
            quotas = {family: int(remaining * weight / total) for family, weight in weights.items()}
            for family in sorted(quotas, key=lambda value: (-quotas[value], value)):
                for url in fresh_first(pool[family])[:quotas[family]]:
                    if not take(url):
                        break

    for url in fresh_first(urls):
        if len(selected) >= budget:
            break
        take(url)
    return selected[:budget]


def sampling_report(
    all_urls: list[str],
    selected: list[str],
    family_of: Callable[[str], str],
    path_of: Callable[[str], str],
) -> dict[str, Any]:
    all_families: dict[str, int] = defaultdict(int)
    selected_families: dict[str, int] = defaultdict(int)
    for url in all_urls:
        all_families[family_of(url)] += 1
    for url in selected:
        selected_families[family_of(url)] += 1
    trust_all = [url for url in all_urls if is_trust_path(path_of(url))]
    trust_selected = [url for url in selected if is_trust_path(path_of(url))]

    # Coverage by route rather than by URL: a route published in twelve markets
    # is one route the customer maintains, and reporting it as twelve sampled
    # pages overstates what the scan actually looked at.
    all_signatures = {route_signature(path_of(url)) for url in all_urls}
    selected_signatures = {route_signature(path_of(url)) for url in selected}
    markets: dict[str, int] = defaultdict(int)
    for url in all_urls:
        path = str(path_of(url) or "/")
        segments = [segment for segment in path.split("/") if segment]
        if segments and LOCALE_SEGMENT_RE.match(segments[0]):
            markets[segments[0].lower()] += 1
    sampled_markets: dict[str, int] = defaultdict(int)
    for url in selected:
        path = str(path_of(url) or "/")
        segments = [segment for segment in path.split("/") if segment]
        if segments and LOCALE_SEGMENT_RE.match(segments[0]):
            sampled_markets[segments[0].lower()] += 1

    path_prefixes: dict[str, int] = defaultdict(int)
    sampled_path_prefixes: dict[str, int] = defaultdict(int)
    for url in all_urls:
        segments = [segment for segment in str(path_of(url) or "/").split("/") if segment]
        if segments:
            path_prefixes[f"/{segments[0]}"] += 1
    for url in selected:
        segments = [segment for segment in str(path_of(url) or "/").split("/") if segment]
        if segments:
            sampled_path_prefixes[f"/{segments[0]}"] += 1

    top_path_prefixes = dict(
        sorted(path_prefixes.items(), key=lambda item: (-item[1], item[0]))[:50]
    )
    top_sampled_path_prefixes = {
        key: sampled_path_prefixes.get(key, 0) for key in top_path_prefixes
    }

    identity_selected = [url for url in selected if family_of(url) in MONEY_FAMILIES]
    identity_all = [url for url in all_urls if family_of(url) in MONEY_FAMILIES]

    # Every count below is built from `selected` -- the URLs chosen for an
    # attempt, before a single page has been fetched. The word "sampled" read as
    # an observation to whoever consumed it, and the FixList went on to label it
    # "sampled" and "represented" to customers. On the September 6 matrix that
    # made four sites claim 148 pages covered against 39 or 40 actually checked.
    #
    # The values are unchanged and still correct for the question they answer.
    # Only the names now say which question that is. The `*_sampled` keys stay
    # for one release so existing readers keep working; new readers must use
    # `*_selected`, and must not read either as evidence a page was checked.
    selection = {
        "sitemap_urls_selected": len(selected),
        "family_selected": dict(selected_families),
        "families_never_selected": sorted(family for family in all_families if not selected_families.get(family)),
        "trust_pages_selected": len(trust_selected),
        "route_signatures_selected": len(selected_signatures),
        "markets_selected": dict(sampled_markets),
        "markets_never_selected": sorted(market for market in markets if not sampled_markets.get(market)),
        "path_prefixes_selected": top_sampled_path_prefixes,
        "identity_pages_selected": len(identity_selected),
    }
    legacy_aliases = {
        "sitemap_urls_sampled": selection["sitemap_urls_selected"],
        "family_sampled": selection["family_selected"],
        "families_never_sampled": selection["families_never_selected"],
        "trust_pages_sampled": selection["trust_pages_selected"],
        "route_signatures_sampled": selection["route_signatures_selected"],
        "markets_sampled": selection["markets_selected"],
        "markets_never_sampled": selection["markets_never_selected"],
        "path_prefixes_sampled": selection["path_prefixes_selected"],
        "identity_pages_sampled": selection["identity_pages_selected"],
    }
    return {
        "sampling_version": SAMPLING_VERSION,
        "sitemap_urls_discovered": len(all_urls),
        "family_totals": dict(all_families),
        "trust_pages_in_sitemap": len(trust_all),
        "route_signatures_discovered": len(all_signatures),
        "locale_variants_collapsed": max(0, len(all_urls) - len(all_signatures)),
        "markets_discovered": dict(markets),
        "path_prefixes_discovered": top_path_prefixes,
        "identity_pages_in_sitemap": len(identity_all),
        **selection,
        **legacy_aliases,
    }


def enrich_checked_coverage(
    report: dict[str, Any],
    checked_pages: list[dict[str, Any]],
    path_of: Callable[[str], str],
) -> dict[str, Any]:
    """Record what the crawl actually returned, in place, after the page cap.

    Selection evidence answers "what did we mean to look at". Nothing in the
    payload answered "what did we look at", so the UI used selection and called
    it coverage.

    The population here must be the same one `pages_crawled` counts, so this is
    called once, after the hard cap has been applied and `pages` is final.
    Passing a partial list would understate the site as confidently as selection
    overstated it.

    The prefix counts are bounded by, never equal to, `pages_checked`: the
    homepage has no first path segment, and pages outside the top discovered
    prefixes have nowhere to be attributed. Forcing the two to reconcile would
    mean inventing a section for the root or dropping a checked page from the
    total. The remainder is real and belongs in an "other checked pages" row.
    """
    pages = [page for page in (checked_pages or []) if isinstance(page, dict)]
    prefix_counts: dict[str, int] = defaultdict(int)
    for page in pages:
        url = str(page.get("final_url") or page.get("url") or "").strip()
        if not url:
            continue
        segments = [segment for segment in str(path_of(url) or "/").split("/") if segment]
        if segments:
            prefix_counts[f"/{segments[0]}"] += 1

    # Keyed on the discovered prefixes the UI already renders, so a row can show
    # found, selected and checked side by side without a second lookup.
    discovered = report.get("path_prefixes_discovered") or {}
    report["pages_checked"] = len(pages)
    report["path_prefixes_checked"] = {key: prefix_counts.get(key, 0) for key in discovered}
    return report
