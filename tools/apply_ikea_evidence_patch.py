from pathlib import Path

review_path = Path("scanner-api/app/review.py")
text = review_path.read_text()

old = '''def build_page_pattern_findings(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
'''
new = '''def image_alt_evidence(page: dict[str, Any]) -> dict[str, Any]:
    """Require material per-page evidence before creating an image-alt task.

    A repeated single missing alt attribute on a page with dozens of images is
    commonly a shared decorative or interface image. It is useful diagnostic
    evidence, but it is not strong enough by itself for a customer-facing fix.
    """
    image_count = int_or_zero(page.get("image_count"))
    missing_alt = int_or_zero(page.get("image_missing_alt_count") or page.get("missing_alt_image_count"))
    ratio = (missing_alt / image_count) if image_count > 0 else 0.0
    material = bool(
        missing_alt > 0
        and image_count > 0
        and (
            missing_alt >= 8
            or (missing_alt >= 3 and ratio >= 0.10)
            or (missing_alt >= 2 and ratio >= 0.20)
            or (missing_alt == 1 and image_count <= 3)
        )
    )
    return {
        "image_count": image_count,
        "missing_alt": missing_alt,
        "missing_alt_ratio": round(ratio, 3),
        "material": material,
    }


def build_page_pattern_findings(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
'''
assert old in text
text = text.replace(old, new, 1)

old = '''        missing_alt = int_or_zero(page.get("image_missing_alt_count") or page.get("missing_alt_image_count"))
        if missing_alt > 0:
            add_bucket(buckets, "image_alt_text", "image_alt_text", family, page, "Batch image descriptions on templates", f"{missing_alt} images missing alt text", "Repeated image-alt gaps are usually a shared template or CMS pattern, especially on listing or detail pages.", "Fix one representative page/template first, then roll out the same rule across the affected group.", "developer" if missing_alt >= 8 else "easy")
'''
new = '''        alt_evidence = image_alt_evidence(page)
        if alt_evidence["material"]:
            missing_alt = alt_evidence["missing_alt"]
            add_bucket(buckets, "image_alt_text", "image_alt_text", family, page, "Batch image descriptions on templates", f"{missing_alt} images missing alt text", "Repeated image-alt gaps are usually a shared template or CMS pattern, especially on listing or detail pages.", "Fix one representative page/template first, then roll out the same rule across the affected group.", "developer" if missing_alt >= 8 else "easy")
'''
assert old in text
text = text.replace(old, new, 1)

old = '''        fixes.append(make_fix(
            rule=bucket["rule"],
            category=bucket["category"],
            priority="critical" if bucket["category"] == "canonical" else "high" if len(bucket["pages"]) >= 8 else "medium",
'''
new = '''        extra_evidence: dict[str, Any] = {}
        current_value = template_current_value(affected)
        priority = "critical" if bucket["category"] == "canonical" else "high" if len(bucket["pages"]) >= 8 else "medium"
        if bucket["rule"] == "image_alt_text":
            alt_stats = [image_alt_evidence(page) for page in bucket["pages"]]
            missing_alt_total = sum(stat["missing_alt"] for stat in alt_stats)
            image_total = sum(stat["image_count"] for stat in alt_stats)
            max_missing_alt = max((stat["missing_alt"] for stat in alt_stats), default=0)
            max_missing_alt_ratio = max((stat["missing_alt_ratio"] for stat in alt_stats), default=0.0)
            aggregate_ratio = round(missing_alt_total / max(1, image_total), 3)
            current_value = (
                f"{len(affected)} materially affected page{'s' if len(affected) != 1 else ''}: "
                f"{missing_alt_total} missing descriptions across {image_total} images "
                f"({round(aggregate_ratio * 100, 1)}%)."
            )
            extra_evidence = {
                "image_alt_evidence_version": "material_image_alt_v1",
                "material_affected_page_count": len(affected),
                "missing_alt_total": missing_alt_total,
                "image_total": image_total,
                "missing_alt_ratio": aggregate_ratio,
                "max_missing_alt_per_page": max_missing_alt,
                "max_missing_alt_ratio_per_page": max_missing_alt_ratio,
            }
            priority = "high" if len(affected) >= 8 or missing_alt_total >= 30 else "medium"
        fixes.append(make_fix(
            rule=bucket["rule"],
            category=bucket["category"],
            priority=priority,
'''
assert old in text
text = text.replace(old, new, 1)

old = '''            extra={
                "current_value": template_current_value(affected),
                "defect_summary": bucket["explanation"],
                "source_pages": dedupe_strings([clean_path(u) for u in affected if clean_path(u)])[:30],
                "page_template_family": bucket["family"],
            },
'''
new = '''            extra={
                "current_value": current_value,
                "defect_summary": bucket["explanation"],
                "source_pages": dedupe_strings([clean_path(u) for u in affected if clean_path(u)])[:30],
                "page_template_family": bucket["family"],
                **extra_evidence,
            },
'''
assert old in text
text = text.replace(old, new, 1)

old = '''def classify_defect_class(fix: dict[str, Any]) -> str:
    text = " ".join(str(fix.get(key, "")) for key in ["rule", "category", "issue_title", "title", "current_value"]).lower()
'''
new = '''def classify_defect_class(fix: dict[str, Any]) -> str:
    text = " ".join(str(fix.get(key, "")) for key in ["rule", "category", "issue_title", "title", "current_value"]).lower()
    if str(fix.get("rule") or "") in {"image_alt_text", "missing_image_alt"} or str(fix.get("category") or "") == "image_alt_text":
        return "metadata"
'''
assert old in text
text = text.replace(old, new, 1)

old = '''    if fix.get("url_confidence") == "crawler_artifact":
        overall = min(overall, 44)
    overall = max(0, min(100, overall))
    priority = "critical" if fix.get("priority") == "critical" or overall >= 82 else "high" if overall >= 68 else "medium" if overall >= 44 else "low"
'''
new = '''    if fix.get("url_confidence") == "crawler_artifact":
        overall = min(overall, 44)
    is_image_alt = str(fix.get("rule") or "") in {"image_alt_text", "missing_image_alt"} or str(fix.get("category") or "") == "image_alt_text"
    if is_image_alt:
        overall = min(overall, 79)
    overall = max(0, min(100, overall))
    priority = "critical" if (not is_image_alt and (fix.get("priority") == "critical" or overall >= 82)) else "high" if overall >= 68 else "medium" if overall >= 44 else "low"
'''
assert old in text
text = text.replace(old, new, 1)

old = '''        "technical_audit_summary": body.get("technical_audit_summary"),
'''
new = '''        "technical_audit_summary": {
            **(body.get("technical_audit_summary") if isinstance(body.get("technical_audit_summary"), dict) else {}),
            "health_score": health_score,
            "score": health_score,
            "scoring_model": SCORING_MODEL,
        },
'''
assert old in text
text = text.replace(old, new, 1)

old = '''        "scan_summary": {
            "health_score": health_score,
            "score": health_score,
            "pages_scanned": site_fingerprint["pages_crawled"],
            "plain_english_summary": summary,
            "site_fingerprint": site_fingerprint,
            "review_input_quality": quality,
            "scan_status": scan_status,
            "review_confidence_state": review_confidence_state,
            "score_is_provisional": score_is_provisional,
            "access_evidence_state": access_evidence_state,
        },
        "scoring_model": SCORING_MODEL,
'''
new = '''        "scan_summary": {
            "health_score": health_score,
            "score": health_score,
            "pages_scanned": site_fingerprint["pages_crawled"],
            "plain_english_summary": summary,
            "site_fingerprint": site_fingerprint,
            "review_input_quality": quality,
            "scan_status": scan_status,
            "review_confidence_state": review_confidence_state,
            "score_is_provisional": score_is_provisional,
            "access_evidence_state": access_evidence_state,
        },
        "site_summary": {
            "health_score": health_score,
            "score": health_score,
            "pages_scanned": site_fingerprint["pages_crawled"],
            "pages_crawled": site_fingerprint["pages_crawled"],
            "pages_found": site_fingerprint["pages_found"],
            "plain_english_summary": summary,
            "scan_status": scan_status,
            "review_confidence_state": review_confidence_state,
            "score_is_provisional": score_is_provisional,
            "access_evidence_state": access_evidence_state,
            "scoring_model": SCORING_MODEL,
        },
        "scoring_model": SCORING_MODEL,
'''
assert old in text
text = text.replace(old, new, 1)

review_path.write_text(text)

Path("scanner-api/tests/test_review_ikea_calibration.py").write_text('''from app.review import run_review\n\n\ndef page(path: str, image_count: int, missing_alt: int, family: str = "product_page") -> dict:\n    return {\n        "url": f"https://www.ikea.com{path}",\n        "final_url": f"https://www.ikea.com{path}/",\n        "path": f"{path}/",\n        "status_code": 200,\n        "title": "Useful page title",\n        "meta_description": "Useful search description",\n        "h1": "Useful heading",\n        "h1_count": 1,\n        "canonical": f"https://www.ikea.com{path}/",\n        "robots": "index, follow",\n        "indexable": True,\n        "word_count": 600,\n        "image_count": image_count,\n        "image_missing_alt_count": missing_alt,\n        "schema_types": ["Product", "BreadcrumbList"],\n        "has_schema": True,\n        "page_template_family": family,\n        "estimated_page_intent": "money_or_conversion",\n    }\n\n\ndef review(pages: list[dict]) -> dict:\n    return run_review({\n        "website_url": "https://www.ikea.com/fr/fr/",\n        "requested_path_prefix": "/fr/fr",\n        "pages_crawled": len(pages),\n        "pages_found": len(pages),\n        "crawled_pages": pages,\n        "technical_audit_summary": {"health_score": 88, "score": 88, "pages_crawled": len(pages), "pages_found": len(pages)},\n        "raw_fixes": [],\n        "grouped_findings": [],\n    })\n\n\ndef test_repeated_single_missing_alt_on_image_heavy_pages_is_suppressed():\n    pages = [page(f"/fr/fr/p/product-{index}", 30, 1) for index in range(20)]\n    result = review(pages)\n    assert not [fix for fix in result["recommendations"] if fix.get("rule") == "image_alt_text"]\n\n\ndef test_material_image_alt_gap_remains_actionable_but_never_critical():\n    result = review([page("/fr/fr/cat/collection-collections", 26, 18, "collection_page")])\n    fixes = [fix for fix in result["recommendations"] if fix.get("rule") == "image_alt_text"]\n    assert len(fixes) == 1\n    fix = fixes[0]\n    assert fix["priority"] in {"medium", "high"}\n    assert fix["priority"] != "critical"\n    assert fix["missing_alt_total"] == 18\n    assert fix["image_total"] == 26\n    assert fix["missing_alt_ratio"] == 0.692\n    assert fix["image_alt_evidence_version"] == "material_image_alt_v1"\n\n\ndef test_final_review_score_is_authoritative_in_every_summary_contract():\n    result = review([page("/fr/fr/cat/collection-collections", 26, 18, "collection_page")])\n    score = result["health_score"]\n    assert score == result["seo_score"]\n    assert score == result["website_health_report"]["health_score"]\n    assert score == result["scan_summary"]["health_score"]\n    assert score == result["site_summary"]["health_score"]\n    assert score == result["technical_audit_summary"]["health_score"]\n    assert result["site_summary"]["score"] == score\n    assert result["technical_audit_summary"]["score"] == score\n''')
