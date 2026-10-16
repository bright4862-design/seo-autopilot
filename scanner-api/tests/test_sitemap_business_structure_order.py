"""Discovery must reach distinct business structures before locale copies."""

import httpx
import pytest

from app import sitemap


ORIGIN = "https://activities.example"


def xml(urls, *, index=False):
    outer, item = ("sitemapindex", "sitemap") if index else ("urlset", "url")
    return f"<{outer}>" + "".join(
        f"<{item}><loc>{url}</loc></{item}>" for url in urls
    ) + f"</{outer}>"


def children():
    # A common marketplace index puts translations of one listing structure
    # before category/city entry points. "listing.other" is a distinct section.
    return [f"{ORIGIN}/{name}.xml" for name in (
        "listing.en", "listing.es", "listing.fr",
        "listing.other.en", "listing.other.fr",
        "category.en", "category.fr", "city.fr", "search-url.fr",
    )]


@pytest.mark.asyncio
async def test_truncated_discovery_reaches_distinct_structures_before_translations(monkeypatch):
    requested = []
    index = f"{ORIGIN}/sitemap.xml"
    targets = {url: f"{ORIGIN}/page-{number}" for number, url in enumerate(children())}

    async def fake_safe_get(_client, url, **_kwargs):
        requested.append(url)
        if url == f"{ORIGIN}/robots.txt":
            return httpx.Response(200, text=f"Sitemap: {index}")
        if url == index:
            return httpx.Response(200, text=xml(children(), index=True))
        return httpx.Response(200, text=xml([targets[url]]))

    monkeypatch.setattr(sitemap, "safe_get", fake_safe_get)
    diagnostics = {}
    found = await sitemap.load_sitemap_urls(
        object(), ORIGIN, "/", 5000, [], max_fetches=6, diagnostics=diagnostics,
    )

    # One index plus five child fetches must reach all five distinct sections.
    expected_sources = [children()[index] for index in (0, 3, 5, 7, 8)]
    assert requested[2:] == expected_sources
    assert set(found) == {targets[url] for url in expected_sources}
    assert diagnostics["sitemap_fetch_count"] == 6
    assert diagnostics["sitemap_fetch_limit_reached"] is True


def test_language_and_number_siblings_do_not_hide_distinct_listing_structures():
    listing = [f"{ORIGIN}/listing.fr-{number}.xml.gz" for number in range(1, 5)]
    other = f"{ORIGIN}/listing.other.fr.xml"
    category = f"{ORIGIN}/category.fr.xml"
    city = f"{ORIGIN}/city.fr.xml"
    search = f"{ORIGIN}/search-url.fr.xml"

    ranked = sitemap.rank_child_sitemaps(listing + [other, category, city, search], "/")

    assert set(ranked[:5]) == {listing[0], other, category, city, search}
    assert ranked[5:] == listing[1:]


def test_attached_pagination_numbers_keep_existing_family_diversity():
    activity = [f"{ORIGIN}/activity-sitemap{number}.xml" for number in range(1, 5)]
    city = f"{ORIGIN}/cities-sitemap.xml"

    ranked = sitemap.rank_child_sitemaps(activity + [city], "/")

    assert set(ranked[:2]) == {activity[0], city}
    assert ranked[2:] == activity[1:]


@pytest.mark.parametrize("hub", ["city", "cities", "ville", "villes", "location", "locations", "store", "stores"])
def test_city_and_location_filename_tokens_rank_before_editorial_and_lookalikes(hub):
    lookalike = f"{ORIGIN}/velocity-sitemap.xml"
    editorial = f"{ORIGIN}/blog-sitemap.xml"
    useful_hub = f"{ORIGIN}/{hub}-sitemap.xml"

    ranked = sitemap.rank_child_sitemaps([lookalike, editorial, useful_hub], "/")

    assert ranked == [useful_hub, editorial, lookalike]


def test_search_url_structure_is_diverse_without_assuming_it_is_commercial():
    search = f"{ORIGIN}/search-url.fr.xml"
    editorial = f"{ORIGIN}/blog-sitemap.xml"

    assert sitemap.rank_child_sitemaps([search, editorial], "/") == [editorial, search]


def test_directory_structures_remain_distinct_when_filenames_are_equal():
    activity = [f"{ORIGIN}/{market}/activities/sitemap.xml" for market in ("en", "es", "fr")]
    city = f"{ORIGIN}/fr/cities/sitemap.xml"
    category = f"{ORIGIN}/fr/categories/sitemap.xml"

    ranked = sitemap.rank_child_sitemaps(activity + [city, category], "/")

    assert set(ranked[:3]) == {activity[0], city, category}
    assert set(ranked) == set(activity + [city, category])


@pytest.mark.parametrize("hint", ["/fr", "/FR/", "/fr/fr"])
def test_verified_primary_market_is_first_within_each_structure(hint):
    ranked = sitemap.rank_child_sitemaps(children(), "/", primary_market_hint=hint)

    assert ranked[:5] == [children()[index] for index in (2, 4, 6, 7, 8)]
    assert set(ranked) == set(children())
    assert len(ranked) == len(children())


def test_exact_two_segment_market_is_preferred_over_language_only_matches():
    candidates = [f"{ORIGIN}/{market}/products/sitemap.xml" for market in (
        "be/fr", "fr/en", "fr/fr", "en",
    )]

    ranked = sitemap.rank_child_sitemaps(candidates, "/", primary_market_hint="/fr/fr")

    assert ranked[0] == candidates[2]
    assert set(ranked) == set(candidates)


@pytest.mark.parametrize("hint", [None, "", "/pricing", "/fr/pricing", "/fr/fr/extra", "https://example.com/fr"])
def test_absent_or_invalid_primary_market_does_not_guess_a_market(hint):
    assert sitemap.rank_child_sitemaps(children(), "/", primary_market_hint=hint) == sitemap.rank_child_sitemaps(children(), "/")


@pytest.mark.asyncio
async def test_loader_passes_market_hint_without_combining_language_url_buckets(monkeypatch):
    index = f"{ORIGIN}/sitemap.xml"
    english = f"{ORIGIN}/products.en.xml?generation=2"
    french = f"{ORIGIN}/products.fr.xml?generation=2"
    child_urls = [english, french]
    page_urls = {
        english: [f"{ORIGIN}/en/products/one?size=m&amp;color=red", f"{ORIGIN}/en/products/two"],
        french: [f"{ORIGIN}/fr/products/un?size=m&amp;color=red", f"{ORIGIN}/fr/products/deux"],
    }
    requested = []

    async def fake_safe_get(_client, url, **_kwargs):
        requested.append(url)
        if url == f"{ORIGIN}/robots.txt":
            return httpx.Response(200, text=f"Sitemap: {index}")
        if url == index:
            return httpx.Response(200, text=xml(child_urls, index=True))
        return httpx.Response(200, text=xml(page_urls[url]))

    monkeypatch.setattr(sitemap, "safe_get", fake_safe_get)
    found = await sitemap.load_sitemap_urls(
        object(), ORIGIN, "/", 3, [], max_fetches=3, primary_market_hint="/fr",
    )

    assert requested[2:] == [french, english]
    assert found == [
        f"{ORIGIN}/fr/products/un?size=m&color=red",
        f"{ORIGIN}/en/products/one?size=m&color=red",
        f"{ORIGIN}/fr/products/deux",
    ]


def test_business_structure_order_preserves_exact_child_url_identities():
    urls = [
        f"{ORIGIN}/products.en.xml?cursor=2",
        f"{ORIGIN}/products.fr.xml?cursor=1",
        f"{ORIGIN}/products.fr.xml?cursor=2",
        f"{ORIGIN}/City.fr.xml.gz?Case=Kept",
    ]

    ranked = sitemap.rank_child_sitemaps(urls + [urls[0]], "/", primary_market_hint="/fr")

    assert set(ranked) == set(urls)
    assert len(ranked) == len(urls)


@pytest.mark.asyncio
async def test_malformed_child_keeps_existing_isolated_failure_behavior(monkeypatch):
    index = f"{ORIGIN}/sitemap.xml"
    malformed = "https://[invalid/sitemap-category.fr.xml"
    valid = f"{ORIGIN}/products.fr.xml"
    target = f"{ORIGIN}/fr/products/kept"

    async def fake_safe_get(_client, url, **_kwargs):
        if url == f"{ORIGIN}/robots.txt":
            return httpx.Response(200, text=f"Sitemap: {index}")
        if url == index:
            return httpx.Response(200, text=xml([malformed, valid], index=True))
        if url == malformed:
            raise httpx.InvalidURL("invalid child URL")
        return httpx.Response(200, text=xml([target]))

    monkeypatch.setattr(sitemap, "safe_get", fake_safe_get)
    diagnostics = {}
    found = await sitemap.load_sitemap_urls(
        object(), ORIGIN, "/", 20, [], diagnostics=diagnostics, primary_market_hint="/fr",
    )

    assert found == [target]
    assert diagnostics["sitemap_source_failures"][malformed] == "sitemap_fetch_exception"
