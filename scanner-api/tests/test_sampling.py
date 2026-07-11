"""Balanced sitemap-bucket sampling regressions using measured site distributions."""
import pytest

from app.sampling import SAMPLING_VERSION, is_trust_path, sampling_report, select_balanced_urls

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
