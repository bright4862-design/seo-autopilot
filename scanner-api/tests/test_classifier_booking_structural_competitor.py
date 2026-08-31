"""Booking is a structural archetype, not a runner-up to article volume.

The 35-site production audit of 2026-08-31 reported Musement and Tiqets, both
booking marketplaces, as content/blog sites. `structural_competitor` capped
content_blog when SaaS, retail, finance, nonprofit or local identity was
present, and booking was the one structural archetype missing from that list,
so a marketplace whose sample skewed editorial lost on article volume alone.

These fixtures are route-shaped, not page captures: they assert what the
classifier does with a given route mix, which is the behaviour the cap governs.
"""

from app.review import run_review


def page(path, title, description="", host="https://example.com"):
    return {
        "url": f"{host}{path}",
        "final_url": f"{host}{path}",
        "status_code": 200,
        "title": title,
        "h1": title,
        "meta_description": description or title,
        "word_count": 250,
        "indexable": True,
        "page_template_family": "homepage" if path == "/" else "standard",
    }


def classify(pages, host="https://example.com"):
    result = run_review({
        "website_url": host,
        "pages_found": len(pages),
        "pages_crawled": len(pages),
        "pages": pages,
    })
    return result["site_fingerprint"]


def booking_marketplace_with_editorial_sample():
    """A ticketing marketplace whose sampled pages are mostly guides."""
    pages = [page("/", "Museum tickets and attractions", "Book museum tickets and attractions")]
    # The editorial surface the sampler over-collected in production.
    pages += [
        page(f"/blog/{slug}", f"Guide to {slug}")
        for slug in (
            "landmarks-in-london", "paris-guide", "rome-guide", "madrid-guide",
            "amsterdam-guide", "berlin-guide", "vienna-guide", "prague-guide",
            "lisbon-guide", "dublin-guide", "oslo-guide", "athens-guide",
        )
    ]
    # The routes that only exist because the business sells the experience.
    pages += [
        page("/tickets/louvre", "Louvre tickets"),
        page("/attractions/eiffel-tower", "Eiffel Tower"),
        page("/tickets/prado", "Prado Museum tickets"),
    ]
    return pages


def test_booking_marketplace_survives_an_editorial_heavy_sample():
    fingerprint = classify(booking_marketplace_with_editorial_sample())
    assert fingerprint["primary_archetype"] == "booking_experiences_marketplace", (
        "a ticketing marketplace was reported as a publisher: "
        f"{fingerprint['classification'].get('winning_reason')}"
    )


def test_booking_dominance_is_reported_so_the_decision_is_auditable():
    fingerprint = classify(booking_marketplace_with_editorial_sample())
    signals = fingerprint["classification"]["structural_signals"]
    assert signals["booking_dominant"] is True
    # The article surface is genuinely large; the point is that it no longer wins.
    assert signals["article_route_pages"] >= 12


def test_article_volume_alone_still_loses_to_booking_structure():
    # Doubling the editorial surface must not flip the result: the cap is on
    # content_blog, so more articles cannot overtake a structural competitor.
    pages = booking_marketplace_with_editorial_sample()
    pages += [page(f"/blog/extra-{i}", f"Extra guide {i}") for i in range(20)]
    fingerprint = classify(pages)
    assert fingerprint["primary_archetype"] == "booking_experiences_marketplace"


def test_a_genuine_publisher_is_still_a_publisher():
    # The cap must not manufacture a marketplace out of a magazine. No booking
    # route exists here, so booking dominance stays false and content_blog wins.
    pages = [page("/", "City culture magazine", "Reviews, interviews and city guides")]
    pages += [
        page(f"/blog/{slug}", f"Feature: {slug}")
        for slug in (
            "london-review", "paris-review", "rome-review", "madrid-review",
            "berlin-review", "vienna-review", "prague-review", "lisbon-review",
            "dublin-review", "oslo-review", "athens-review", "porto-review",
        )
    ]
    fingerprint = classify(pages)
    assert fingerprint["primary_archetype"] == "content_blog"
    assert fingerprint["classification"]["structural_signals"]["booking_dominant"] is False


def test_booking_dominance_needs_real_routes_not_homepage_words_alone():
    # Homepage wording is not evidence of a marketplace on its own. This is the
    # limit the audit's Musement and Tiqets cases actually sit behind: when the
    # 150-page sample surfaces no listing or ticket route, booking dominance is
    # false and the cap never applies. Fixing those two needs representative
    # sampling, not a louder classifier.
    pages = [page("/", "Things to do and guided tours", "Book an experience")]
    pages += [page(f"/blog/{i}", f"Guide {i}") for i in range(12)]
    fingerprint = classify(pages)
    signals = fingerprint["classification"]["structural_signals"]
    assert signals["booking_dominant"] is False
    assert fingerprint["primary_archetype"] == "content_blog"
