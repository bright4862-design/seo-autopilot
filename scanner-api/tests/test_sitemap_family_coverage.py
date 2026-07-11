from app.sitemap import interleave_by_family, rank_child_sitemaps, sitemap_family_key


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
