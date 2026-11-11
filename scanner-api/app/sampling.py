"""Deterministic, balanced sitemap-bucket sampling."""

from __future__ import annotations

import re
import hashlib
import math
from collections import Counter, defaultdict
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlparse

from .extract import is_legal_page_path, is_route_boundary
from .market_scope import strip_market_locale_prefix

SAMPLING_VERSION = "balanced_sitemap_buckets_v8_importance_section_quotas"
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


def route_pattern(path: str) -> str:
    """A sampling pattern only; never use this as a request/evidence identity."""
    parts = [part for part in route_signature(path).split("/") if part]
    if not parts:
        return "/"
    for index, part in enumerate(parts):
        if part.isdigit():
            parts[index] = ":id"
        elif any(char.isdigit() for char in part) or (len(parts) >= 2 and index == len(parts) - 1):
            parts[index] = ":slug"
    return "/" + "/".join(parts)


def section_keys(urls: Iterable[str], path_of: Callable[[str], str]) -> dict[str, str]:
    """Partition by locale-stripped section; split dominant repeated branches.

    Standalone top-level pages share the root section; an inventory section's
    actual hub belongs to that section. Dominant sections split at genuine
    subdirectories, never into thousands of leaf slugs.
    """
    paths = {url: [part for part in strip_locale_prefix(path_of(url)).split("/") if part] for url in urls}
    branch_roots = {parts[0] for parts in paths.values() if len(parts) >= 2}
    keys = {url: "/" + parts[0] if parts and (len(parts) >= 2 or parts[0] in branch_roots) else "/" for url, parts in paths.items()}
    counts = Counter(keys.values())
    for section, count in counts.items():
        if section == "/" or count <= len(paths) / 2:
            continue
        branches = Counter(parts[1] for url, parts in paths.items() if keys[url] == section and len(parts) >= 3)
        if sum(value >= 2 for value in branches.values()) < 2:
            continue
        for url, parts in paths.items():
            if keys[url] == section and len(parts) >= 2 and branches[parts[1]] >= 2:
                keys[url] = section + "/" + parts[1]
    return keys


def select_balanced_urls(
    urls: Iterable[str],
    family_of: Callable[[str], str],
    path_of: Callable[[str], str],
    budget: int,
    *,
    preferred_market: str = "",
    homepage_links: Iterable[str] = (),
    lastmod: Mapping[str, str] | None = None,
    importance_scores: Mapping[str, Any] | None = None,
) -> list[str]:
    """Select sections before volume, retaining commercial and trust reserves.

    Floors are bounded by available URLs and allocated in rounds, so when a
    budget cannot fit every three-page floor it still covers as many sections
    as possible. Locale/query duplicates fill only after fresh routes.
    """
    urls = list(dict.fromkeys(urls))
    homepage_links = tuple(homepage_links)
    if budget <= 0:
        return []
    if len(urls) <= budget:
        return urls
    from .page_importance import build_page_importance

    paths = {url: path_of(url) for url in urls}
    families = {url: family_of(url) for url in urls}
    roles = {url: selection_role(paths[url], families[url]) for url in urls}
    signatures = {url: route_signature(paths[url]) for url in urls}
    scores = importance_scores or build_page_importance(urls, family_of, path_of, homepage_links=homepage_links, lastmod=lastmod)
    navigation = set(homepage_links)
    market_parts = str(preferred_market or "").strip("/").split("/")
    valid_market = 1 <= len(market_parts) <= 2 and all(LOCALE_SEGMENT_RE.fullmatch(part) for part in market_parts)
    market_prefix = "/" + "/".join(part.lower() for part in market_parts) if valid_market else ""

    def importance(url: str) -> float:
        value = scores.get(url, 0.0)
        if isinstance(value, Mapping):
            value = value.get("importance_score", 0.0)
        try:
            return min(1.0, max(0.0, float(value)))
        except (TypeError, ValueError):
            return 0.0

    def rank(url: str) -> tuple:
        path = str(paths[url]).lower().split("?", 1)[0].split("#", 1)[0]
        preferred = bool(market_prefix) and (path == market_prefix or path.startswith(market_prefix + "/"))
        return (not preferred, -importance(url), hashlib.sha256(url.encode("utf-8")).hexdigest(), url)

    urls.sort(key=rank)
    # Pick a preferred-market representative before spending on translations.
    fresh_urls, repeats, known = [], [], set()
    for url in urls:
        signature = signatures[url]
        if signature in known:
            repeats.append(url)
        else:
            fresh_urls.append(url)
            known.add(signature)
    # Allocate section quotas *inside* the preferred market. Replacing a
    # finished selection with the first preferred URLs would undo every quota
    # on locale-prefixed sites and let one recognized family consume the cap.
    if market_prefix:
        preferred = [url for url in fresh_urls if rank(url)[0] is False]
        if preferred:
            if len(preferred) >= budget:
                return select_balanced_urls(
                    preferred, family_of, path_of, budget,
                    homepage_links=homepage_links, lastmod=lastmod,
                    importance_scores=scores,
                )
            preferred_set = set(preferred)
            remaining = select_balanced_urls(
                [url for url in fresh_urls if url not in preferred_set] + repeats,
                family_of, path_of, budget - len(preferred),
                homepage_links=homepage_links, lastmod=lastmod,
                importance_scores=scores,
            )
            return preferred + remaining
    sections = section_keys(fresh_urls, path_of)
    buckets: dict[str, list[str]] = defaultdict(list)
    for url in fresh_urls:
        buckets[sections[url]].append(url)

    def spread(values: list[str]) -> list[str]:
        patterns: dict[str, list[str]] = defaultdict(list)
        for url in values:
            patterns[route_pattern(paths[url])].append(url)
        pattern_order = sorted(patterns, key=lambda key: rank(patterns[key][0]))
        output = []
        for index in range(max((len(group) for group in patterns.values()), default=0)):
            for pattern in pattern_order:
                if index < len(patterns[pattern]):
                    output.append(patterns[pattern][index])
        return output

    buckets = {section: spread(values) for section, values in buckets.items()}
    section_order = sorted(buckets, key=lambda section: rank(buckets[section][0]))
    selected, chosen = [], set()
    counts = Counter()

    def take(url: str) -> bool:
        if url in chosen or len(selected) >= budget:
            return False
        chosen.add(url)
        selected.append(url)
        counts[sections[url]] += 1
        return True

    # Exact homepage, bounded trust, then observed navigation.
    for url in fresh_urls:
        if signatures[url] == "/":
            take(url)
    for url in [url for url in fresh_urls if is_trust_path(paths[url])][:TRUST_RESERVE]:
        take(url)
    reserved_trust = list(selected)
    for url in [url for url in fresh_urls if url in navigation][:max(1, int(budget * 0.15))]:
        take(url)
    reserved_nav = [url for url in selected if url not in reserved_trust]

    # One head in every section before a second or third representative.
    heads = []
    for round_index in range(3):
        for section in section_order:
            want = min(3, len(buckets[section]))
            if counts[section] >= min(want, round_index + 1):
                continue
            candidate = next((url for url in buckets[section] if url not in chosen), None)
            if candidate and take(candidate) and round_index == 0:
                heads.append(candidate)

    # Preserve v7's demonstrated business-identity protections, after section
    # floors so an unfamiliar vocabulary can no longer be starved by them.
    for allowed_roles, limit in ((HUB_ROLES, budget // 2), (LEAF_ROLES, min(IDENTITY_RESERVE, max(1, budget // 4)))):
        available: dict[str, list[str]] = defaultdict(list)
        for url in fresh_urls:
            if roles[url] in allowed_roles and url not in chosen:
                available[roles[url]].append(url)
        have = sum(roles[url] in allowed_roles for url in selected)
        while available and have < limit and len(selected) < budget:
            for role in sorted(list(available)):
                if have >= limit:
                    break
                if take(available[role].pop(0)):
                    have += 1
                if not available[role]:
                    del available[role]

    # Floors precede square-root proportional fill. Deficit allocation reuses
    # capacity from exhausted sections without a sitemap-order-dependent tail.
    weights = {}
    for section, values in buckets.items():
        mean_score = sum(importance(url) for url in values) / len(values)
        role_weight = sum(HUB_WEIGHT if roles[url] in HUB_ROLES else MONEY_WEIGHT if roles[url] in LEAF_ROLES else 1.0 for url in values) / len(values)
        weights[section] = math.sqrt(len(values)) * (0.2 + mean_score) * role_weight
    total_weight = sum(weights.values())
    targets = {section: budget * weight / total_weight for section, weight in weights.items()}
    # A 40% ceiling is feasible only when at least three sizeable sections can
    # supply the balance. Small /trust and singleton sections do not count.
    sizeable = [section for section, values in buckets.items() if len(values) >= max(3, int(budget * 0.2)) and not all(is_trust_path(paths[url]) for url in values)]
    ceiling = max(1, int(budget * 0.4)) if len(sizeable) >= 4 else budget
    remaining = {section: [url for url in values if url not in chosen] for section, values in buckets.items()}
    while len(selected) < budget:
        eligible = [section for section in section_order if remaining[section] and counts[section] < ceiling]
        if not eligible:
            eligible = [section for section in section_order if remaining[section]]
        if not eligible:
            break
        section = min(eligible, key=lambda key: (counts[key] / max(targets[key], 0.000001), rank(remaining[key][0])))
        take(remaining[section].pop(0))
    # Repeated routes fill unused space; original exact URL identities survive.
    for url in repeats:
        if len(selected) >= budget:
            break
        if url not in chosen:
            chosen.add(url)
            selected.append(url)

    # Fetch order leads with nav/heads, then commercial hubs before more leaves.
    selected_set = set(selected)
    leading = reserved_trust + reserved_nav + sorted(set(heads), key=rank)
    leading = [url for url in dict.fromkeys(leading) if url in selected_set]
    leading_set = set(leading)
    groups = [{}, {}, {}]
    for url in sorted((url for url in selected if url not in leading_set), key=rank):
        group = groups[0] if roles[url] in HUB_ROLES else groups[1] if roles[url] in LEAF_ROLES else groups[2]
        group.setdefault(roles[url] if group is not groups[2] else families[url], []).append(url)
    ordered = list(leading)
    while any(groups):
        for group in (groups[0], groups[0], groups[0], groups[1], groups[2]):
            for key in sorted(list(group)):
                ordered.append(group[key].pop(0))
                if not group[key]:
                    del group[key]
    if market_prefix:
        ordered.sort(key=lambda url: rank(url)[0])
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
    inventory_patterns = Counter(route_pattern(path_of(url)) for url in all_urls)
    selected_patterns = Counter(route_pattern(path_of(url)) for url in selected)
    sections = section_keys(all_urls, path_of)
    discovered_sections = Counter(sections.values())
    selected_sections = Counter(sections[url] for url in selected if url in sections)

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
        "sections_discovered": dict(discovered_sections),
        "sections_selected": {key: selected_sections[key] for key in discovered_sections},
        "sections_never_selected": sorted(key for key in discovered_sections if not selected_sections[key]),
        "route_patterns": {
            key: {"inventory_count": count, "selected_count": selected_patterns[key]}
            for key, count in sorted(inventory_patterns.items())
        },
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
    pattern_counts: Counter[str] = Counter()
    for page in pages:
        url = str(page.get("final_url") or page.get("url") or "").strip()
        if not url:
            continue
        pattern_counts[route_pattern(path_of(url))] += 1
        segments = [segment for segment in str(path_of(url) or "/").split("/") if segment]
        if segments:
            prefix_counts[f"/{segments[0]}"] += 1

    # Keyed on the discovered prefixes the UI already renders, so a row can show
    # found, selected and checked side by side without a second lookup.
    discovered = report.get("path_prefixes_discovered") or {}
    report["pages_checked"] = len(pages)
    report["path_prefixes_checked"] = {key: prefix_counts.get(key, 0) for key in discovered}
    patterns = report.setdefault("route_patterns", {})
    for pattern in set(patterns) | set(pattern_counts):
        row = patterns.setdefault(pattern, {"inventory_count": 0, "selected_count": 0})
        row["checked_count"] = pattern_counts[pattern]
    return report
