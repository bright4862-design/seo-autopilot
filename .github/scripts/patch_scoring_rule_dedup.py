from pathlib import Path

review_path = Path("scanner-api/app/review.py")
test_path = Path("scanner-api/tests/test_review_calibration.py")

review = review_path.read_text()
old_score = '''def compute_health_score(fixes: list[dict[str, Any]], site_fingerprint: dict[str, Any]) -> int:
    score = 92
    for fix in fixes:
        priority = fix.get("priority")
        if priority == "critical":
            score -= 12
        elif priority == "high":
            score -= 8
        elif priority == "medium":
            score -= 4
        else:
            score -= 1
    if crawl_is_blocked(site_fingerprint):
        return min(score, 45)
    if evidence_is_incomplete(site_fingerprint):
        return min(score, 55)
    if site_fingerprint.get("pages_crawled") == 0:
        score = min(score, 86)
    return max(35, min(98, score))
'''
new_score = '''def _health_score_rule_key(fix: dict[str, Any], index: int) -> str:
    rule = str(fix.get("rule") or "").strip().lower()
    aliases = {
        "missing_canonical": "canonical_missing",
        "missing_image_alt": "image_alt_text",
    }
    if rule:
        return f"rule:{aliases.get(rule, rule)}"

    identity = str(
        fix.get("fix_id")
        or fix.get("id")
        or fix.get("issue_title")
        or fix.get("title")
        or ""
    ).strip().lower()
    category = str(fix.get("category") or "uncategorized").strip().lower()
    return f"card:{category}:{identity or index}"


def compute_health_score(fixes: list[dict[str, Any]], site_fingerprint: dict[str, Any]) -> int:
    penalties = {"critical": 12, "high": 8, "medium": 4, "low": 1}
    strongest_penalty_by_rule: dict[str, int] = {}

    for index, fix in enumerate(fixes):
        if fix.get("non_scoring") is True or fix.get("score_impact") == 0:
            continue
        priority = str(fix.get("priority") or "low").lower()
        penalty = penalties.get(priority, 1)
        key = _health_score_rule_key(fix, index)
        strongest_penalty_by_rule[key] = max(strongest_penalty_by_rule.get(key, 0), penalty)

    score = 92 - sum(strongest_penalty_by_rule.values())
    if crawl_is_blocked(site_fingerprint):
        return min(score, 45)
    if evidence_is_incomplete(site_fingerprint):
        return min(score, 55)
    if site_fingerprint.get("pages_crawled") == 0:
        score = min(score, 86)
    return max(35, min(98, score))
'''
if review.count(old_score) != 1:
    raise SystemExit("compute_health_score block did not match exactly once")
review = review.replace(old_score, new_score)
review_path.write_text(review)

tests = test_path.read_text()
old_import = "from app.review import run_review\n"
new_import = "from app.review import compute_health_score, run_review\n"
if tests.count(old_import) != 1:
    raise SystemExit("review import did not match exactly once")
tests = tests.replace(old_import, new_import)

start = tests.index("def test_funbooker_narrow_issues_calibrate_to_needs_work_without_score_noise():")
end = tests.index("\ndef test_two_commercial_pages_missing_canonicals_remain_high_priority():", start)
segment = tests[start:end]
anchor = '''    ]

    result = apply_review_evidence_calibration(reviewed, body)
'''
duplicates = '''    ]
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
'''
if segment.count(anchor) != 1:
    raise SystemExit("Funbooker calibration anchor did not match exactly once")
segment = segment.replace(anchor, duplicates)
assertions = '''    assert result["review_evidence_calibration_version"] == "review_evidence_calibration_v4_legal_page_scope"
'''
replacement_assertions = '''    assert result["review_evidence_calibration_version"] == "review_evidence_calibration_v4_legal_page_scope"
    assert len([fix for fix in result["recommendations"] if fix["rule"] == "sitemap_redirect"]) == 2
    assert len([fix for fix in result["recommendations"] if fix["rule"] == "missing_meta_description"]) == 2
    assert len([fix for fix in result["recommendations"] if fix["rule"] == "missing_h1"]) == 2
'''
if segment.count(assertions) != 1:
    raise SystemExit("Funbooker assertion anchor did not match exactly once")
segment = segment.replace(assertions, replacement_assertions)
tests = tests[:start] + segment + tests[end:]

extra_test = '''

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
'''
if "def test_health_score_uses_the_strongest_priority_once_per_rule():" in tests:
    raise SystemExit("strongest-priority scoring test already exists")
tests = tests.rstrip() + extra_test + "\n"
test_path.write_text(tests)
