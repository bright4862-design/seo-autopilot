from urllib.parse import urlparse

from app.sampling import sampling_report, select_balanced_urls


def family(url):
    return urlparse(url).path.strip("/").split("/", 1)[0] or "homepage"


def path(url):
    return urlparse(url).path


def urls(name, count):
    return [f"https://example.com/{name}/{index}" for index in range(count)]


def test_balanced_sample_is_deterministic_and_fills_budget():
    candidates = urls("activity", 100) + urls("booking", 20) + urls("collection", 10)
    first = select_balanced_urls(candidates, family, path, 25)
    assert first == select_balanced_urls(candidates, family, path, 25)
    assert len(first) == 25


def test_material_families_receive_three_representatives():
    candidates = urls("activity", 100) + urls("booking", 20) + urls("collection", 10)
    selected = select_balanced_urls(candidates, family, path, 30)
    counts = {name: sum(family(url) == name for url in selected) for name in ["activity", "booking", "collection"]}
    assert all(count >= 3 for count in counts.values())


def test_trust_pages_are_reserved_before_family_quotas():
    candidates = urls("loan", 200) + [
        "https://example.com/contact/",
        "https://example.com/privacy/",
        "https://example.com/mentions-legales/",
    ]
    selected = select_balanced_urls(candidates, family, path, 25)
    assert all(url in selected for url in candidates[-3:])


def test_small_site_returns_everything_and_sitemapless_is_empty():
    candidates = urls("standard", 4)
    assert select_balanced_urls(candidates, family, path, 25) == candidates
    assert select_balanced_urls([], family, path, 25) == []


def test_small_budget_keeps_trust_guarantee():
    candidates = urls("loan", 100) + ["https://example.com/contact/", "https://example.com/privacy/"]
    selected = select_balanced_urls(candidates, family, path, 10)
    assert candidates[-2] in selected and candidates[-1] in selected
    assert len(selected) == 10


def test_sampling_report_exposes_coverage():
    candidates = urls("loan", 10) + urls("standard", 3) + ["https://example.com/contact/"]
    selected = select_balanced_urls(candidates, family, path, 8)
    report = sampling_report(candidates, selected, family, path)
    assert report["sampling_version"] == "balanced_sitemap_buckets_v1"
    assert report["sitemap_urls_discovered"] == 14
    assert report["sitemap_urls_sampled"] == 8
    assert report["trust_pages_in_sitemap"] == 1
    assert report["trust_pages_sampled"] == 1
