from app.review import run_review


def _page(path):
    url = f"https://example.com{path}"
    return {
        "final_url": url,
        "status_code": 200,
        "canonical": url,
        "h1_count": 1,
        "meta_description": "Clear description",
        "image_missing_alt_count": 1,
        "page_template_family": "contact",
    }


def _run(pages):
    return run_review({
        "website_url": "https://example.com",
        "pages": pages,
        "scan_coverage": {
            "pages_found": len(pages),
            "pages_crawled": len(pages),
            "sampled_pages_sent_to_ai": len(pages),
        },
    })


def _image_alt_fix(result):
    return next(
        fix for fix in result["cleaned_fixes"]
        if fix.get("rule") == "image_alt_text"
    )


def test_grouped_page_pattern_image_alt_fix_is_owner_or_web_person_work():
    fix = _image_alt_fix(_run([_page("/contact"), _page("/contact-sales")]))

    assert fix["source"].startswith("page_pattern:image_alt_text:")
    assert len(fix["affected_pages"]) == 2
    assert fix["who_can_do_this"] == "you_or_your_web_person"
    assert fix["difficulty"] == "moderate"
    assert fix["requires_developer"] is False
    assert fix.get("requires_approval") is True


def test_single_page_image_alt_pattern_is_owner_or_web_person_work():
    # A page-pattern image-alt card may be a CMS field or a template change, so
    # it should not claim that a developer is always required.
    fix = _image_alt_fix(_run([_page("/contact")]))

    assert len(fix["affected_pages"]) == 1
    assert fix["source"].startswith("page_pattern:image_alt_text:")
    assert fix["who_can_do_this"] == "you_or_your_web_person"
    assert fix["difficulty"] == "moderate"
    assert fix["requires_developer"] is False
    assert fix.get("requires_approval") is True


def test_single_sampled_activity_page_collapses_raw_singleton_and_keeps_flexible_owner():
    """Funbooker regression: a raw singleton and generator card for one activity URL collapse."""
    pages = [{
        "final_url": "https://funbooker.com/fr/annonce/kaskad/voir",
        "status_code": 200,
        "h1_count": 1,
        "meta_description": "d",
        "canonical": "https://funbooker.com/fr/annonce/kaskad/voir",
        "image_missing_alt_count": 6,
        "page_template_family": "activity_detail",
    }]
    raw = [{
        "rule": "image_alt_text",
        "category": "image_alt_text",
        "title": "Add useful image descriptions",
        "page_url": "https://funbooker.com/fr/annonce/kaskad/voir",
        "affected_pages": ["https://funbooker.com/fr/annonce/kaskad/voir"],
    }]
    result = run_review({
        "website_url": "https://funbooker.com",
        "pages": pages,
        "raw_fixes": raw,
        "scan_coverage": {
            "pages_found": 1200,
            "pages_crawled": 1,
            "sampled_pages_sent_to_ai": 1,
        },
    })
    image_fixes = [
        fix for fix in result["cleaned_fixes"]
        if "image" in (
            fix.get("category", "")
            + fix.get("rule", "")
            + str(fix.get("issue_title", ""))
        ).lower()
    ]

    assert len(image_fixes) == 1
    assert image_fixes[0]["source"] == "page_pattern:image_alt_text:activity_detail"
    assert image_fixes[0]["who_can_do_this"] == "you_or_your_web_person"
    assert image_fixes[0]["requires_developer"] is False


def test_trailing_slash_variants_produce_one_card():
    "/fr and /fr/ represent the same page and must collapse into one image-alt card."
    pages = [
        {
            "final_url": "https://s.com/fr",
            "status_code": 200,
            "h1_count": 1,
            "meta_description": "d",
            "canonical": "",
            "image_missing_alt_count": 3,
        },
        {
            "final_url": "https://s.com/fr/",
            "status_code": 200,
            "h1_count": 1,
            "meta_description": "d",
            "canonical": "",
            "image_missing_alt_count": 3,
        },
    ]
    result = run_review({
        "website_url": "https://s.com",
        "pages": pages,
        "scan_coverage": {
            "pages_found": 50,
            "pages_crawled": 2,
            "sampled_pages_sent_to_ai": 2,
        },
    })
    image_fixes = [
        fix for fix in result["cleaned_fixes"]
        if "image" in (
            fix.get("category", "")
            + fix.get("rule", "")
            + str(fix.get("issue_title", ""))
        ).lower()
    ]

    assert len(image_fixes) == 1
    assert image_fixes[0]["affected_pages"] == ["/fr"]


def test_clean_path_normalizes_trailing_slash():
    from app.review import clean_path

    assert clean_path("https://s.com/fr/") == "/fr"
    assert clean_path("/fr/") == "/fr"
    assert clean_path("/fr") == "/fr"
    assert clean_path("https://s.com/") == "/"
    assert clean_path("/a/b/?q=1") == "/a/b?q=1"
