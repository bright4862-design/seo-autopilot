"""Contract specs for PR4 evidence generators.

These are intentionally marked xfail until PR4 implements the generators.
They document the desired product behavior without making the current branch red.
"""

import pytest

from app.review import run_review


@pytest.mark.xfail(reason="PR4 canonical mismatch generator not implemented yet")
def test_canonical_to_other_url_generator_contract():
    result = run_review({
        "website_url": "https://shop.example.com",
        "pages_crawled": 2,
        "pages_found": 2,
        "pages": [
            {
                "url": "https://shop.example.com/products/a",
                "status_code": 200,
                "canonical": "https://shop.example.com/collections/a",
                "canonical_url": "https://shop.example.com/collections/a",
                "h1_count": 1,
                "meta_description": "Product A",
                "indexable": True,
            },
            {
                "url": "https://shop.example.com/products/b",
                "status_code": 200,
                "canonical": "https://shop.example.com/collections/b",
                "canonical_url": "https://shop.example.com/collections/b",
                "h1_count": 1,
                "meta_description": "Product B",
                "indexable": True,
            },
        ],
    })
    fix = next(f for f in result["cleaned_fixes"] if f.get("rule") == "canonical_to_other_url")
    assert fix["category"] == "canonical"
    assert fix["who_can_do_this"] == "your_web_person"
    assert fix["source_pages"] == ["/products/a", "/products/b"]
    assert "/products/a" in fix["current_value"]
    assert "/collections/a" in fix["current_value"]


@pytest.mark.xfail(reason="PR4 canonical other-domain generator not implemented yet")
def test_canonical_to_other_domain_generator_contract():
    result = run_review({
        "website_url": "https://brand.example.com",
        "pages_crawled": 1,
        "pages_found": 1,
        "pages": [
            {
                "url": "https://brand.example.com/services",
                "status_code": 200,
                "canonical": "https://vendor.example.net/services",
                "canonical_url": "https://vendor.example.net/services",
                "h1_count": 1,
                "meta_description": "Services",
                "indexable": True,
            }
        ],
    })
    fix = next(f for f in result["cleaned_fixes"] if f.get("rule") == "canonical_to_other_domain")
    assert fix["priority"] in {"critical", "high"}
    assert fix["who_can_do_this"] == "your_web_person"
    assert fix["source_pages"] == ["/services"]
    assert "vendor.example.net" in fix["current_value"]


@pytest.mark.xfail(reason="PR4 schema generator not implemented yet")
def test_missing_schema_generator_contract_for_money_pages():
    result = run_review({
        "website_url": "https://fun.example.com",
        "pages_crawled": 2,
        "pages_found": 2,
        "pages": [
            {
                "url": "https://fun.example.com/fr/annonce/abc/voir",
                "status_code": 200,
                "canonical": "https://fun.example.com/fr/annonce/abc/voir",
                "h1_count": 1,
                "meta_description": "Activity page",
                "schema_types": [],
                "indexable": True,
            },
            {
                "url": "https://fun.example.com/fr/annonce/def/voir",
                "status_code": 200,
                "canonical": "https://fun.example.com/fr/annonce/def/voir",
                "h1_count": 1,
                "meta_description": "Activity page",
                "schema_types": [],
                "indexable": True,
            },
        ],
    })
    fix = next(f for f in result["cleaned_fixes"] if f.get("rule") in {"missing_schema", "structured_data_missing"})
    assert fix["category"] == "schema"
    assert fix["page_template_family"] == "activity_detail"
    assert fix["who_can_do_this"] == "your_web_person"
    assert len(fix["source_pages"]) == 2


@pytest.mark.xfail(reason="PR4 duplicate route casing generator not implemented yet")
def test_duplicate_route_casing_generator_contract():
    result = run_review({
        "website_url": "https://app.example.com",
        "pages_crawled": 2,
        "pages_found": 2,
        "pages": [
            {"url": "https://app.example.com/dashboard", "status_code": 200, "canonical": "https://app.example.com/dashboard", "h1_count": 1, "meta_description": "Dashboard", "indexable": True},
            {"url": "https://app.example.com/Dashboard", "status_code": 200, "canonical": "https://app.example.com/Dashboard", "h1_count": 1, "meta_description": "Dashboard", "indexable": True},
        ],
    })
    fix = next(f for f in result["cleaned_fixes"] if f.get("rule") == "duplicate_route_casing")
    assert fix["category"] == "canonical"
    assert fix["who_can_do_this"] == "your_web_person"
    assert set(fix["source_pages"]) == {"/dashboard", "/Dashboard"}
    assert "/dashboard" in fix["current_value"]
    assert "/Dashboard" in fix["current_value"]


@pytest.mark.xfail(reason="PR4 money-path blocked generator not implemented yet")
def test_money_path_blocked_generator_contract():
    result = run_review({
        "website_url": "https://lender.example.com",
        "pages_crawled": 2,
        "pages_found": 2,
        "pages": [
            {"url": "https://lender.example.com/apply-now", "status_code": 429, "fetch_error": "rate limited", "source_pages": ["https://lender.example.com/loans/dscr"], "url_confidence": "linked_but_failed"},
            {"url": "https://lender.example.com/request-a-payoff", "status_code": 429, "fetch_error": "rate limited", "source_pages": ["https://lender.example.com/loans/dscr"], "url_confidence": "linked_but_failed"},
        ],
    })
    fix = next(f for f in result["cleaned_fixes"] if f.get("rule") == "money_path_blocked")
    assert fix["priority"] in {"critical", "high"}
    assert fix["primary_defect_class"] == "blocked_access"
    assert fix["who_can_do_this"] == "your_web_person"
    assert set(fix["source_pages"]) == {"/loans/dscr"}
    assert "/apply-now" in fix["current_value"]
    assert "HTTP 429" in fix["current_value"]
