"""Deterministic, balanced sitemap-bucket sampling."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Callable, Iterable
from urllib.parse import urlparse

from .extract import is_legal_page_path, is_route_boundary
from .market_scope import strip_market_locale_prefix

SAMPLING_VERSION = "balanced_sitemap_buckets_v7_commercial_hubs_before_repeated_leaves"
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
HUB_WEIGHT = 4.0
HUB_ROLES = {
    "category_or_collection", "city_or_location", "service", "pricing",
    "contact", "comparison", "calculator",
}
LEAF_ROLES = MONEY_FAMILIES - {"collection_page", "location_landing", "calculator", "comparison_page"}
SMALL_BUDGET = 25
# Slots held for the routes that prove what the business actually does. The
# 35-site production audit reported IKEA as a publisher because its sample was
# corporate pages, and Musement and Tiqets as publishers because theirs were
# city and editorial pages: in each case the commercial identity of the site
# was never fetched, so no classifier could have seen it.
IDENTITY_RESERVE = 24


def strip_locale_prefix(path: str) -> str:
    """Drop one/two leading market segments for sampling, never URL identity."""
    clean = str(path or "/").split("?", 1)[0].split("#", 1)[0]
    return strip_market_locale_prefix(clean)


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


def selection_role(path: str, family: str) -> str:
    """Scheduling hints only: no indexability, template or revenue authority."""
    clean = strip_locale_prefix(path).lower()
    first = clean.strip("/").split("/", 1)[0]
    if family == "route_boundary" or is_route_boundary(path) or is_legal_page_path(clean):
        return "diagnostic"
    if first in {"pricing", "price", "prices", "plans", "tarif", "tarifs", "tarification"}:
        return "pricing"
    if first in {"service", "services", "our-service", "our-services", "notre-service", "nos-services", "prestations"}:
        return "service"
    if family == "collection_page" or first in {"category", "categories", "categorie", "catégorie", "collection", "collections"}:
        return "category_or_collection"
    if family == "location_landing" or first in {"city", "cities", "ville", "villes", "location", "locations"}:
        return "city_or_location"
    if family == "contact" or first in {"contact", "contact-us", "nous-contacter", "contactez-nous"}:
        return "contact"
    if family in {"comparison_page", "calculator"}:
        return "comparison" if family == "comparison_page" else "calculator"
    return family if family in MONEY_FAMILIES else "diagnostic"


def select_balanced_urls(
    urls: Iterable[str],
    family_of: Callable[[str], str],
    path_of: Callable[[str], str],
    budget: int,
    *,
    preferred_market: str = "",
) -> list[str]:
    urls = list(urls)
    if budget <= 0:
        return []
    if len(urls) <= budget:
        return urls

    # This is a scheduling key, separate from exact request/evidence identities.
    # Only a verified/explicit leading locale hint may affect market preference.
    market_parts = str(preferred_market or "").strip("/").split("/")
    market_parts = market_parts if 1 <= len(market_parts) <= 2 and all(LOCALE_SEGMENT_RE.fullmatch(part) for part in market_parts) else []
    market_prefix = "/" + "/".join(part.lower() for part in market_parts) if market_parts else ""
    paths = {url: path_of(url) for url in urls}
    families = {url: family_of(url) for url in urls}
    roles = {url: selection_role(paths[url], families[url]) for url in urls}
    signatures = {url: route_signature(paths[url]) for url in urls}

    def rank(url: str) -> tuple:
        path = str(paths[url]).lower().split("?", 1)[0].split("#", 1)[0]
        preferred = bool(market_prefix) and (path == market_prefix or path.startswith(market_prefix + "/"))
        return (not preferred, signatures[url], url)

    urls = sorted(set(urls), key=rank)
    buckets: dict[str, list[str]] = defaultdict(list)
    role_buckets: dict[str, list[str]] = defaultdict(list)
    for url in urls:
        buckets[families[url]].append(url)
        role_buckets[roles[url]].append(url)

    selected: list[str] = []
    chosen: set[str] = set()
    seen_signatures: set[str] = set()

    def take(url: str) -> bool:
        if url in chosen or len(selected) >= budget:
            return False
        chosen.add(url)
        seen_signatures.add(signatures[url])
        selected.append(url)
        return True

    def fresh(candidates: Iterable[str]) -> list[str]:
        """One exact URL per new sampling route; repeats can fill unused space."""
        result = []
        pending: set[str] = set()
        for url in candidates:
            signature = signatures[url]
            if url not in chosen and signature not in seen_signatures and signature not in pending:
                pending.add(signature)
                result.append(url)
        return result

    def interleave(groups: dict[str, list[str]]) -> Iterable[str]:
        pending = {key: iter(values) for key, values in sorted(groups.items()) if values}
        while pending:
            for key in list(pending):
                try:
                    yield next(pending[key])
                except StopIteration:
                    del pending[key]

    trust_candidates = [url for url in urls if is_trust_path(paths[url])]
    trust_fresh = fresh(trust_candidates)
    trust_fresh_set = set(trust_fresh)
    trust_order = trust_fresh + [url for url in trust_candidates if url not in trust_fresh_set]
    for url in trust_order[:TRUST_RESERVE]:
        take(url)
    reserved_trust = list(selected)

    # Hubs lead to many commercial pages. Reserve half the sample for distinct
    # available hubs before a large activity/product inventory takes the fill.
    # Keep a separate bounded leaf reserve so we still review actual inventory.
    for allowed_roles, limit in ((HUB_ROLES, budget // 2), (LEAF_ROLES, min(IDENTITY_RESERVE, max(1, budget // 4)))):
        added = 0
        for url in interleave({role: fresh(values) for role, values in role_buckets.items() if role in allowed_roles}):
            if added >= limit or len(selected) >= budget:
                break
            if signatures[url] not in seen_signatures and take(url):
                added += 1

    min_per_family = 1 if budget < SMALL_BUDGET else MIN_PER_MATERIAL_FAMILY
    for family in sorted(f for f, values in buckets.items() if len(values) >= MATERIAL_THRESHOLD):
        want = min(min_per_family, len({signatures[url] for url in buckets[family]}))
        have = len({signatures[url] for url in selected if families[url] == family})
        for url in fresh(buckets[family]):
            if have >= want or len(selected) >= budget:
                break
            if take(url):
                have += 1

    for family, family_urls in sorted(buckets.items()):
        if len(family_urls) < MATERIAL_THRESHOLD:
            take(family_urls[0])

    remaining = budget - len(selected)
    if remaining > 0:
        pool = {role: fresh(values) for role, values in role_buckets.items()}
        weights = {
            role: len(values) * (HUB_WEIGHT if role in HUB_ROLES else MONEY_WEIGHT if role in MONEY_FAMILIES else 1.0)
            for role, values in pool.items() if values
        }
        total = sum(weights.values())
        if total > 0:
            quotas = {role: int(remaining * weight / total) for role, weight in weights.items()}
            for url in interleave({role: pool[role][:quota] for role, quota in quotas.items()}):
                if signatures[url] not in seen_signatures:
                    take(url)

    # Use fresh paths across every role before any remaining language/query
    # variants. This changes selection, never the exact URLs we fetch or seal.
    for url in fresh(urls) + urls:
        if len(selected) >= budget:
            break
        take(url)

    # Membership and fetch order answer different questions. Two hub rounds
    # followed by one leaf/diagnostic round gives deadlines a diverse prefix,
    # instead of fetching all pages from the largest XML family first.
    pending_hubs = {role: iter([url for url in selected if url not in reserved_trust and roles[url] == role]) for role in sorted(HUB_ROLES)}
    pending_leaves = {role: iter([url for url in selected if url not in reserved_trust and roles[url] == role]) for role in sorted(LEAF_ROLES)}
    pending_diagnostics = {family: iter([url for url in selected if url not in reserved_trust and roles[url] == "diagnostic" and families[url] == family]) for family in sorted(buckets)}
    ordered = list(reserved_trust)
    while pending_hubs or pending_leaves or pending_diagnostics:
        for groups in (pending_hubs, pending_hubs, pending_leaves, pending_diagnostics):
            for key in list(groups):
                try:
                    ordered.append(next(groups[key]))
                except StopIteration:
                    del groups[key]
    return ordered


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
