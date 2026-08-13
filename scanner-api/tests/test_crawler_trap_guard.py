from app.artifact_filter import is_artifact_url, record_artifact
from app.crawler_trap_guard import CRAWL_TRAP_GUARD_VERSION, crawl_trap_reason


def test_normal_faceted_and_paginated_urls_remain_crawlable():
    urls = [
        "https://example.com/products?color=red&size=m&page=2&sort=price",
        "https://example.com/search?q=summer+dresses&brand=one&brand=two",
        "https://example.com/blog/benefits-of-using-bridge-loans-for-real-estate-transactions",
        "https://example.com/category/subcategory/product-name-with-a-long-human-readable-slug",
    ]
    for url in urls:
        assert crawl_trap_reason(url) == ""
        assert is_artifact_url(url) is False


def test_extreme_query_pair_explosion_is_suppressed():
    query = "&".join(f"filter{i}=value{i}" for i in range(21))
    url = f"https://example.com/products?{query}"
    assert crawl_trap_reason(url) == "crawler_trap_query_pair_explosion"
    assert is_artifact_url(url) is True


def test_repeated_query_key_trap_is_suppressed():
    query = "&".join(f"filter=value{i}" for i in range(7))
    url = f"https://example.com/products?{query}"
    assert crawl_trap_reason(url) == "crawler_trap_repeated_query_key"
    assert is_artifact_url(url) is True


def test_extreme_path_depth_is_suppressed():
    path = "/".join(f"segment{i}" for i in range(41))
    url = f"https://example.com/{path}"
    assert crawl_trap_reason(url) == "crawler_trap_path_depth"
    assert is_artifact_url(url) is True


def test_repeated_path_segment_trap_is_suppressed():
    url = "https://example.com/" + "/".join(["calendar"] * 9)
    assert crawl_trap_reason(url) == "crawler_trap_repeated_path_segment"
    assert is_artifact_url(url) is True


def test_oversized_url_is_suppressed():
    url = "https://example.com/page?token=" + ("a" * 4100)
    assert crawl_trap_reason(url) == "crawler_trap_oversized_url"
    assert is_artifact_url(url) is True


def test_existing_wordpress_artifact_filter_behavior_is_preserved():
    assert is_artifact_url("https://example.com/wp-admin/") is True
    assert is_artifact_url("https://example.com/post?replytocom=123") is True


def test_trap_artifact_records_explainable_reason_and_version():
    target = []
    query = "&".join(f"filter=value{i}" for i in range(7))
    url = f"https://example.com/products?{query}"

    record_artifact(target, url, "internal_link", "/products", "Next filters")

    assert len(target) == 1
    assert target[0]["suppressed_from_crawl"] is True
    assert target[0]["url_suspicion_reasons"] == ["crawler_trap_repeated_query_key"]
    assert target[0]["guard_version"] == CRAWL_TRAP_GUARD_VERSION
