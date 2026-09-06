"""Balanced sitemap-bucket sampling regressions using measured site distributions."""
import pytest

from app.sampling import (
    SAMPLING_VERSION,
    enrich_checked_coverage,
    is_trust_path,
    sampling_report,
    select_balanced_urls,
)

BUDGET = 150


def _universe(spec):
    urls, family_by_url = [], {}
    for family, (count, template) in spec.items():
        for i in range(count):
            url = template.format(i=i)
            urls.append(url)
            family_by_url[url] = family
    return urls, (lambda url: family_by_url[url]), (lambda url: url.replace("https://x.com", ""))


FUNBOOKER = {
    "activity_detail": (8478, "https://x.com/fr/annonce/a{i}/voir"),
    "standard": (1075, "https://x.com/p{i}"),
    "booking_or_checkout": (272, "https://x.com/checkout/{i}"),
    "collection_page": (66, "https://x.com/collections/c{i}"),
    "route_boundary": (5, "https://x.com/login{i}"),
    "archive": (2, "https://x.com/tag/t{i}"),
}
PRETTO = {
    "loan_program": (1308, "https://x.com/pret-immobilier/{i}"),
    "guide_article": (537, "https://x.com/blog/g{i}"),
    "standard": (156, "https://x.com/s{i}"),
    "legal_info": (8, "https://x.com/mentions-legales/{i}"),
    "contact": (2, "https://x.com/contact/{i}"),
    "conversion": (1, "https://x.com/devis/{i}"),
}
CENTER_STREET = {
    "guide_article": (258, "https://x.com/blog/b{i}"),
    "location_landing": (60, "https://x.com/locations/l{i}"),
    "standard": (12, "https://x.com/s{i}"),
    "loan_program": (6, "https://x.com/loans/{i}"),
    "conversion": (3, "https://x.com/apply-now{i}"),
    "legal_info": (2, "https://x.com/privacy{i}"),
    "contact": (1, "https://x.com/contact{i}"),
}


def _counts(spec):
    urls, family, path = _universe(spec)
    selected = select_balanced_urls(urls, family, path, BUDGET)
    counts = {}
    for url in selected:
        counts[family(url)] = counts.get(family(url), 0) + 1
    return urls, selected, counts, family, path


@pytest.mark.parametrize("spec", [FUNBOOKER, PRETTO, CENTER_STREET])
def test_budget_is_respected_and_filled(spec):
    _, selected, _, _, _ = _counts(spec)
    assert len(selected) == BUDGET
    assert len(set(selected)) == BUDGET


@pytest.mark.parametrize("spec", [FUNBOOKER, PRETTO, CENTER_STREET])
def test_no_material_family_is_never_sampled(spec):
    _, _, counts, _, _ = _counts(spec)
    for family, (count, _) in spec.items():
        if count >= 2:
            assert counts.get(family, 0) >= 1


def test_pretto_trust_pages_are_always_sampled():
    _, selected, counts, _, path = _counts(PRETTO)
    assert any(is_trust_path(path(url)) for url in selected)
    assert counts.get("legal_info", 0) >= 1
    assert counts.get("contact", 0) >= 1


def test_center_street_location_pages_are_sampled():
    assert _counts(CENTER_STREET)[2].get("location_landing", 0) >= 3


def test_funbooker_booking_and_collection_pages_are_sampled():
    counts = _counts(FUNBOOKER)[2]
    assert counts.get("booking_or_checkout", 0) >= 3
    assert counts.get("collection_page", 0) >= 3


@pytest.mark.parametrize("spec,money", [(FUNBOOKER, "activity_detail"), (PRETTO, "loan_program")])
def test_money_family_keeps_dominant_share(spec, money):
    _, selected, counts, _, _ = _counts(spec)
    assert counts[money] > len(selected) * 0.5


@pytest.mark.parametrize("spec", [FUNBOOKER, PRETTO, CENTER_STREET])
def test_selection_is_deterministic(spec):
    urls, family, path = _universe(spec)
    assert select_balanced_urls(urls, family, path, BUDGET) == select_balanced_urls(urls, family, path, BUDGET)


def test_small_site_is_crawled_entirely():
    urls, family, path = _universe({"standard": (10, "https://x.com/p{i}")})
    assert select_balanced_urls(urls, family, path, BUDGET) == urls


def test_sitemapless_site_returns_empty_selection():
    assert select_balanced_urls([], lambda url: "x", lambda url: "/", BUDGET) == []


def test_small_budget_still_guarantees_trust_and_coverage():
    urls, family, path = _universe(PRETTO)
    selected = select_balanced_urls(urls, family, path, 25)
    assert len(selected) == 25
    assert any(is_trust_path(path(url)) for url in selected)


def test_sampling_report_exposes_coverage_evidence():
    urls, selected, _, family, path = _counts(PRETTO)
    report = sampling_report(urls, selected, family, path)
    assert report["sampling_version"] == SAMPLING_VERSION
    assert report["sitemap_urls_discovered"] == len(urls)
    assert report["sitemap_urls_sampled"] == BUDGET
    assert report["trust_pages_in_sitemap"] >= 10
    assert report["trust_pages_sampled"] >= 1
    assert "legal_info" not in report["families_never_sampled"]


def test_locale_prefixed_cms_legal_routes_are_trust_pages():
    assert is_trust_path("/fr/page/cgu")
    assert is_trust_path("/fr/page/mentions-legales")
    assert is_trust_path("/en/pages/privacy-policy")
    assert is_trust_path("/fr/contact")
    assert is_trust_path("/de/security")
    assert not is_trust_path("/fr/annonce/domaine-de-locguenole-a-kervignac-56/voir")


def test_funbooker_legal_pages_are_reserved_and_reported():
    activities = [f"https://x.com/fr/annonce/activity-{index}/voir" for index in range(20)]
    legal_pages = [
        "https://x.com/fr/page/cgu",
        "https://x.com/fr/page/mentions-legales",
    ]
    urls = activities + legal_pages

    def family(url):
        return "legal_info" if url in legal_pages else "activity_detail"

    def path(url):
        return url.replace("https://x.com", "")

    selected = select_balanced_urls(urls, family, path, 5)
    report = sampling_report(urls, selected, family, path)

    assert all(url in selected for url in legal_pages)
    assert report["trust_pages_in_sitemap"] == 2
    assert report["trust_pages_sampled"] == 2
    assert report["family_sampled"]["legal_info"] == 2


# ---------------------------------------------------------------------------
# Selected URLs are not checked pages.
#
# The September 6 matrix stopped on this: Salt & Straw reported 345 pages found
# and 39 checked, while the section rows underneath claimed 54 + 29 + 35 + 30 =
# 148 "sampled". Stumptown, Fly By Jing and Fishwife all showed the same 148
# against 39 or 40. `sampling_report()` builds those prefix counts from the
# URLs chosen before the crawl, so the number measures an intention, and the
# page labelled it an observation.
# ---------------------------------------------------------------------------

SALT_AND_STRAW_PREFIXES = {"/products": 55, "/collections": 40, "/blogs": 33, "/pages": 20}


def _salt_and_straw():
    """345 discovered URLs, 148 selected for the attempt, 39 pages actually returned."""
    all_urls, selected = [], []
    for prefix, count in SALT_AND_STRAW_PREFIXES.items():
        for index in range(count):
            all_urls.append(f"https://x.com{prefix}/{index}")
    all_urls += [f"https://x.com/other/{index}" for index in range(197)]
    for prefix, count in (("/products", 54), ("/collections", 29), ("/blogs", 35), ("/pages", 30)):
        selected += [f"https://x.com{prefix}/{index}" for index in range(count)]
    # What the crawler actually came back with: far fewer, and not proportional.
    checked = (
        [{"url": f"https://x.com/products/{index}"} for index in range(12)]
        + [{"url": f"https://x.com/collections/{index}"} for index in range(9)]
        + [{"url": f"https://x.com/blogs/{index}"} for index in range(8)]
        + [{"url": f"https://x.com/pages/{index}"} for index in range(7)]
        + [{"url": "https://x.com/"}, {"url": "https://x.com/about"}, {"url": "https://x.com/contact"}]
    )
    return all_urls, selected, checked


def _path_of(url):
    return url.replace("https://x.com", "") or "/"


def test_sampling_evidence_separates_selected_urls_from_checked_pages():
    all_urls, selected, checked = _salt_and_straw()
    report = sampling_report(all_urls, selected, lambda url: "standard", _path_of)
    enrich_checked_coverage(report, checked, _path_of)

    assert report["sitemap_urls_selected"] == 148
    assert report["pages_checked"] == 39
    # The invariant the UI depends on: no section may claim more checked pages
    # than the crawl produced in total.
    assert sum(report["path_prefixes_checked"].values()) <= 39
    assert report["path_prefixes_selected"] != report["path_prefixes_checked"]


def test_no_prefix_claims_more_checked_pages_than_the_crawl_returned():
    all_urls, selected, checked = _salt_and_straw()
    report = sampling_report(all_urls, selected, lambda url: "standard", _path_of)
    enrich_checked_coverage(report, checked, _path_of)

    assert report["path_prefixes_selected"]["/products"] == 54
    assert report["path_prefixes_checked"]["/products"] == 12
    for prefix, count in report["path_prefixes_checked"].items():
        assert count <= report["pages_checked"], prefix


def test_pages_without_a_first_segment_are_counted_but_not_attributed():
    """The homepage is checked; it belongs to no prefix.

    Forcing selected and checked to reconcile per-prefix would either invent a
    section for the root or drop the page from the total. Neither is honest, so
    the sum of prefix counts is bounded by, not equal to, pages_checked.
    """
    all_urls, selected, checked = _salt_and_straw()
    report = sampling_report(all_urls, selected, lambda url: "standard", _path_of)
    enrich_checked_coverage(report, checked, _path_of)

    assert sum(report["path_prefixes_checked"].values()) < report["pages_checked"]


def test_the_selection_fields_keep_their_historical_meaning():
    all_urls, selected, checked = _salt_and_straw()
    report = sampling_report(all_urls, selected, lambda url: "standard", _path_of)
    before = dict(report["path_prefixes_selected"])
    enrich_checked_coverage(report, checked, _path_of)

    assert report["path_prefixes_selected"] == before, "enrichment must not rewrite selection evidence"
    assert report["sampling_version"] != "balanced_sitemap_buckets_v5_locale_collapsed_identity_scope_discovery_bounded_prefixes", (
        "a semantic split in this payload needs its own version marker"
    )


def test_the_crawler_records_checked_coverage_after_the_page_cap():
    """A helper nothing calls is not a fix.

    The enrichment has to run once, after `pages = pages[:max_pages]`, because
    that cap is the last thing that can remove a page. Called earlier it would
    count pages the result never contains -- overstating coverage in the
    opposite direction from the bug it exists to fix.
    """
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "app" / "scanner.py").read_text(encoding="utf-8")
    cap = source.index("pages = pages[:max_pages]")
    call = source.index("enrich_checked_coverage(sampling_evidence, pages, path_of)")
    assert call > cap, "checked coverage is recorded before the page cap is applied"
    assert source.count("enrich_checked_coverage(") == 1, "checked coverage must be recorded exactly once"

    # And the population must be the one pages_crawled counts.
    assert '"pages_crawled": len(pages)' in source
