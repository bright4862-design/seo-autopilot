from app.sitemap import normalize_sitemap_page_url, rank_child_sitemaps


def test_sitemap_page_urls_normalize_www_to_origin_host():
    assert normalize_sitemap_page_url(
        "https://www.centerstreetlending.com/blog/benefits-of-using-bridge-loans-for-real-estate-transactions",
        "https://centerstreetlending.com",
    ) == "https://centerstreetlending.com/blog/benefits-of-using-bridge-loans-for-real-estate-transactions"


def test_sitemap_page_urls_normalize_apex_to_www_origin_host():
    assert normalize_sitemap_page_url(
        "https://centerstreetlending.com/loans/fix-and-flip",
        "https://www.centerstreetlending.com",
    ) == "https://www.centerstreetlending.com/loans/fix-and-flip"


def test_sitemap_page_urls_do_not_cross_unrelated_hosts():
    assert normalize_sitemap_page_url(
        "https://example.com/loans/fix-and-flip",
        "https://centerstreetlending.com",
    ) == "https://example.com/loans/fix-and-flip"


def test_page_sitemaps_rank_before_blog_sitemaps():
    ranked = rank_child_sitemaps([
        "https://www.centerstreetlending.com/post-sitemap.xml",
        "https://www.centerstreetlending.com/page-sitemap.xml",
        "https://www.centerstreetlending.com/category-sitemap.xml",
        "https://www.centerstreetlending.com/author-sitemap.xml",
    ], "/")
    assert ranked[:2] == [
        "https://www.centerstreetlending.com/page-sitemap.xml",
        "https://www.centerstreetlending.com/category-sitemap.xml",
    ]
    assert ranked[-1] == "https://www.centerstreetlending.com/author-sitemap.xml"
