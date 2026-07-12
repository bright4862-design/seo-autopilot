from app.review import run_review
from app.review_calibration import apply_review_evidence_calibration


def page(path: str, image_count: int, missing_alt: int, family: str = "product_page") -> dict:
    return {
        "url": f"https://www.ikea.com{path}",
        "final_url": f"https://www.ikea.com{path}/",
        "path": f"{path}/",
        "status_code": 200,
        "title": "Useful page title",
        "meta_description": "Useful search description",
        "h1": "Useful heading",
        "h1_count": 1,
        "canonical": f"https://www.ikea.com{path}/",
        "robots": "index, follow",
        "indexable": True,
        "word_count": 600,
        "image_count": image_count,
        "image_missing_alt_count": missing_alt,
        "schema_types": ["Product", "BreadcrumbList"],
        "has_schema": True,
        "page_template_family": family,
        "estimated_page_intent": "money_or_conversion",
    }


def payload(pages: list[dict]) -> dict:
    return {
        "website_url": "https://www.ikea.com/fr/fr/",
        "requested_path_prefix": "/fr/fr",
        "pages_crawled": len(pages),
        "pages_found": len(pages),
        "crawled_pages": pages,
        "technical_audit_summary": {
            "health_score": 88,
            "score": 88,
            "pages_crawled": len(pages),
            "pages_found": len(pages),
        },
        "raw_fixes": [],
        "grouped_findings": [],
    }


def calibrated(pages: list[dict]) -> dict:
    body = payload(pages)
    return apply_review_evidence_calibration(run_review(body), body)


def test_repeated_single_missing_alt_on_image_heavy_pages_is_suppressed():
    pages = [page(f"/fr/fr/p/product-{index}", 30, 1) for index in range(20)]
    result = calibrated(pages)
    assert not [fix for fix in result["recommendations"] if fix.get("rule") == "image_alt_text"]


def test_material_image_alt_gap_remains_actionable_but_never_critical():
    result = calibrated([page("/fr/fr/cat/collection-collections", 26, 18, "collection_page")])
    fixes = [fix for fix in result["recommendations"] if fix.get("rule") == "image_alt_text"]
    assert len(fixes) == 1
    fix = fixes[0]
    assert fix["priority"] in {"medium", "high"}
    assert fix["priority"] != "critical"
    assert fix["missing_alt_total"] == 18
    assert fix["image_total"] == 26
    assert fix["missing_alt_ratio"] == 0.692
    assert fix["image_alt_evidence_version"] == "material_image_alt_v1"


def test_weak_pages_are_removed_from_a_mixed_image_alt_group():
    pages = [
        page("/fr/fr/cat/collection-collections", 26, 18, "collection_page"),
        page("/fr/fr/cat/collection-stockholm", 40, 1, "collection_page"),
    ]
    result = calibrated(pages)
    fix = next(fix for fix in result["recommendations"] if fix.get("rule") == "image_alt_text")
    assert fix["affected_pages"] == ["/fr/fr/cat/collection-collections"]
    assert fix["weak_signal_page_count_suppressed"] == 1


def test_final_review_score_is_authoritative_in_every_summary_contract():
    result = calibrated([page("/fr/fr/cat/collection-collections", 26, 18, "collection_page")])
    score = result["health_score"]
    assert score == result["seo_score"]
    assert score == result["website_health_report"]["health_score"]
    assert score == result["scan_summary"]["health_score"]
    assert score == result["site_summary"]["health_score"]
    assert score == result["technical_audit_summary"]["health_score"]
    assert result["site_summary"]["score"] == score
    assert result["technical_audit_summary"]["score"] == score
