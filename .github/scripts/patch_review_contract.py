from __future__ import annotations

from pathlib import Path
import re

ROOT = Path.cwd()


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Missing patch anchor: {label}")
    return text.replace(old, new, 1)


frontend_path = "src/components/scan/ScanWebsiteForm.jsx"
frontend = read(frontend_path)
import_anchor = 'import { base44 } from "@/api/base44Client";\n'
contract_import = 'import { selectFinalReviewFixes } from "@/lib/reviewContract";\n'
if contract_import not in frontend:
    frontend = replace_once(frontend, import_anchor, import_anchor + contract_import, "frontend review contract import")

old_final = '  const finalFixes = groupAndSortFixes((aiFixes.length > 0 ? aiFixes : scannerFixes).map(slimFix), { requestedPathPrefix }).slice(0, 120);'
new_final = '''  const finalFixes = selectFinalReviewFixes({
    aiData,
    aiFixes,
    scannerFixes,
    slimFix,
    groupAndSortFixes,
    requestedPathPrefix,
  });'''
if old_final in frontend:
    frontend = frontend.replace(old_final, new_final, 1)
elif "selectFinalReviewFixes({" not in frontend:
    raise RuntimeError("Missing frontend final-fix selection anchor")
write(frontend_path, frontend)

write(
    "src/lib/reviewContract.js",
    '''export function hasAuthoritativePythonReview(aiData = {}) {
  return (
    aiData?.ai_review_backend === "python_review_api" &&
    aiData?.python_review_fallback_used !== true
  );
}

export function selectFinalReviewFixes({
  aiData = {},
  aiFixes = [],
  scannerFixes = [],
  slimFix = (fix) => fix,
  groupAndSortFixes,
  requestedPathPrefix = "",
} = {}) {
  const reviewed = Array.isArray(aiFixes) ? aiFixes : [];
  const scanner = Array.isArray(scannerFixes) ? scannerFixes : [];

  // Python Review already grouped, deduplicated, prioritized, titled, and assigned ownership.
  // Preserve that contract, including an authoritative empty result.
  if (hasAuthoritativePythonReview(aiData)) {
    return reviewed.map(slimFix).slice(0, 120);
  }

  // Legacy and fallback records still need the frontend compatibility layer.
  const source = reviewed.length > 0 ? reviewed : scanner;
  const normalized = source.map(slimFix);
  if (typeof groupAndSortFixes !== "function") return normalized.slice(0, 120);
  return groupAndSortFixes(normalized, { requestedPathPrefix }).slice(0, 120);
}
''',
)

write(
    "tests/frontend/reviewContract.test.mjs",
    '''import assert from "node:assert/strict";
import test from "node:test";

import {
  hasAuthoritativePythonReview,
  selectFinalReviewFixes,
} from "../../src/lib/reviewContract.js";

const slimFix = (fix) => ({ ...fix, normalized: true });

function groupingSpy() {
  const calls = [];
  const group = (fixes, options) => {
    calls.push({ fixes, options });
    return fixes.map((fix) => ({ ...fix, title: `rewritten: ${fix.title}` }));
  };
  return { calls, group };
}

test("successful Python Review bypasses frontend regrouping and preserves copy", () => {
  const spy = groupingSpy();
  const fixes = selectFinalReviewFixes({
    aiData: { ai_review_backend: "python_review_api", python_review_fallback_used: false },
    aiFixes: [{ title: "Add canonical URLs to legal info pages", is_low_value_page: false }],
    scannerFixes: [{ title: "scanner fallback" }],
    slimFix,
    groupAndSortFixes: spy.group,
  });

  assert.equal(hasAuthoritativePythonReview({ ai_review_backend: "python_review_api" }), true);
  assert.equal(spy.calls.length, 0);
  assert.equal(fixes[0].title, "Add canonical URLs to legal info pages");
  assert.equal(fixes[0].is_low_value_page, false);
});

test("authoritative empty Python Review does not resurrect scanner findings", () => {
  const spy = groupingSpy();
  const fixes = selectFinalReviewFixes({
    aiData: { ai_review_backend: "python_review_api", python_review_fallback_used: false },
    aiFixes: [],
    scannerFixes: [{ title: "stale scanner finding" }],
    slimFix,
    groupAndSortFixes: spy.group,
  });

  assert.deepEqual(fixes, []);
  assert.equal(spy.calls.length, 0);
});

test("fallback and legacy results retain compatibility grouping", () => {
  const fallbackSpy = groupingSpy();
  const fallback = selectFinalReviewFixes({
    aiData: { ai_review_backend: "python_review_api", python_review_fallback_used: true },
    aiFixes: [{ title: "fallback finding" }],
    slimFix,
    groupAndSortFixes: fallbackSpy.group,
    requestedPathPrefix: "/fr",
  });
  assert.equal(fallbackSpy.calls.length, 1);
  assert.equal(fallbackSpy.calls[0].options.requestedPathPrefix, "/fr");
  assert.match(fallback[0].title, /^rewritten:/);

  const legacySpy = groupingSpy();
  const legacy = selectFinalReviewFixes({
    aiData: {},
    aiFixes: [],
    scannerFixes: [{ title: "scanner finding" }],
    slimFix,
    groupAndSortFixes: legacySpy.group,
  });
  assert.equal(legacySpy.calls.length, 1);
  assert.match(legacy[0].title, /^rewritten:/);
});
''',
)

review_path = "scanner-api/app/review.py"
review = read(review_path)

if "def page_pattern_title(" not in review:
    marker = "\ndef build_page_pattern_findings(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:\n"
    helper = '''
def page_pattern_title(rule: str, family: str, is_group: bool) -> str:
    label = family_label(family)
    if rule == "canonical_missing":
        return f"Add canonical URLs to {label} pages" if is_group else "Add a canonical URL to the affected page"
    if rule == "image_alt_text":
        return f"Add missing image descriptions to {label} pages" if is_group else "Add missing image descriptions to the affected page"
    if rule == "missing_meta_description":
        return f"Add meta descriptions to {label} pages" if is_group else "Add a meta description to the affected page"
    if rule == "missing_h1":
        return f"Add H1 headings to {label} pages" if is_group else "Add an H1 to the affected page"
    if rule == "multiple_h1":
        return f"Use one main heading on {label} pages" if is_group else "Use one main heading on the affected page"
    return f"Fix the repeated {label} page issue" if is_group else "Fix the affected page issue"


'''
    review = replace_once(review, marker, "\n" + helper + marker.lstrip("\n"), "page-pattern title helper")

old_title = '        title = bucket["title"].replace("templates", f"{family_label(bucket[\'family\'])} templates") if is_group else bucket["title"].replace("templates", "the affected page")'
new_title = '        title = page_pattern_title(bucket["rule"], bucket["family"], is_group)'
if old_title in review:
    review = review.replace(old_title, new_title, 1)
elif new_title not in review:
    raise RuntimeError("Missing backend page-pattern title anchor")

if "def is_cross_cutting_evidence(" not in review:
    score_marker = "\ndef score_fix(fix: dict[str, Any], site_fingerprint: dict[str, Any], body: dict[str, Any], playbook: dict[str, Any]) -> dict[str, Any]:\n"
    cross_helper = '''
def is_cross_cutting_evidence(fix: dict[str, Any]) -> bool:
    """HTTP/crawler-access evidence groups by failure mode, not page template."""
    source = str(fix.get("source", ""))
    rule = str(fix.get("rule", ""))
    if source.startswith("scanner_verified_failed_pages:"):
        return True
    return rule in {"rate_limited_page", "broken_page", "server_error", "blocked_page"}


'''
    review = replace_once(review, score_marker, "\n" + cross_helper + score_marker.lstrip("\n"), "cross-cutting evidence helper")

strong_family = '        "page_template_family": "mixed" if is_cross_cutting_evidence(fix) else fix.get("page_template_family") or get_template_family(page_url),'
family_variants = [
    '        "page_template_family": fix.get("page_template_family") or get_template_family(page_url),',
    '        "page_template_family": fix.get("page_template_family") or ("mixed" if is_cross_cutting_evidence(fix) else get_template_family(page_url)),',
]
if strong_family not in review:
    for variant in family_variants:
        if variant in review:
            review = review.replace(variant, strong_family, 1)
            break
    else:
        raise RuntimeError("Missing backend page_template_family scoring anchor")

new_default_steps = '''def default_steps(category: str, rule: str, difficulty: str, recommended_value: str) -> list[str]:
    text = f"{category} {rule}"

    if category == "image_alt_text" or re.search(r"image_alt|missing_alt|alt_text", rule, re.I):
        return [
            "Open one affected page and identify which meaningful images are missing alt text.",
            "Update the shared image component or CMS image field to output short, specific alt text.",
            "Check several affected pages to confirm decorative images remain empty and meaningful images are described.",
            "Publish the change and run FixList again to confirm the missing-alt count has fallen.",
        ]
    if re.search(r"canonical_missing|missing_canonical|canonical_to_other", rule, re.I) or category == "canonical":
        return [
            "Send the affected URLs to your web person.",
            "Add or correct self-referencing canonical tags on the affected page or shared template.",
            "Publish the change and inspect the rendered page source to confirm the canonical URL is correct.",
            "Run FixList again to confirm the canonical issue is resolved.",
        ]
    if re.search(r"missing_h1", rule, re.I):
        return [
            "Open the affected page or shared template.",
            "Add one clear H1 that describes the page's main topic.",
            "Keep supporting section headings as H2 or H3 headings.",
            "Publish the change and run FixList again.",
        ]
    if re.search(r"multiple_h1", rule, re.I):
        return [
            "Open the affected page or shared template.",
            "Keep the primary page heading as the only H1.",
            "Change supporting headings to H2 or H3 without altering their visual style.",
            "Publish the change and run FixList again.",
        ]
    if re.search(r"missing_meta_description", rule, re.I) or category == "meta_description":
        return [
            "Open the affected page in the CMS or page template.",
            "Add a concise meta description that accurately explains the page and gives searchers a reason to click.",
            "Keep the description unique to the page and avoid copying visible boilerplate or HTML markup.",
            "Publish the update and run FixList again.",
        ]
    if re.search(r"429|blocked|rate_limited", rule, re.I):
        return [
            "Send the grouped affected URLs to your web person.",
            "Check CDN, firewall, server, and bot-protection logs for HTTP 429 or verification responses.",
            "Confirm whether Googlebot and normal users can load the pages.",
            "Adjust rate-limit or bot-protection rules only if legitimate crawlers or users are blocked.",
            "Run FixList again to confirm the affected pages load.",
        ]
    if re.search(r"404|410|broken", text, re.I):
        return [
            "Send the affected URLs and source-page evidence to your web person.",
            "Decide whether each URL should be restored, redirected, or removed from internal links.",
            "Update the source links or add 301 redirects to the closest relevant live page.",
            "Run FixList again to confirm the URLs no longer fail.",
        ]
    if re.search(r"server_error|5xx|500|502|503|504", text, re.I):
        return [
            "Send the affected URLs and timestamps to your web person.",
            "Check application, hosting, and reverse-proxy logs for the server error.",
            "Fix the failing route, dependency, timeout, or infrastructure rule.",
            "Recheck the URLs directly, then run FixList again.",
        ]
    if difficulty == "developer" or re.search(r"redirect|route_boundary|indexability|template|schema|javascript|render", text, re.I):
        return [
            "Send this recommendation to your web person.",
            clean_str(recommended_value) or "Apply the recommended technical change.",
            "Publish the change and rerun FixList to verify it.",
        ]
    return [
        "Open the affected page or template.",
        clean_str(recommended_value) or "Apply the recommended change.",
        "Publish the update and run FixList again.",
    ]
'''
pattern = re.compile(
    r"def default_steps\(category: str, rule: str, difficulty: str, recommended_value: str\) -> list\[str\]:\n.*?\n\ndef needs_developer_owner",
    re.S,
)
match = pattern.search(review)
if not match:
    raise RuntimeError("Missing default_steps function")
review = review[: match.start()] + new_default_steps + "\n\ndef needs_developer_owner" + review[match.end() :]
write(review_path, review)

write(
    "scanner-api/tests/test_review_presentation_contract.py",
    '''"""Presentation-contract regressions for Python Review and frontend handoff."""

from app.review import run_review


def _run(pages):
    return run_review({
        "website_url": "https://example.com",
        "pages": pages,
        "scan_coverage": {
            "pages_found": max(10, len(pages)),
            "pages_crawled": len(pages),
            "sampled_pages_sent_to_ai": len(pages),
        },
    })


def _page(path, family="standard", **extra):
    return {
        "final_url": f"https://example.com{path}",
        "status_code": 200,
        "h1_count": 1,
        "meta_description": "Useful description",
        "canonical": f"https://example.com{path}",
        "page_template_family": family,
        **extra,
    }


def _fix(result, rule):
    return next(fix for fix in result["cleaned_fixes"] if fix.get("rule") == rule)


def test_activity_image_alt_card_has_specific_title_and_steps():
    pages = [
        _page(f"/fr/annonce/activity-{index}/voir", "activity_detail", image_missing_alt_count=2)
        for index in range(3)
    ]
    card = _fix(_run(pages), "image_alt_text")
    steps = " ".join(card["what_to_do_steps"]).lower()

    assert card["title"] == "Add missing image descriptions to activity/detail pages"
    assert "alt text" in steps
    assert "shared image component" in steps
    assert "routing" not in steps
    assert "canonical, schema" not in steps


def test_legal_canonical_card_has_specific_title_and_steps():
    pages = [
        _page("/fr/page/cgu", "legal_info", canonical=""),
        _page("/fr/page/mentions-legales", "legal_info", canonical=""),
    ]
    card = _fix(_run(pages), "canonical_missing")
    steps = " ".join(card["what_to_do_steps"]).lower()

    assert card["title"] == "Add canonical URLs to legal info pages"
    assert "self-referencing canonical" in steps
    assert "rendered page source" in steps
    assert "schema, indexability" not in steps


def test_single_missing_meta_description_has_singular_copy():
    card = _fix(
        _run([_page("/fr/annonce/activity/voir", "activity_detail", meta_description="")]),
        "missing_meta_description",
    )
    steps = " ".join(card["what_to_do_steps"]).lower()

    assert card["title"] == "Add a meta description to the affected page"
    assert "meta description" in steps
    assert "unique to the page" in steps


def test_single_missing_h1_has_singular_copy():
    card = _fix(_run([_page("/fr/review/page", h1_count=0)]), "missing_h1")
    steps = " ".join(card["what_to_do_steps"]).lower()

    assert card["title"] == "Add an H1 to the affected page"
    assert "one clear h1" in steps
    assert "h2 or h3" in steps


def test_cross_cutting_429_card_is_family_neutral():
    families = {
        "collection_page": ["/fr/category/escape-game", "/fr/category/karting"],
        "activity_detail": ["/fr/annonce/a1/voir", "/fr/annonce/a2/voir"],
        "location_landing": ["/fr/lieu/lyon"],
        "standard": ["/fr/theme/cadeau"],
    }
    pages = [
        _page(url, family, status_code=429)
        for family, urls in families.items()
        for url in urls
    ]
    card = _fix(_run(pages), "rate_limited_page")

    assert card["page_template_family"] == "mixed"
    assert card["title"] == "Check pages blocked by rate limiting"
    assert len(card["affected_pages"]) == 6
''',
)

print("Review presentation contract patch applied.")
