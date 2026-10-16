"""Commercial sitemap choices must be useful before a crawl hits its deadline."""

from urllib.parse import urlparse

import pytest

from app.extract import classify_template
from app.sampling import enrich_checked_coverage, sampling_report, select_balanced_urls


HOST = "https://example.com"


def path_of(url):
    return urlparse(url).path or "/"


def family_of(url):
    # Exercise the same path-only classification that scanner.run_scan uses.
    return classify_template(path_of(url))


def select(paths, budget=150, **kwargs):
    urls = [HOST + path for path in paths]
    return select_balanced_urls(urls, family_of, path_of, budget, **kwargs)


def test_category_city_service_and_pricing_are_in_the_early_crawl_prefix():
    activities = [f"/fr/annonce/activity-{index}/voir" for index in range(1000)]
    hubs = ["/fr/category/anniversaire", "/fr/ville/paris", "/fr/services/team-building", "/fr/pricing"]
    trust = ["/privacy", "/terms", "/about", "/contact", "/security"]
    selected = select(activities + hubs + trust)

    assert len(selected) == 150
    assert set(HOST + path for path in hubs) <= set(selected[:15])
    assert set(HOST + path for path in trust) <= set(selected)
    assert any("/annonce/" in url for url in selected[:15])


def test_hubs_receive_a_meaningful_sample_instead_of_only_family_minimums():
    activities = [f"/fr/annonce/activity-{index}/voir" for index in range(1000)]
    hubs = [f"/fr/category/theme-{index}" for index in range(25)] + [f"/fr/ville/city-{index}" for index in range(25)]
    selected = select(activities + hubs)

    assert sum(url in {HOST + path for path in hubs} for url in selected) >= 24
    assert sum("/category/" in url for url in selected[:24]) >= 10
    assert sum("/ville/" in url for url in selected[:24]) >= 10


def test_available_categories_and_cities_take_priority_over_excess_activity_leaves():
    paths = ([f"/fr/annonce/activity-{index}/voir" for index in range(1000)]
             + [f"/fr/category/theme-{index}" for index in range(50)]
             + [f"/fr/ville/city-{index}" for index in range(50)])
    selected = select(paths)
    hubs = [url for url in selected if "/category/" in url or "/ville/" in url]

    assert len(hubs) >= 75
    assert sum("/annonce/" in url for url in selected) >= 24
    assert len(selected) == len(set(selected)) == 150


def test_large_site_selection_does_not_depend_on_xml_input_order():
    paths = ([f"/fr/annonce/activity-{index}/voir" for index in range(100)]
             + [f"/products/item-{index}" for index in range(30)]
             + [f"/services/service-{index}" for index in range(12)]
             + ["/pricing", "/contact", "/privacy", "/terms"])
    assert select(paths, 60) == select(list(reversed(paths)), 60)


@pytest.mark.parametrize("path", ["/services/seo", "/our-services/seo", "/nos-services/seo", "/pricing", "/plans", "/tarifs", "/fr/fr/services/seo", "/fr/fr/pricing"])
def test_path_only_services_and_pricing_are_commercial_choices(path):
    selected = select([f"/blog/article-{index}" for index in range(200)] + [path], 30)
    assert HOST + path in selected[:8]


def test_similar_words_auth_and_legal_do_not_masquerade_as_commercial_hubs():
    noise = ["/servicescape", "/pricing-news", "/plans-for-the-week", "/account/pricing", "/login", "/cart", "/checkout", "/privacy"]
    hubs = ["/services/seo", "/pricing", "/ville/paris", "/category/tours"]
    selected = select(noise + [f"/annonce/a-{index}/voir" for index in range(100)] + hubs, 30)

    first_hub = min(selected.index(HOST + path) for path in hubs)
    assert all(selected.index(HOST + path) > first_hub for path in noise[:7] if HOST + path in selected)
    # Utility and legal routes remain available as diagnostic evidence.
    assert HOST + "/privacy" in selected
    assert any(url in {HOST + "/login", HOST + "/cart", HOST + "/checkout"} for url in selected)


def test_query_multiplicity_cannot_take_the_commercial_reserve_from_fresh_roles():
    variants = [f"/products/shoe?color={index}" for index in range(1000)]
    paths = variants + [f"/blog/article-{index}" for index in range(100)] + ["/services/fitting", "/pricing", "/ville/paris"]
    selected = select(paths, 60)

    assert {HOST + path for path in paths[-3:]} <= set(selected[:12])
    assert sum(path_of(url) == "/products/shoe" for url in selected) == 1
    assert any("?color=" in url for url in selected)


def test_fresh_business_paths_precede_locale_repeats_across_roles():
    variants = [f"/{market}/products/shoe" for market in ("fr", "de", "es", "pt", "it", "nl", "pl", "cs", "da", "fi", "sv", "no")]
    paths = variants + [f"/services/service-{index}" for index in range(40)] + [f"/blog/article-{index}" for index in range(80)]
    selected = select(paths, 30)
    assert sum(url.endswith("/products/shoe") for url in selected) == 1
    assert len({url for url in selected if "/services/" in url}) >= 20


def test_preferred_market_orders_one_and_two_segment_markets_without_filtering():
    paths = ([f"/us/en/products/item-{index}" for index in range(40)]
             + [f"/fr/fr/products/item-{index}" for index in range(40)]
             + [f"/france/products/item-{index}" for index in range(40)])
    selected = select(paths, 50, preferred_market="/fr/fr")

    assert all(url.startswith(HOST + "/fr/fr/") for url in selected[:24])
    assert any(url.startswith(HOST + "/france/") for url in selected)
    assert len(selected) == len(set(selected)) == 50


def test_one_segment_market_preference_never_matches_a_substring():
    paths = ([f"/france/products/item-{index}" for index in range(40)]
             + [f"/fr/products/item-{index}" for index in range(40)])
    selected = select(paths, 30, preferred_market="/fr")
    assert all(url.startswith(HOST + "/fr/") for url in selected)


def test_other_market_variants_fill_capacity_after_preferred_fresh_routes():
    paths = ([f"/us/en/products/item-{index}" for index in range(40)]
             + [f"/fr/fr/products/item-{index}" for index in range(40)])
    selected = select(paths, 50, preferred_market="/fr/fr")
    assert sum(url.startswith(HOST + "/fr/fr/") for url in selected) == 40
    assert sum(url.startswith(HOST + "/us/en/") for url in selected) == 10


@pytest.mark.parametrize("hint", ["/f", "/france", "/fr/fr/ville", "/fr?x=1", "https://example.com/fr"])
def test_invalid_market_hints_do_not_change_neutral_ordering(hint):
    paths = [f"/{market}/products/item-{index}" for market in ("fr", "us") for index in range(40)]
    assert select(paths, 30, preferred_market=hint) == select(paths, 30)


def test_request_query_case_and_slash_identities_survive_when_the_budget_fits():
    paths = ["/products/shoe?a=1", "/products/shoe?a=2", "/Products/shoe", "/products/shoe/", "/fr/fr/products/shoe", "/us/en/products/shoe"]
    urls = [HOST + path for path in paths]
    assert select_balanced_urls(urls, family_of, path_of, len(urls), preferred_market="/fr/fr") == urls


def test_repeated_routes_can_fill_unused_capacity_without_rewriting_their_urls():
    paths = [f"/products/shoe?color={index}" for index in range(100)]
    selected = select(paths, 30)
    assert len(selected) == len(set(selected)) == 30
    assert set(selected) <= {HOST + path for path in paths}


def test_selected_and_checked_counts_still_describe_different_populations():
    urls = [HOST + path for path in [f"/annonce/a-{index}/voir" for index in range(200)] + ["/ville/paris", "/category/tours"]]
    selected = select_balanced_urls(urls, family_of, path_of, 150)
    report = sampling_report(urls, selected, family_of, path_of)
    enrich_checked_coverage(report, [{"url": url} for url in selected[:12]], path_of)

    assert report["sitemap_urls_selected"] == 150
    assert report["pages_checked"] == 12
    assert sum(report["path_prefixes_checked"].values()) <= 12
    assert report["sitemap_urls_discovered"] == len(urls)
