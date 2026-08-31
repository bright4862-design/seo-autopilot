"""The pipeline recovers a marketplace the audit saw reported as a publisher.

This exercises the real order: select a 150-page budget from a discovery set
dominated by editorial and localized city pages, then classify what came back.

What this proves, precisely. The classifier change is load-bearing here:
without booking in `structural_competitor` the ticketing surface is sampled and
still loses to article volume. The sampler's identity reserve is *not* what
saves this fixture -- once `/tickets/` and `/attractions/` classify as
`activity_detail`, ordinary per-family allocation already fetches them. The
reserve earns its place when the commercial surface is a small minority of a
large sitemap, which `test_sampling_locale_and_identity.py` covers directly.

The route-classification fix is the quiet prerequisite for both: before it,
`/tickets/attraction-1` was a plain "standard" page, so no family logic and no
reserve could distinguish a ticketing route from any other page.
"""

from urllib.parse import urlparse

from app.review import run_review
from app.sampling import select_balanced_urls
from app.scanner import classify_template

HOST = "https://example.com"
BUDGET = 149


def family_of(url):
    return classify_template(urlparse(url).path or "/")


def path_of(url):
    return urlparse(url).path or "/"


def marketplace_sitemap():
    """Discovery dominated by editorial and localized city pages."""
    editorial = [
        f"{HOST}/blog/{slug}-guide"
        for slug in (
            "london", "paris", "rome", "madrid", "amsterdam", "berlin", "vienna",
            "prague", "lisbon", "dublin", "oslo", "athens", "porto", "milan", "venice",
        )
        for _ in range(12)
    ]
    # The same city route republished across five markets.
    localized = [f"{HOST}/{market}/city-{i}" for market in ("cs", "nl", "de", "fr", "es") for i in range(40)]
    ticketing = [f"{HOST}/tickets/attraction-{i}" for i in range(30)]
    ticketing += [f"{HOST}/attractions/museum-{i}" for i in range(15)]
    return editorial, localized, ticketing


def page(url, title):
    return {
        "url": url,
        "final_url": url,
        "status_code": 200,
        "title": title,
        "h1": title,
        "meta_description": title,
        "word_count": 250,
        "indexable": True,
        "page_template_family": "standard",
    }


def scan():
    editorial, localized, ticketing = marketplace_sitemap()
    sitemap = editorial + localized + ticketing
    sampled = select_balanced_urls(sitemap, family_of, path_of, BUDGET)
    pages = [page(f"{HOST}/", "Museum tickets and attractions")]
    pages += [
        page(url, "Attraction tickets" if ("/tickets/" in url or "/attractions/" in url) else "City guide")
        for url in sampled
    ]
    result = run_review({
        "website_url": HOST,
        "pages_found": len(sitemap),
        "pages_crawled": len(pages),
        "pages": pages,
    })
    return sampled, result


def test_the_ticketing_surface_survives_an_editorial_sitemap():
    sampled, _ = scan()
    assert len(sampled) == BUDGET
    ticketing = [url for url in sampled if "/tickets/" in url or "/attractions/" in url]
    assert len(ticketing) >= 24, (
        f"only {len(ticketing)} ticketing routes were fetched; the classifier cannot "
        "recognise a marketplace whose commercial surface was never sampled"
    )


def test_the_marketplace_is_classified_as_one():
    _, result = scan()
    fingerprint = result["site_fingerprint"]
    assert fingerprint["primary_archetype"] == "booking_experiences_marketplace", (
        f"reported as {fingerprint['primary_archetype']}: "
        f"{fingerprint['classification'].get('winning_reason')}"
    )
    assert fingerprint["classification"]["structural_signals"]["booking_dominant"] is True


def test_the_customer_is_told_the_right_place_to_start():
    _, result = scan()
    summary = result["plain_english_summary"]
    assert "booking / experiences marketplace" in summary, summary
    # The publisher playbook's opening advice must not survive.
    assert "pillar guides" not in summary, summary


def test_the_page_cap_is_not_widened_to_achieve_any_of_this():
    sampled, result = scan()
    assert len(sampled) == BUDGET
    assert result["site_fingerprint"]["pages_crawled"] <= 150
