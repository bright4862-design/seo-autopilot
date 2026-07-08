from app.review_evidence_contract import normalize_template_family, run_review


def test_failed_page_only_gets_failure_fix_not_phantom_template_fixes():
    result = run_review({
        "website_url": "https://example.com",
        "pages_crawled": 1,
        "pages_found": 1,
        "pages": [
            {
                "url": "https://example.com/old-page",
                "status_code": 404,
                "canonical": "",
                "canonical_url": "",
                "h1_count": 0,
                "meta_description": "",
                "source_pages": ["https://example.com/source"],
                "url_confidence": "linked_but_failed",
            }
        ],
    })
    rules = {fix.get("rule") for fix in result["cleaned_fixes"]}
    assert "broken_page" in rules
    assert "canonical_missing" not in rules
    assert "missing_h1" not in rules
    assert "missing_meta_description" not in rules


def test_grouped_template_fix_carries_source_pages_and_evidence_current_value():
    result = run_review({
        "website_url": "https://shop.example.com",
        "pages_crawled": 3,
        "pages_found": 3,
        "pages": [
            {"url": "https://shop.example.com/collections/a", "status_code": 200, "page_template_family": "category_listing", "canonical": "", "h1_count": 1, "meta_description": "A"},
            {"url": "https://shop.example.com/collections/b", "status_code": 200, "page_template_family": "category_listing", "canonical": "", "h1_count": 1, "meta_description": "B"},
            {"url": "https://shop.example.com/collections/c", "status_code": 200, "page_template_family": "category_listing", "canonical": "", "h1_count": 1, "meta_description": "C"},
        ],
    })
    canonical = next(fix for fix in result["cleaned_fixes"] if fix.get("rule") == "canonical_missing")
    assert canonical["page_template_family"] == "collection_page"
    assert canonical["source_pages"] == ["/collections/a", "/collections/b", "/collections/c"]
    assert canonical["current_value"].startswith("3 affected pages: /collections/a, /collections/b, /collections/c")
    assert canonical["who_can_do_this"] == "your_web_person"


def test_legacy_template_stamps_are_reclassified_by_canonical_classifier():
    assert normalize_template_family("category_listing", "https://shop.example.com/products/widget") == "product_page"
    assert normalize_template_family("guide", "https://fun.example.com/fr/annonce/abc/voir") == "activity_detail"
    assert normalize_template_family("", "https://finance.example.com/loans/dscr") == "loan_program"
    assert normalize_template_family("activity_detail", "https://example.com/anything") == "activity_detail"


def test_every_fix_has_source_pages():
    result = run_review({
        "website_url": "https://shop.example.com",
        "pages_crawled": 1,
        "pages_found": 1,
        "pages": [
            {"url": "https://shop.example.com/products/widget", "status_code": 200, "canonical": "", "h1_count": 1, "meta_description": "Widget"}
        ],
    })
    assert result["cleaned_fixes"]
    assert all(fix.get("source_pages") for fix in result["cleaned_fixes"])
