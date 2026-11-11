"""Large inventories are sampled by business section, independent of vocabulary."""

from collections import Counter
from datetime import datetime, timezone
from random import Random
from urllib.parse import urlparse

import pytest

from app.extract import classify_template
from app.sampling import select_balanced_urls, sampling_report, enrich_checked_coverage


def path_of(url):
    return urlparse(url).path


def family_of(url):
    return classify_template(path_of(url))


def inventory():
    counts = {"solutions": 1560, "insights": 1040, "stores": 400, "products": 300}
    return [f"https://example.com/{section}/page-{i}" for section, count in counts.items() for i in range(count)] + [
        "https://example.com/platform", "https://example.com/contact", "https://example.com/privacy",
        "https://example.com/about", "https://example.com/pricing", "https://example.com/security", "https://example.com/",
    ]


@pytest.mark.parametrize("budget", [149, 499])
def test_every_material_section_is_represented_without_inventory_monopoly(budget):
    urls = inventory()
    selected = select_balanced_urls(urls, family_of, path_of, budget)
    counts = Counter(path_of(url).strip("/").split("/")[0] for url in selected)
    assert len(selected) == len(set(selected)) == budget
    for section in ("solutions", "insights", "stores", "products"):
        assert counts[section] >= 3
        assert counts[section] <= budget * 0.4


@pytest.mark.parametrize("budget", [149, 499])
def test_preferred_locale_keeps_section_quotas_instead_of_overwriting_them(budget):
    urls = [url.replace("https://example.com/", "https://example.com/fr/") for url in inventory()]
    selected = select_balanced_urls(urls, family_of, path_of, budget, preferred_market="/fr")
    counts = Counter(path_of(url).strip("/").split("/")[1] for url in selected if path_of(url).strip("/") != "fr")
    for section in ("solutions", "insights", "stores", "products"):
        assert counts[section] >= 3
        assert counts[section] <= budget * 0.4
    assert len(selected) == budget
    assert all(url.startswith("https://example.com/fr/") for url in selected)


def test_shuffled_inventory_produces_identical_order():
    urls = inventory()
    shuffled = urls.copy()
    Random(91).shuffle(shuffled)
    assert select_balanced_urls(urls, family_of, path_of, 149) == select_balanced_urls(shuffled, family_of, path_of, 149)


def test_two_url_sections_use_the_available_inventory_without_duplicates():
    urls = [f"https://example.com/section-{s}/page-{i}" for s in range(80) for i in range(2)]
    selected = select_balanced_urls(urls, family_of, path_of, 149)
    counts = Counter(path_of(url).split("/")[1] for url in selected)
    assert len(selected) == len(set(selected)) == 149
    assert len(counts) == 80
    assert max(counts.values()) <= 2


def test_homepage_navigation_is_reserved_even_when_not_in_a_known_family():
    urls = inventory()
    nav = ["https://example.com/platform", "https://example.com/solutions/page-1559"]
    selected = select_balanced_urls(urls, family_of, path_of, 149, homepage_links=nav)
    assert set(nav) <= set(selected[:30])


def test_existing_section_hubs_are_selected_before_repeated_leaves():
    hubs = [f"https://example.com/{section}" for section in ("solutions", "insights", "stores", "products")]
    selected = select_balanced_urls(inventory() + hubs, family_of, path_of, 149)
    assert set(hubs) <= set(selected[:20])


def test_alphabetical_section_renaming_does_not_remove_coverage():
    urls = inventory()
    renamed = [url.replace("/solutions", "/zzz").replace("/insights", "/yyy").replace("/stores", "/aaa").replace("/products", "/bbb") for url in urls]
    selected = select_balanced_urls(renamed, family_of, path_of, 149)
    counts = Counter(path_of(url).strip("/").split("/")[0] for url in selected)
    assert all(counts[section] >= 3 for section in ("zzz", "yyy", "aaa", "bbb"))


def test_importance_uses_observed_signals_and_ignores_uniform_lastmod():
    from app.page_importance import build_page_importance

    urls = ["https://example.com/", "https://example.com/platform", "https://example.com/platform/a/b", "https://example.com/news/old"]
    now = datetime(2026, 11, 11, tzinfo=timezone.utc)
    plain = build_page_importance(urls, family_of, path_of, now=now)
    uniform = build_page_importance(urls, family_of, path_of, lastmod={url: "2026-11-10" for url in urls}, now=now)
    assert {url: row["importance_score"] for url, row in plain.items()} == {url: row["importance_score"] for url, row in uniform.items()}
    enriched = build_page_importance(urls, family_of, path_of, homepage_links=[urls[1]], observed_inlinks={urls[1]: 9}, now=now)
    assert enriched[urls[0]]["importance_score"] == 1.0
    assert enriched[urls[1]]["importance_score"] > plain[urls[1]]["importance_score"]
    assert enriched[urls[1]]["selection_reason"] == "Linked from your homepage"
    assert all(0 <= row["importance_score"] <= 1 for row in enriched.values())


def test_pattern_counts_are_inventory_and_selection_not_issue_prevalence():
    urls = inventory()
    selected = select_balanced_urls(urls, family_of, path_of, 149)
    report = sampling_report(urls, selected, family_of, path_of)
    pattern = report["route_patterns"]["/solutions/:slug"]
    assert pattern["inventory_count"] == 1560
    assert pattern["selected_count"] >= 3
    assert "affected_page_count" not in pattern
    enrich_checked_coverage(report, [{"url": "https://example.com/solutions/page-11"}], path_of)
    assert pattern["checked_count"] == 1
    assert report["route_patterns"]["/stores/:slug"]["checked_count"] == 0
