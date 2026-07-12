from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Expected text not found in {path}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


root = Path(__file__).resolve().parents[1]

review_calibration = root / "scanner-api/app/review_calibration.py"
replace_once(
    review_calibration,
    'CALIBRATION_VERSION = "review_evidence_calibration_v1"\nIMAGE_ALT_EVIDENCE_VERSION = "material_image_alt_v1"\nIMAGE_ALT_RULES = {"image_alt_text", "missing_image_alt"}\n',
    'CALIBRATION_VERSION = "review_evidence_calibration_v2_verification_only"\nIMAGE_ALT_EVIDENCE_VERSION = "material_image_alt_v1"\nIMAGE_ALT_RULES = {"image_alt_text", "missing_image_alt"}\nVERIFICATION_ONLY_RULES = {"potential_orphan_pages", "indexable_faceted_navigation"}\nVERIFICATION_ONLY_LIMITATION_CODES = {\n    "sampled_crawl_cannot_prove_orphan",\n    "faceted_navigation_requires_strategy_review",\n}\n',
)
replace_once(
    review_calibration,
    '\n\ndef _health_grade(score: int, scan_status: str) -> str:\n',
    '''\n\ndef _is_verification_only_fix(fix: dict[str, Any]) -> bool:\n    rule = str(fix.get("rule") or "")\n    limitation_code = str(fix.get("limitation_code") or "")\n    return bool(\n        fix.get("non_scoring") is True\n        or rule in VERIFICATION_ONLY_RULES\n        or limitation_code in VERIFICATION_ONLY_LIMITATION_CODES\n    )\n\n\ndef _calibrate_verification_only_fix(fix: dict[str, Any]) -> dict[str, Any]:\n    return {\n        **fix,\n        "priority": "low",\n        "overall_priority_score": min(39, _int(fix.get("overall_priority_score")) or 39),\n        "score_impact": 0,\n        "non_scoring": True,\n        "evidence_status": fix.get("evidence_status") or "needs_verification",\n        "verification_state": fix.get("verification_state") or "needs_verification",\n    }\n\n\ndef _fix_sort_key(fix: dict[str, Any]) -> tuple[int, int]:\n    priority_score = {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(\n        str(fix.get("priority") or ""),\n        0,\n    )\n    return (priority_score, _int(fix.get("overall_priority_score")))\n\n\ndef _health_grade(score: int, scan_status: str) -> str:\n''',
)
replace_once(
    review_calibration,
    '''        if rule in IMAGE_ALT_RULES or str(item.get("category") or "") == "image_alt_text":\n            item = _calibrate_image_alt_fix(item, evidence)\n            if item is None:\n                continue\n        fixes.append(item)\n\n    fingerprint = calibrated_result.get("site_fingerprint")\n''',
    '''        if rule in IMAGE_ALT_RULES or str(item.get("category") or "") == "image_alt_text":\n            item = _calibrate_image_alt_fix(item, evidence)\n            if item is None:\n                continue\n        if _is_verification_only_fix(item):\n            item = _calibrate_verification_only_fix(item)\n        fixes.append(item)\n\n    fixes = sorted(fixes, key=_fix_sort_key, reverse=True)\n    scoring_fixes = [item for item in fixes if not _is_verification_only_fix(item)]\n\n    fingerprint = calibrated_result.get("site_fingerprint")\n''',
)
replace_once(
    review_calibration,
    '    score = compute_health_score(fixes, fingerprint) if fingerprint else _int(calibrated_result.get("health_score"))\n',
    '    score = compute_health_score(scoring_fixes, fingerprint) if fingerprint else _int(calibrated_result.get("health_score"))\n',
)

review_tests = root / "scanner-api/tests/test_review_calibration.py"
review_tests.write_text(
    review_tests.read_text(encoding="utf-8")
    + '''\n\ndef test_verification_only_findings_stay_low_non_scoring_and_do_not_outrank_confirmed_work():\n    body = payload([page("/fr/fr/p/healthy-product", 4, 0)])\n    reviewed = run_review(body)\n    reviewed["recommendations"] = [\n        {\n            "id": "orphan",\n            "fix_id": "orphan",\n            "rule": "potential_orphan_pages",\n            "category": "indexability",\n            "priority": "critical",\n            "overall_priority_score": 94,\n            "affected_pages": [f"/fr/item-{index}" for index in range(122)],\n            "source_pages": ["/sitemap.xml"],\n            "evidence_status": "needs_verification",\n            "verification_state": "needs_verification",\n            "limitation_code": "sampled_crawl_cannot_prove_orphan",\n            "issue_title": "Verify sitemap-only pages are internally linked",\n        },\n        {\n            "id": "canonical",\n            "fix_id": "canonical",\n            "rule": "canonical_missing",\n            "category": "canonical",\n            "priority": "high",\n            "overall_priority_score": 74,\n            "affected_pages": ["/fr/confirmed"],\n            "source_pages": ["/fr/confirmed"],\n            "issue_title": "Add a canonical URL",\n        },\n    ]\n\n    result = apply_review_evidence_calibration(reviewed, body)\n    orphan = next(fix for fix in result["recommendations"] if fix["rule"] == "potential_orphan_pages")\n\n    assert result["recommendations"][0]["rule"] == "canonical_missing"\n    assert orphan["priority"] == "low"\n    assert orphan["overall_priority_score"] <= 39\n    assert orphan["score_impact"] == 0\n    assert orphan["non_scoring"] is True\n    assert result["health_score"] == 84\n    assert result["next_best_step"] == "Add a canonical URL"\n''',
    encoding="utf-8",
)

redirect_validation = root / "scanner-api/app/redirect_validation.py"
replace_once(
    redirect_validation,
    'REDIRECT_EVIDENCE_VERSION = "redirect_evidence_v1"\n',
    'REDIRECT_EVIDENCE_VERSION = "redirect_evidence_v2_trailing_slash_identity"\n',
)
replace_once(
    redirect_validation,
    '''    path = parsed.path or "/"\n    if path != "/":\n        path = path.rstrip("/")\n    return parsed._replace(\n''',
    '''    path = parsed.path or "/"\n    return parsed._replace(\n''',
)

redirect_tests = root / "scanner-api/tests/test_redirect_evidence.py"
replace_once(
    redirect_tests,
    '''\n\n@pytest.mark.asyncio\nasync def test_redirect_chain_and_loop_are_explicit(monkeypatch):\n''',
    '''\n\n@pytest.mark.asyncio\nasync def test_trailing_slash_redirect_is_not_mislabeled_as_a_loop(monkeypatch):\n    monkeypatch.setattr("app.redirect_validation.is_public_http_url", lambda _url: True)\n    client = FakeClient({\n        "https://example.com/fr": _response("https://example.com/fr", 301, location="/fr/"),\n        "https://example.com/fr/": _response("https://example.com/fr/", 200),\n    })\n    policy = RobotsPolicy("https://example.com/robots.txt", "missing", 404)\n\n    page = await fetch_and_extract(client, "https://example.com/fr", DISCOVERY_SITEMAP, robots_policy=policy)\n\n    assert client.calls == ["https://example.com/fr", "https://example.com/fr/"]\n    assert page["redirect_state"] == "single_redirect"\n    assert page["redirect_chain"] == ["https://example.com/fr", "https://example.com/fr/"]\n    assert page["redirect_destination_url"] == "https://example.com/fr/"\n\n\n@pytest.mark.asyncio\nasync def test_redirect_chain_and_loop_are_explicit(monkeypatch):\n''',
)

print("Applied Funbooker accuracy regression patch")
