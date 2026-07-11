from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Anchor not found in {path}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


review_contract = ROOT / "src/lib/reviewContract.js"
text = review_contract.read_text(encoding="utf-8")
if "export function normalizeActionPriority" not in text:
    text += """

export function normalizeActionPriority(value) {
  const priority = String(value || "").toLowerCase();
  return ["critical", "high", "medium", "low"].includes(priority) ? priority : "medium";
}
"""
    review_contract.write_text(text, encoding="utf-8")

scan_form = ROOT / "src/components/scan/ScanWebsiteForm.jsx"
replace_once(
    scan_form,
    'import { selectFinalReviewFixes } from "@/lib/reviewContract";',
    'import { normalizeActionPriority, selectFinalReviewFixes } from "@/lib/reviewContract";',
)
replace_once(
    scan_form,
    'function normalizeActionPriority(value) { const priority = normalizePriority(value); return priority === "critical" ? "high" : priority; }\n',
    "",
)

review_py = ROOT / "scanner-api/app/review.py"
replace_once(
    review_py,
    "\n\ndef build_review_payload(body: dict[str, Any], pages: list[dict[str, Any]], fixes: list[dict[str, Any]], site_fingerprint: dict[str, Any], playbook: dict[str, Any], website_url: str) -> dict[str, Any]:\n",
    """

RATE_LIMIT_RULES = {"rate_limited_page", "blocked_page"}


def has_rate_limit_evidence(fixes: list[dict[str, Any]]) -> bool:
    return any(
        str(fix.get("rule") or "") in RATE_LIMIT_RULES
        or str(fix.get("source") or "").startswith("scanner_verified_failed_pages:429")
        for fix in fixes
    )


def build_review_payload(body: dict[str, Any], pages: list[dict[str, Any]], fixes: list[dict[str, Any]], site_fingerprint: dict[str, Any], playbook: dict[str, Any], website_url: str) -> dict[str, Any]:
""",
)
replace_once(
    review_py,
    '    bigger_projects = [fix.get("issue_title") or fix.get("title") for fix in fixes if fix.get("difficulty") == "developer" or fix.get("requires_developer")][:3]\n    report = {\n',
    '''    bigger_projects = [fix.get("issue_title") or fix.get("title") for fix in fixes if fix.get("difficulty") == "developer" or fix.get("requires_developer")][:3]\n    limitations = [\n        "This scan is read-only and cannot confirm private analytics, paid search data, conversions, or server logs."\n    ]\n    if has_rate_limit_evidence(fixes):\n        limitations.append(\n            "HTTP 429 and connection-verification results need access-log confirmation before being treated as confirmed broken customer pages."\n        )\n    report = {\n''',
)
replace_once(
    review_py,
    '''        "limitations": [\n            "This scan is read-only and cannot confirm private analytics, paid search data, conversions, or server logs.",\n            "HTTP 429 and connection-verification results need access-log confirmation before being treated as confirmed broken customer pages.",\n        ],\n''',
    '        "limitations": limitations,\n',
)

frontend_test = ROOT / "tests/frontend/review_contract.test.mjs"
frontend_test.parent.mkdir(parents=True, exist_ok=True)
frontend_test.write_text(
    '''import test from "node:test";\nimport assert from "node:assert/strict";\n\nimport { getPriorityLabel } from "../../src/lib/friendlyLabels.js";\nimport { normalizeActionPriority } from "../../src/lib/reviewContract.js";\n\ntest("compact actions preserve critical priority", () => {\n  assert.equal(normalizeActionPriority("critical"), "critical");\n  assert.equal(normalizeActionPriority("high"), "high");\n  assert.equal(normalizeActionPriority("medium"), "medium");\n  assert.equal(normalizeActionPriority("low"), "low");\n});\n\ntest("unknown compact action priorities fall back safely", () => {\n  assert.equal(normalizeActionPriority("urgent"), "medium");\n  assert.equal(normalizeActionPriority(""), "medium");\n});\n\ntest("the customer-facing label contract accepts critical", () => {\n  assert.equal(getPriorityLabel("critical"), "High impact");\n  assert.equal(getPriorityLabel("high"), "High impact");\n});\n''',
    encoding="utf-8",
)

presentation_test = ROOT / "scanner-api/tests/test_review_presentation_contract.py"
text = presentation_test.read_text(encoding="utf-8")
addition = '''\n\ndef test_clean_review_does_not_emit_rate_limit_caveat():\n    result = _run([_page("/clean")])\n    limitations = result["website_health_report"]["limitations"]\n\n    assert len(limitations) == 1\n    assert not any("HTTP 429" in limitation for limitation in limitations)\n\n\ndef test_rate_limit_card_and_caveat_are_emitted_together():\n    result = _run([_page("/blocked", status_code=429)])\n    limitations = result["website_health_report"]["limitations"]\n\n    assert _fix(result, "rate_limited_page")\n    assert any("HTTP 429" in limitation for limitation in limitations)\n\n\ndef test_server_error_card_does_not_trigger_rate_limit_caveat():\n    result = _run([_page("/server-error", status_code=503)])\n    limitations = result["website_health_report"]["limitations"]\n\n    assert _fix(result, "server_error")\n    assert not any("HTTP 429" in limitation for limitation in limitations)\n'''
if "test_clean_review_does_not_emit_rate_limit_caveat" not in text:
    presentation_test.write_text(text.rstrip() + addition + "\n", encoding="utf-8")

package_json = ROOT / "package.json"
package = json.loads(package_json.read_text(encoding="utf-8"))
package.setdefault("scripts", {})["test:frontend"] = "node --test tests/frontend/*.test.mjs"
package_json.write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")
