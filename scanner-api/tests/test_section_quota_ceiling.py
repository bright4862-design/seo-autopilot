"""Section ceilings apply to commercial reserves as well as quota fill."""
from collections import Counter
from urllib.parse import urlparse

import pytest

from app.extract import classify_template
from app.sampling import select_balanced_urls


@pytest.mark.parametrize("budget", [149, 499])
@pytest.mark.parametrize("section_count", [3, 4])
def test_commercial_reserve_cannot_exceed_feasible_section_ceiling(budget, section_count):
    sections = ("services", "solutions", "stores", "insights")[:section_count]
    urls = [f"https://example.com/{section}/page-{index}"
            for section in sections for index in range(1000)]
    path_of = lambda url: urlparse(url).path
    family_of = lambda url: classify_template(path_of(url))

    selected = select_balanced_urls(urls, family_of, path_of, budget)

    counts = Counter(path_of(url).split("/")[1] for url in selected)
    assert len(selected) == len(set(selected)) == budget
    assert set(counts) == set(sections)
    assert all(3 <= count <= budget * 0.4 for count in counts.values())
    assert selected == select_balanced_urls(list(reversed(urls)), family_of, path_of, budget)


def test_infeasible_ceiling_does_not_discard_available_scan_budget():
    urls = [f"https://example.com/services/page-{index}" for index in range(500)]
    urls += [f"https://example.com/solutions/page-{index}" for index in range(3)]
    path_of = lambda url: urlparse(url).path
    selected = select_balanced_urls(urls, lambda url: classify_template(path_of(url)), path_of, 149)

    assert len(selected) == len(set(selected)) == 149
    assert sum("/solutions/" in url for url in selected) == 3


@pytest.mark.parametrize("budget", [149, 499])
def test_navigation_floor_cannot_displace_an_existing_section_hub(budget):
    origin = "https://example.com"
    sections = [f"section-{index}" for index in range(40)]
    hubs = {f"{origin}/{section}" for section in sections}
    urls = sorted(hubs) + [f"{origin}/{section}/page-{index}"
                          for section in sections for index in range(100)]
    navigation = [f"{origin}/{sections[0]}/page-{index}" for index in range(int(budget * 0.15))]
    path_of = lambda url: urlparse(url).path

    selected = select_balanced_urls(
        urls, lambda url: classify_template(path_of(url)), path_of, budget,
        homepage_links=navigation,
    )

    assert hubs.issubset(selected)
    assert set(navigation).issubset(selected)
    assert len(selected) == len(set(selected)) == budget


@pytest.mark.asyncio
async def test_feasible_30_percent_500_crawl_keeps_navigation_and_known_hubs(mock_network):
    from app import scanner
    from tests import fixtures as fx

    origin = "https://early-hubs.example"
    sections = [f"section-{index}" for index in range(40)]
    hubs = {f"{origin}/{section}" for section in sections}
    urls = sorted(hubs) + [f"{origin}/{section}/page-{index}"
                          for section in sections for index in range(100)]
    navigation = [f"{origin}/{sections[0]}/page-{index}" for index in range(74)]
    mock_network({
        origin + "/": fx._html(fx._page("Home", links=navigation)),
        origin + "/sitemap.xml": fx._xml(fx._sitemap(urls)),
        **{url: fx._html(fx._page(url)) for url in urls},
    })

    # Internal staged planning is separate from the synchronous /scan ingress.
    state = await scanner.plan_scan(origin + "/", scan_mode="standard_500", staged=True, concurrency=8)
    assert len(state.first_pass_urls) <= 150
    await scanner.crawl_batch(state, max_pages=150)

    retained = {page["url"] for page in state.pages}
    assert origin + "/" in retained
    assert hubs.issubset(retained)
    assert set(navigation).issubset(retained)
    assert state.rescored is True
    assert len(retained) == 150
