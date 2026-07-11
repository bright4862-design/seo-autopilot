"""Deterministic, balanced sitemap-bucket sampling."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable, Iterable

SAMPLING_VERSION = "balanced_sitemap_buckets_v1"
TRUST_PREFIXES = (
    "/about", "/contact", "/privacy", "/terms", "/legal", "/mentions-legales",
    "/cgv", "/security", "/impressum", "/conditions", "/a-propos",
)
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


def is_trust_path(path: str) -> bool:
    return str(path or "").lower().startswith(TRUST_PREFIXES)


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

    def take(url: str) -> bool:
        if url in chosen or len(selected) >= budget:
            return False
        chosen.add(url)
        selected.append(url)
        return True

    for url in [u for u in urls if is_trust_path(path_of(u))][:TRUST_RESERVE]:
        take(url)

    min_per_family = 1 if budget < SMALL_BUDGET else MIN_PER_MATERIAL_FAMILY
    for family in sorted(f for f, values in buckets.items() if len(values) >= MATERIAL_THRESHOLD):
        want = min(min_per_family, len(buckets[family]))
        have = sum(1 for url in selected if family_of(url) == family)
        for url in buckets[family]:
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
                for url in pool[family][:quotas[family]]:
                    if not take(url):
                        break

    for url in urls:
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
    return {
        "sampling_version": SAMPLING_VERSION,
        "sitemap_urls_discovered": len(all_urls),
        "sitemap_urls_sampled": len(selected),
        "family_totals": dict(all_families),
        "family_sampled": dict(selected_families),
        "families_never_sampled": sorted(family for family in all_families if not selected_families.get(family)),
        "trust_pages_in_sitemap": len(trust_all),
        "trust_pages_sampled": len(trust_selected),
    }
