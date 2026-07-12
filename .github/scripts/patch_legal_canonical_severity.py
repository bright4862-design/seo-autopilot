from pathlib import Path

CALIBRATION = Path("scanner-api/app/review_calibration.py")
TESTS = Path("scanner-api/tests/test_review_calibration.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


calibration = CALIBRATION.read_text(encoding="utf-8")
calibration = replace_once(
    calibration,
    'CALIBRATION_VERSION = "review_evidence_calibration_v3_narrow_scope_severity"',
    'CALIBRATION_VERSION = "review_evidence_calibration_v4_legal_page_scope"',
    "calibration version",
)
calibration = replace_once(
    calibration,
    'PRIORITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}\n',
    'PRIORITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}\n'
    'LEGAL_TEMPLATE_FAMILIES = {"legal_info", "legal", "terms", "privacy"}\n'
    'LEGAL_PATH_MARKERS = (\n'
    '    "/mentions-legales",\n'
    '    "/mentions_legales",\n'
    '    "/cgu",\n'
    '    "/cgv",\n'
    '    "/conditions-generales",\n'
    '    "/conditions_generales",\n'
    '    "/legal",\n'
    '    "/terms",\n'
    '    "/privacy",\n'
    '    "/politique-de-confidentialite",\n'
    ')\n',
    "legal constants",
)
helper = '''def _is_legal_page_path(value: Any) -> bool:\n    path = _path(value).lower()\n    return bool(path and any(marker in path for marker in LEGAL_PATH_MARKERS))\n\n\ndef _is_narrow_legal_canonical_fix(fix: dict[str, Any]) -> bool:\n    if str(fix.get("rule") or "") not in CANONICAL_MISSING_RULES:\n        return False\n    if _affected_page_count(fix) > 5:\n        return False\n    if str(fix.get("page_scope") or "").lower() == "sitewide":\n        return False\n\n    family = str(fix.get("page_template_family") or fix.get("page_type") or "").lower()\n    if family in LEGAL_TEMPLATE_FAMILIES:\n        return True\n\n    affected = fix.get("affected_pages") if isinstance(fix.get("affected_pages"), list) else []\n    if not affected and fix.get("page_url"):\n        affected = [fix.get("page_url")]\n    return bool(affected and all(_is_legal_page_path(value) for value in affected))\n\n\n'''
calibration = replace_once(
    calibration,
    'def _calibrate_scope_sensitive_fix(fix: dict[str, Any]) -> dict[str, Any]:\n',
    helper + 'def _calibrate_scope_sensitive_fix(fix: dict[str, Any]) -> dict[str, Any]:\n',
    "legal helper insertion",
)
calibration = replace_once(
    calibration,
    '''    if rule in CANONICAL_MISSING_RULES and affected_count <= 2 and page_scope != "sitewide":\n        return _cap_priority(\n            fix,\n            "high",\n            81,\n            "narrow_missing_canonical_scope",\n        )\n''',
    '''    if _is_narrow_legal_canonical_fix(fix):\n        return _cap_priority(\n            fix,\n            "medium",\n            67,\n            "legal_page_missing_canonical_scope",\n        )\n\n    if rule in CANONICAL_MISSING_RULES and affected_count <= 2 and page_scope != "sitewide":\n        return _cap_priority(\n            fix,\n            "high",\n            81,\n            "narrow_missing_canonical_scope",\n        )\n''',
    "legal canonical calibration",
)
CALIBRATION.write_text(calibration, encoding="utf-8")


tests = TESTS.read_text(encoding="utf-8")
tests = replace_once(
    tests,
    '    assert priorities["canonical_missing"] == "high"\n',
    '    assert priorities["canonical_missing"] == "medium"\n',
    "Funbooker canonical expectation",
)
tests = replace_once(
    tests,
    '    assert result["health_score"] == 72\n',
    '    assert result["health_score"] == 76\n',
    "Funbooker score expectation",
)
tests = replace_once(
    tests,
    '    assert result["review_evidence_calibration_version"] == "review_evidence_calibration_v3_narrow_scope_severity"\n',
    '    assert result["review_evidence_calibration_version"] == "review_evidence_calibration_v4_legal_page_scope"\n',
    "calibration version expectation",
)
new_test = '''def test_two_commercial_pages_missing_canonicals_remain_high_priority():\n    body = payload([page("/fr/fr/p/healthy-product", 4, 0)])\n    reviewed = run_review(body)\n    reviewed["recommendations"] = [\n        {\n            "id": "commercial-canonical",\n            "fix_id": "commercial-canonical",\n            "rule": "canonical_missing",\n            "category": "canonical",\n            "priority": "critical",\n            "overall_priority_score": 78,\n            "affected_pages": ["/fr/annonce/activity-one/voir", "/fr/annonce/activity-two/voir"],\n            "page_count": 2,\n            "page_scope": "family",\n            "page_template_family": "activity_detail",\n            "issue_title": "Add canonical URLs to activity pages",\n        }\n    ]\n\n    result = apply_review_evidence_calibration(reviewed, body)\n    fix = result["recommendations"][0]\n\n    assert fix["priority"] == "high"\n    assert fix["severity_calibration_reason"] == "narrow_missing_canonical_scope"\n    assert result["health_score"] == 84\n\n\n'''
tests = replace_once(
    tests,
    'def test_widespread_canonical_and_unsafe_redirect_evidence_are_not_demoted():\n',
    new_test + 'def test_widespread_canonical_and_unsafe_redirect_evidence_are_not_demoted():\n',
    "commercial canonical regression",
)
TESTS.write_text(tests, encoding="utf-8")
