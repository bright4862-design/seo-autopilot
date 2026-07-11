from app.sitemap import (
    interleave_by_family,
    interleave_url_families,
    rank_child_sitemaps,
    sitemap_family_key,
)


def activity_children(count=20):
    return [f"https://example.com/sitemap-activites-{i}.xml" for i in range(count)]


def test_booking_child_sitemap_is_not_starved_by_activity_family():
    children = activity_children() + [
        "https://example.com/sitemap-reservation.xml",
        "https://example.com/sitemap-collections.xml",
    ]
    ranked = rank_child_sitemaps(children, "/")
    assert ranked.index("https://example.com/sitemap-reservation.xml") < 5
    assert ranked.index("https://example.com/sitemap-collections.xml") < 5


def test_all_funbooker_children_fit_under_fetch_cap():
    children = activity_children() + [
        "https://example.com/sitemap-pages.xml",
        "https://example.com/sitemap-reservation.xml",
        "https://example.com/sitemap-collections.xml",
        "https://example.com/sitemap-blog.xml",
    ]
    assert len(rank_child_sitemaps(children, "/")) == 24


def test_one_large_family_cannot_starve_booking():
    children = activity_children(100) + ["https://example.com/sitemap-booking.xml"]
    ranked = rank_child_sitemaps(children, "/")
    assert ranked.index("https://example.com/sitemap-booking.xml") < 10


def test_family_key_collapses_numbered_siblings():
    assert sitemap_family_key("https://x.com/sitemap-activites-1.xml") == "sitemap-activites"
    assert sitemap_family_key("https://x.com/sitemap-activites-20.xml") == "sitemap-activites"


def test_family_key_strips_non_numbered_extension():
    assert sitemap_family_key("https://x.com/sitemap-reservation.xml") == "sitemap-reservation"


def test_interleave_round_robins_families():
    children = activity_children(3) + ["https://x.com/sitemap-booking.xml"]
    ordered = interleave_by_family(children)
    assert ordered[1] == "https://x.com/sitemap-booking.xml"


def test_trust_and_booking_sitemaps_are_prioritized():
    children = activity_children(20) + [
        "https://x.com/sitemap-privacy.xml",
        "https://x.com/sitemap-booking.xml",
    ]
    ranked = rank_child_sitemaps(children, "/")
    assert ranked.index("https://x.com/sitemap-privacy.xml") < 5
    assert ranked.index("https://x.com/sitemap-booking.xml") < 5


# URL-level family diversity before the global discovery cap. Funbooker's live
# failure had family_totals={"activity_detail": 5000}: one 8,478-URL activity
# child filled the complete discovery universe before booking or collections.
DISCOVERY_LIMIT = 5000


def _funbooker_family_urls():
    return {
        "sitemap-activites": [f"/fr/annonce/a{i}/voir" for i in range(8478)],
        "sitemap-reservation": [f"/reservation/{i}" for i in range(272)],
        "sitemap-collections": [f"/collections/c{i}" for i in range(66)],
        "sitemap-pages": [f"/p{i}" for i in range(20)],
    }


def _family_of(url):
    if "/annonce/" in url:
        return "activity_detail"
    if "/reservation/" in url:
        return "booking_or_checkout"
    if "/collections/" in url:
        return "collection_page"
    return "standard"


def _discovery_universe():
    urls = interleave_url_families(_funbooker_family_urls())[:DISCOVERY_LIMIT]
    totals = {}
    for url in urls:
        family = _family_of(url)
        totals[family] = totals.get(family, 0) + 1
    return urls, totals


def test_one_huge_child_sitemap_cannot_consume_the_discovery_limit():
    urls, totals = _discovery_universe()
    assert len(urls) == DISCOVERY_LIMIT
    assert "activity_detail" in totals
    assert "booking_or_checkout" in totals
    assert "collection_page" in totals
    assert "standard" in totals


def test_small_families_survive_the_cap_entirely():
    """Small booking, collection, and page families should survive completely."""
    _, totals = _discovery_universe()
    assert totals["booking_or_checkout"] == 272
    assert totals["collection_page"] == 66
    assert totals["standard"] == 20


def test_dominant_family_still_takes_the_remaining_capacity():
    _, totals = _discovery_universe()
    assert totals["activity_detail"] > DISCOVERY_LIMIT * 0.8


def test_interleave_url_families_is_deterministic():
    families = _funbooker_family_urls()
    assert interleave_url_families(families)[:500] == interleave_url_families(families)[:500]


def test_interleave_url_families_handles_empty_input():
    assert interleave_url_families({}) == []
    assert interleave_url_families({"a": []}) == []
