"""Presentation-contract regressions for Python Review and frontend handoff."""

from app.review import run_review


def _run(pages):
    return run_review({
        "website_url": "https://example.com",
        "pages": pages,
        "scan_coverage": {
            "pages_found": max(10, len(pages)),
            "pages_crawled": len(pages),
            "sampled_pages_sent_to_ai": len(pages),
        },
    })


def _page(path, family="standard", **extra):
    return {
        "final_url": f"https://example.com{path}",
        "status_code": 200,
        "h1_count": 1,
        "meta_description": "Useful description",
        "canonical": f"https://example.com{path}",
        "page_template_family": family,
        **extra,
    }


def _fix(result, rule):
    return next(fix for fix in result["cleaned_fixes"] if fix.get("rule") == rule)


def test_activity_image_alt_card_has_specific_title_and_steps():
    pages = [
        _page(f"/fr/annonce/activity-{index}/voir", "activity_detail", image_missing_alt_count=2)
        for index in range(3)
    ]
    card = _fix(_run(pages), "image_alt_text")
    steps = " ".join(card["what_to_do_steps"]).lower()

    assert card["title"] == "Add missing image descriptions to activity/detail pages"
    assert "alt text" in steps
    assert "shared image component" in steps
    assert "routing" not in steps
    assert "canonical, schema" not in steps


def test_legal_canonical_card_has_specific_title_and_steps():
    pages = [
        _page("/fr/page/cgu", "legal_info", canonical=""),
        _page("/fr/page/mentions-legales", "legal_info", canonical=""),
    ]
    card = _fix(_run(pages), "canonical_missing")
    steps = " ".join(card["what_to_do_steps"]).lower()

    assert card["title"] == "Add canonical URLs to legal info pages"
    assert "self-referencing canonical" in steps
    assert "rendered page source" in steps
    assert "schema, indexability" not in steps


def test_single_missing_meta_description_has_singular_copy():
    card = _fix(
        _run([_page("/fr/annonce/activity/voir", "activity_detail", meta_description="")]),
        "missing_meta_description",
    )
    steps = " ".join(card["what_to_do_steps"]).lower()

    assert card["title"] == "Add a meta description to the affected page"
    assert "meta description" in steps
    assert "unique to the page" in steps


def test_single_missing_h1_has_singular_copy():
    card = _fix(_run([_page("/fr/review/page", h1_count=0)]), "missing_h1")
    steps = " ".join(card["what_to_do_steps"]).lower()

    assert card["title"] == "Add an H1 to the affected page"
    assert "one clear h1" in steps
    assert "h2 or h3" in steps


def test_cross_cutting_429_card_is_family_neutral():
    families = {
        "collection_page": ["/fr/category/escape-game", "/fr/category/karting"],
        "activity_detail": ["/fr/annonce/a1/voir", "/fr/annonce/a2/voir"],
        "location_landing": ["/fr/lieu/lyon"],
        "standard": ["/fr/theme/cadeau"],
    }
    pages = [
        _page(url, family, status_code=429)
        for family, urls in families.items()
        for url in urls
    ]
    card = _fix(_run(pages), "rate_limited_page")

    assert card["page_template_family"] == "mixed"
    assert card["title"] == "Check pages blocked by rate limiting"
    assert len(card["affected_pages"]) == 6
