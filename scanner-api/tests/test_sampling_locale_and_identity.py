"""The 150-page budget must represent the business, not its translation count.

The 35-site production audit found two distinct ways the budget was misspent.

Translated copies of one route counted as independent members of a family, so
proportional fill could spend several slots on one page: Wise sampled
`/plug-types/democratic-republic-of-congo` in three languages and
`/about/our-story` in two markets.

Commercial identity was never reserved, so a large site could spend the whole
budget on whichever surface published the most URLs. IKEA was reported as a
publisher because its sample was corporate pages; Musement and Tiqets because
theirs were city and editorial pages. No classifier can recognise a business
whose commercial routes were never fetched.
"""

from app.sampling import (
    IDENTITY_RESERVE,
    route_signature,
    sampling_report,
    select_balanced_urls,
    strip_locale_prefix,
)

HOST = "https://example.com"


def family_of(url):
    path = url.replace(HOST, "")
    if "/tickets/" in path or "/attractions/" in path:
        return "activity_detail"
    if "/products/" in path:
        return "product_page"
    if "/blog/" in path:
        return "guide_article"
    return "standard"


def path_of(url):
    return url.replace(HOST, "") or "/"


def test_a_market_prefix_is_not_part_of_the_route():
    assert strip_locale_prefix("/de-at/legal-documents") == "/legal-documents"
    assert strip_locale_prefix("/fr/plug-types/congo") == "/plug-types/congo"
    assert strip_locale_prefix("/au/about/our-story") == "/about/our-story"
    # A two-letter segment that is not a market prefix must survive.
    assert strip_locale_prefix("/products/tv") == "/products/tv"
    assert strip_locale_prefix("/") == "/"


def test_translated_copies_share_one_route_signature():
    assert route_signature("/fr/plug-types/congo") == route_signature("/de/plug-types/congo")
    assert route_signature("/au/about/our-story") == route_signature("/br/about/our-story")
    assert route_signature("/de-at/team") == route_signature("/en-at/team")
    assert route_signature("/blog/one") != route_signature("/blog/two")


def test_one_route_in_many_markets_does_not_consume_the_budget():
    # One route published in twelve markets, plus eleven distinct routes.
    translated = [f"{HOST}/{m}/plug-types/congo" for m in
                  ("fr", "de", "es", "it", "pt", "nl", "pl", "cs", "da", "fi", "sv", "no")]
    distinct = [f"{HOST}/guide-{i}" for i in range(11)]
    selected = select_balanced_urls(translated + distinct, family_of, path_of, 12)

    signatures = {route_signature(path_of(url)) for url in selected}
    assert len(selected) == 12
    # Without the collapse the twelve translations alone could fill the budget.
    assert len(signatures) >= 11, f"budget spent on repeats: {sorted(signatures)}"
    congo = [url for url in selected if "plug-types" in url]
    assert len(congo) == 1, f"one route took {len(congo)} slots: {congo}"


def test_commercial_identity_is_reserved_before_editorial_volume():
    # A retailer whose sitemap is overwhelmingly editorial, as IKEA's sample was:
    # the commercial surface is a small minority, so a purely proportional
    # budget gives it only a handful of slots.
    editorial = [f"{HOST}/blog/post-{i}" for i in range(1000)]
    commercial = [f"{HOST}/products/item-{i}" for i in range(25)]
    selected = select_balanced_urls(editorial + commercial, family_of, path_of, 150)

    sampled_products = [url for url in selected if "/products/" in url]
    assert len(sampled_products) >= min(IDENTITY_RESERVE, 25), (
        f"only {len(sampled_products)} commercial pages survived a 1000-page editorial sitemap"
    )


def test_a_booking_marketplace_keeps_its_listing_routes():
    # Musement and Tiqets shaped: city and editorial pages dominate discovery.
    editorial = [f"{HOST}/blog/city-{i}" for i in range(200)]
    cities = [f"{HOST}/{m}/city-{i}" for m in ("us", "uk", "fr") for i in range(40)]
    listings = [f"{HOST}/tickets/attraction-{i}" for i in range(30)]
    selected = select_balanced_urls(editorial + cities + listings, family_of, path_of, 150)

    sampled_listings = [url for url in selected if "/tickets/" in url]
    assert len(sampled_listings) >= min(IDENTITY_RESERVE, 30), (
        f"only {len(sampled_listings)} listing routes sampled; the classifier cannot see a marketplace"
    )


def test_the_budget_is_still_a_hard_cap():
    urls = [f"{HOST}/products/item-{i}" for i in range(500)]
    assert len(select_balanced_urls(urls, family_of, path_of, 150)) == 150
    assert select_balanced_urls(urls, family_of, path_of, 0) == []


def test_path_prefix_discovery_is_bounded_to_top_fifty_segments():
    all_urls = []
    for index in range(70):
        count = 70 - index
        all_urls.extend([f"{HOST}/section-{index}/page-{n}" for n in range(count)])
    selected = all_urls[:150]
    report = sampling_report(all_urls, selected, family_of, path_of)

    assert len(report["path_prefixes_discovered"]) == 50
    assert set(report["path_prefixes_sampled"]) == set(report["path_prefixes_discovered"])
    assert "/section-0" in report["path_prefixes_discovered"]
    assert "/section-69" not in report["path_prefixes_discovered"]


def test_path_prefix_discovery_preserves_case_sensitive_first_segments():
    all_urls = [
        f"{HOST}/Products/item-a",
        f"{HOST}/products/item-b",
        f"{HOST}/Products/item-c",
    ]
    selected = list(all_urls)
    report = sampling_report(all_urls, selected, family_of, path_of)

    assert report["path_prefixes_discovered"]["/Products"] == 2
    assert report["path_prefixes_discovered"]["/products"] == 1
    assert report["path_prefixes_sampled"]["/Products"] == 2
    assert report["path_prefixes_sampled"]["/products"] == 1


def test_coverage_is_reported_by_route_and_market():
    translated = [f"{HOST}/{m}/plug-types/congo" for m in ("fr", "de", "es")]
    distinct = [f"{HOST}/products/item-{i}" for i in range(5)]
    all_urls = translated + distinct
    selected = select_balanced_urls(all_urls, family_of, path_of, 4)
    report = sampling_report(all_urls, selected, family_of, path_of)

    assert report["route_signatures_discovered"] == 6, report
    assert report["locale_variants_collapsed"] == 2, report
    assert set(report["markets_discovered"]) == {"fr", "de", "es"}
    assert report["identity_pages_in_sitemap"] == 5
    assert report["identity_pages_sampled"] >= 1
    assert report["path_prefixes_discovered"]["/products"] == 5
    assert sum(report["path_prefixes_sampled"].values()) == len(selected)
