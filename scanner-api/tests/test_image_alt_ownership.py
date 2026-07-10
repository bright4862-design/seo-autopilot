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


def test_grouped_page_pattern_image_alt_fix_is_developer_owned():
    fix = _image_alt_fix(_run([_page("/contact"), _page("/contact-sales")]))

    assert fix["source"].startswith("page_pattern:image_alt_text:")
    assert len(fix["affected_pages"]) == 2
    assert fix["who_can_do_this"] == "your_web_person"
    assert fix["difficulty"] == "developer"
    assert fix["requires_developer"] is True


def test_single_page_image_alt_fix_stays_user_owned():
    fix = _image_alt_fix(_run([_page("/contact")]))

    assert len(fix["affected_pages"]) == 1
    assert fix["who_can_do_this"] == "you"
    assert fix["difficulty"] == "easy"
    assert fix["requires_developer"] is False
