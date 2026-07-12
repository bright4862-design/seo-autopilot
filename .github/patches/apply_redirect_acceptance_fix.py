from pathlib import Path

acceptance_path = Path("scanner-api/app/crawler_acceptance.py")
acceptance = acceptance_path.read_text(encoding="utf-8")
old = '            or bool(page.get("redirect_state"))\n'
new = '            or _str(page.get("redirect_state")) not in {"", "not_redirected"}\n'
if old not in acceptance:
    if new not in acceptance:
        raise SystemExit("redirect acceptance condition was not found")
else:
    if acceptance.count(old) != 1:
        raise SystemExit("redirect acceptance condition was not unique")
    acceptance = acceptance.replace(old, new, 1)
    acceptance_path.write_text(acceptance, encoding="utf-8")

test_path = Path("scanner-api/tests/test_crawler_acceptance.py")
tests = test_path.read_text(encoding="utf-8")
marker = "def test_not_redirected_state_is_not_a_redirect_source():"
if marker not in tests:
    tests += '''\n\n\ndef test_not_redirected_state_is_not_a_redirect_source():\n    scan = _scan()\n    scan["crawled_pages"][0]["redirect_state"] = "not_redirected"\n\n    validation = validate_crawler_contract(scan, _review())\n\n    assert validation["passed"] is True\n    assert "redirect_marked_indexable" not in validation["error_codes"]\n\n\ndef test_actual_redirect_state_cannot_remain_indexable_after_final_200():\n    scan = _scan()\n    page = scan["crawled_pages"][0]\n    page.update({\n        "status_code": 200,\n        "redirect_state": "single_redirect",\n        "redirect_hop_count": 1,\n        "indexability_state": "Redirected",\n        "indexable": True,\n    })\n\n    validation = validate_crawler_contract(scan, _review())\n\n    assert validation["passed"] is False\n    assert "redirect_marked_indexable" in validation["error_codes"]\n'''
    test_path.write_text(tests, encoding="utf-8")

trigger_path = Path("data/final-crawler-validation-trigger")
trigger_path.write_text(
    "final-crawler-validation-v3\n"
    "requested_at=2026-07-12T17:10:00+02:00\n"
    "reason=rerun after correcting not_redirected acceptance classification\n",
    encoding="utf-8",
)
