from app.review import compute_health_score, run_review
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


def test_verification_only_findings_stay_low_non_scoring_and_do_not_outrank_confirmed_work():
    body = payload([page("/fr/fr/p/healthy-product", 4, 0)])
    reviewed = run_review(body)
    reviewed["recommendations"] = [
        {
            "id": "orphan",
            "fix_id": "orphan",
            "rule": "potential_orphan_pages",
            "category": "indexability",
            "priority": "critical",
            "overall_priority_score": 94,
            "affected_pages": [f"/fr/item-{index}" for index in range(122)],
            "source_pages": ["/sitemap.xml"],
            "evidence_status": "needs_verification",
            "verification_state": "needs_verification",
            "limitation_code": "sampled_crawl_cannot_prove_orphan",
            "issue_title": "Verify sitemap-only pages are internally linked",
        },
        {
            "id": "canonical",
            "fix_id": "canonical",
            "rule": "canonical_missing",
            "category": "canonical",
            "priority": "high",
            "overall_priority_score": 74,
            "affected_pages": ["/fr/confirmed"],
            "source_pages": ["/fr/confirmed"],
            "issue_title": "Add a canonical URL",
        },
    ]

    result = apply_review_evidence_calibration(reviewed, body)
    orphan = next(fix for fix in result["recommendations"] if fix["rule"] == "potential_orphan_pages")

    assert result["recommendations"][0]["rule"] == "canonical_missing"
    assert orphan["priority"] == "low"
    assert orphan["overall_priority_score"] <= 39
    assert orphan["score_impact"] == 0
    assert orphan["non_scoring"] is True
    assert result["health_score"] == 84
    assert result["next_best_step"] == "Add a canonical URL"


def test_funbooker_narrow_issues_calibrate_to_needs_work_without_score_noise():
    body = payload([page("/fr/fr/p/healthy-product", 4, 0)])
    reviewed = run_review(body)
    reviewed["recommendations"] = [
        {
            "id": "canonical",
            "fix_id": "canonical",
            "rule": "canonical_missing",
            "category": "canonical",
            "priority": "critical",
            "overall_priority_score": 76,
            "affected_pages": ["/fr/page/mentions-legales", "/fr/page/cgu"],
            "page_count": 2,
            "page_scope": "family",
            "page_template_family": "legal_info",
            "issue_title": "Add canonical URLs to legal info pages",
        },
        {
            "id": "redirect",
            "fix_id": "redirect",
            "rule": "sitemap_redirect",
            "category": "indexability",
            "priority": "high",
            "overall_priority_score": 74,
            "affected_pages": ["/fr"],
            "page_count": 1,
            "source_pages": ["/sitemap.xml"],
            "current_value": "https://example.com/fr → https://example.com/fr/ — destination HTTP 200 — destination: Indexable",
            "issue_title": "Replace a redirecting URL in the sitemap",
        },
        {
            "id": "meta",
            "fix_id": "meta",
            "rule": "missing_meta_description",
            "category": "meta_description",
            "priority": "high",
            "overall_priority_score": 69,
            "affected_pages": ["/fr/annonce/example/voir"],
            "page_count": 1,
            "issue_title": "Add a meta description to the affected page",
        },
        {
            "id": "h1",
            "fix_id": "h1",
            "rule": "missing_h1",
            "category": "thin_content",
            "priority": "medium",
            "overall_priority_score": 56,
            "affected_pages": ["/fr/review/page"],
            "page_count": 1,
            "issue_title": "Add an H1 to the affected page",
        },
        {
            "id": "orphan",
            "fix_id": "orphan",
            "rule": "potential_orphan_pages",
            "category": "indexability",
            "priority": "critical",
            "overall_priority_score": 94,
            "affected_pages": [f"/fr/item-{index}" for index in range(121)],
            "evidence_status": "needs_verification",
            "verification_state": "needs_verification",
            "limitation_code": "sampled_crawl_cannot_prove_orphan",
            "issue_title": "Verify sitemap-only pages are internally linked",
        },
    ]
    reviewed["recommendations"].extend(
        [
            {
                "id": "redirect-evidence-card-2",
                "fix_id": "redirect-evidence-card-2",
                "rule": "sitemap_redirect",
                "category": "indexability",
                "priority": "high",
                "overall_priority_score": 70,
                "affected_pages": ["/fr"],
                "page_count": 1,
                "current_value": "https://example.com/fr → https://example.com/fr/ — destination HTTP 200 — destination: Indexable",
                "issue_title": "Review the redirecting sitemap URL evidence",
            },
            {
                "id": "meta-evidence-card-2",
                "fix_id": "meta-evidence-card-2",
                "rule": "missing_meta_description",
                "category": "meta_description",
                "priority": "high",
                "overall_priority_score": 66,
                "affected_pages": ["/fr/annonce/example/voir"],
                "page_count": 1,
                "issue_title": "Review the missing description evidence",
            },
            {
                "id": "h1-evidence-card-2",
                "fix_id": "h1-evidence-card-2",
                "rule": "missing_h1",
                "category": "thin_content",
                "priority": "medium",
                "overall_priority_score": 52,
                "affected_pages": ["/fr/review/page"],
                "page_count": 1,
                "issue_title": "Review the missing H1 evidence",
            },
        ]
    )

    result = apply_review_evidence_calibration(reviewed, body)
    priorities = {fix["rule"]: fix["priority"] for fix in result["recommendations"]}

    assert priorities["canonical_missing"] == "medium"
    assert priorities["sitemap_redirect"] == "medium"
    assert priorities["missing_meta_description"] == "medium"
    assert priorities["missing_h1"] == "medium"
    assert priorities["potential_orphan_pages"] == "low"
    assert result["health_score"] == 76
    assert result["health_grade"] == "Needs work"
    assert result["next_best_step"] == "Add canonical URLs to legal info pages"
    assert result["review_evidence_calibration_version"] == "review_evidence_calibration_v4_legal_page_scope"
    assert len([fix for fix in result["recommendations"] if fix["rule"] == "sitemap_redirect"]) == 2
    assert len([fix for fix in result["recommendations"] if fix["rule"] == "missing_meta_description"]) == 2
    assert len([fix for fix in result["recommendations"] if fix["rule"] == "missing_h1"]) == 2


def test_two_commercial_pages_missing_canonicals_remain_high_priority():
    body = payload([page("/fr/fr/p/healthy-product", 4, 0)])
    reviewed = run_review(body)
    reviewed["recommendations"] = [
        {
            "id": "commercial-canonical",
            "fix_id": "commercial-canonical",
            "rule": "canonical_missing",
            "category": "canonical",
            "priority": "critical",
            "overall_priority_score": 78,
            "affected_pages": ["/fr/annonce/activity-one/voir", "/fr/annonce/activity-two/voir"],
            "page_count": 2,
            "page_scope": "family",
            "page_template_family": "activity_detail",
            "issue_title": "Add canonical URLs to activity pages",
        }
    ]

    result = apply_review_evidence_calibration(reviewed, body)
    fix = result["recommendations"][0]

    assert fix["priority"] == "high"
    assert fix["severity_calibration_reason"] == "narrow_missing_canonical_scope"
    assert result["health_score"] == 84


def test_widespread_canonical_and_unsafe_redirect_evidence_are_not_demoted():
    body = payload([page("/fr/fr/p/healthy-product", 4, 0)])
    reviewed = run_review(body)
    reviewed["recommendations"] = [
        {
            "id": "canonical-sitewide",
            "fix_id": "canonical-sitewide",
            "rule": "canonical_missing",
            "category": "canonical",
            "priority": "critical",
            "overall_priority_score": 95,
            "affected_pages": [f"/product-{index}" for index in range(20)],
            "page_count": 20,
            "page_scope": "sitewide",
            "issue_title": "Fix sitewide missing canonicals",
        },
        {
            "id": "redirect-loop",
            "fix_id": "redirect-loop",
            "rule": "sitemap_redirect",
            "category": "indexability",
            "priority": "critical",
            "overall_priority_score": 92,
            "affected_pages": ["/loop"],
            "page_count": 1,
            "redirect_state": "loop",
            "current_value": "Redirect loop detected before a final destination",
            "issue_title": "Fix a sitemap redirect loop",
        },
    ]

    result = apply_review_evidence_calibration(reviewed, body)
    priorities = {fix["rule"] + fix["id"]: fix["priority"] for fix in result["recommendations"]}

    assert priorities["canonical_missingcanonical-sitewide"] == "critical"
    assert priorities["sitemap_redirectredirect-loop"] == "critical"

def test_health_score_uses_the_strongest_priority_once_per_rule():
    fingerprint = {
        "pages_crawled": 1,
        "pages_found": 1,
        "pages_received": 1,
        "sampled_pages_sent_to_ai": 1,
    }
    fixes = [
        {"id": "h1-medium", "rule": "missing_h1", "priority": "medium"},
        {"id": "h1-high", "rule": "missing_h1", "priority": "high"},
        {"id": "verification", "rule": "potential_orphan_pages", "priority": "critical", "non_scoring": True},
    ]

    assert compute_health_score(fixes, fingerprint) == 84



def test_severe_undercoverage_is_incomplete_and_score_limited():
    from app.review import evidence_is_incomplete
    fingerprint = {"pages_found": 900, "pages_crawled": 7, "pages_received": 7, "sampled_pages_sent_to_ai": 7, "blocked_access_pages": 0, "blocked_or_429_pages": 0}
    assert evidence_is_incomplete(fingerprint) is True
    assert compute_health_score([], fingerprint) == 55


def test_incidental_commerce_keywords_do_not_override_saas_structure():
    body = {"website_url": "https://signal.example", "pages_found": 706, "pages_crawled": 3, "pages": [
        {"url": "https://signal.example/pricing", "status_code": 200, "title": "Pricing", "h1": "Pricing", "meta_description": "Plans", "page_template_family": "standard"},
        {"url": "https://signal.example/features", "status_code": 200, "title": "Features", "h1": "Features", "meta_description": "Product features", "page_template_family": "standard"},
        {"url": "https://signal.example/docs/api", "status_code": 200, "title": "API docs", "h1": "API", "meta_description": "Developer docs with checkout examples", "page_template_family": "guide_article"},
    ]}
    result = run_review(body)
    assert result["site_fingerprint"]["primary_archetype"] == "saas_app_membership"
    assert result["site_fingerprint"]["business_model"] == "saas_or_member_app"
