from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"missing patch anchor: {label}")
    return text.replace(old, new, 1)


review_path = ROOT / "src/lib/reviewContract.js"
review = review_path.read_text(encoding="utf-8")

helpers = '''export function isRateLimitFinding(fix = {}) {
  const rule = String(fix?.rule || fix?.issue_type || "").toLowerCase();
  const source = String(fix?.source || "").toLowerCase();
  const text = `${rule} ${fix?.category || ""} ${fix?.title || ""} ${fix?.issue_title || ""} ${fix?.current_value || ""} ${fix?.fetch_error || ""}`.toLowerCase();
  const status = Number(fix?.status_code || fix?.current_status_code || fix?.http_status || fix?.evidence?.status_code || 0);
  return (
    status === 429 ||
    ["rate_limited_page", "blocked_page", "blocked_page_429", "scanner_blocked"].includes(rule) ||
    source.startsWith("scanner_verified_failed_pages:429") ||
    text.includes("429") ||
    text.includes("rate limit") ||
    text.includes("rate-limit") ||
    text.includes("too many requests") ||
    text.includes("bot protection")
  );
}


export function shouldUseLegacyRateLimitPresentation(scanRecord = {}, fix = {}) {
  return isRateLimitFinding(fix) && !hasAuthoritativePythonReview(scanRecord);
}
'''

if "export function isRateLimitFinding" not in review:
    review = replace_once(
        review,
        "\n\nexport function normalizeFindingEvidence(fix = {}) {",
        f"\n\n{helpers}\nexport function normalizeFindingEvidence(fix = {{}}) {{",
        "review presentation helpers",
    )

review = re.sub(
    r'''  const rule = String\(fix\?\.rule \|\| fix\?\.issue_type \|\| ""\)\.toLowerCase\(\);\n  const source = String\(fix\?\.source \|\| ""\)\.toLowerCase\(\);\n  const rateLimited =\n    \["rate_limited_page", "blocked_page", "blocked_page_429", "scanner_blocked"\]\.includes\(rule\) \|\|\n    source\.startsWith\("scanner_verified_failed_pages:429"\);''',
    "  const rateLimited = isRateLimitFinding(fix);",
    review,
    count=1,
)
review_path.write_text(review, encoding="utf-8")

fixlist_path = ROOT / "src/pages/FixList.jsx"
fixlist = fixlist_path.read_text(encoding="utf-8")
fixlist = replace_once(
    fixlist,
    'import { Button } from "@/components/ui/button";\n',
    'import { Button } from "@/components/ui/button";\nimport { isRateLimitFinding, shouldUseLegacyRateLimitPresentation } from "@/lib/reviewContract";\n',
    "FixList reviewContract import",
)

new_normalize = '''function normalizeRecommendation(item = {}, scanRecord = {}) {
  const legacyBlocked429 = shouldUseLegacyRateLimitPresentation(scanRecord, item);
  const evidence = legacyBlocked429 ? extractRecommendationEvidence(item, scanRecord) : {};
  const priority = legacyBlocked429 ? blockedPriority(item, evidence) : normalizePriority(item.priority);
  const category = String(item.category || "other").toLowerCase();
  const affectedPages = firstArray([item.affected_pages, item.pages, item.page_urls]);
  const fallbackPage = item.page_url || item.url || affectedPages[0] || "";
  const bucket = legacyBlocked429 ? "needs_developer" : getIssueBucket(item);
  const customerCategory = legacyBlocked429 ? "Scan coverage" : item.customer_category || CATEGORY_LABELS[category] || humanize(category || "Website improvement");
  const title = legacyBlocked429 ? build429Title(evidence) : cleanString(item.issue_title || item.title || item.name) || buildSpecificTitle(item);
  const explanation = legacyBlocked429 ? build429Explanation(evidence) : cleanString(item.plain_english_explanation || item.plain_english_summary || item.explanation || item.description || item.summary || item.recommendation) || buildSpecificExplanation(item);
  const whyItMatters = legacyBlocked429 ? build429Why(evidence) : cleanString(item.why_it_matters || item.impact || item.reason) || buildSpecificWhy(item);
  const recommendation = legacyBlocked429 ? build429Recommendation(evidence) : cleanString(item.simple_next_step || item.recommended_value || item.recommendation || item.suggested_fix || item.ai_recommendation) || "Review the affected page and make the recommended update.";
  const needsHelp = bucket === "needs_developer";

  return {
    id: item.id || item.fix_id || stableId(`${fallbackPage}|${category}|${title}`),
    original: item,
    category,
    priority,
    bucket,
    customerCategory,
    title,
    explanation,
    whyItMatters,
    recommendation,
    affectedPages: unique([...affectedPages.map(String), ...(fallbackPage ? [fallbackPage] : [])]),
    currentValue: legacyBlocked429 ? "HTTP 429 — crawler was rate-limited or blocked" : cleanString(item.current_value || item.current || item.detected_value),
    pageType: legacyBlocked429 && evidence.scopeRelationship === "sibling_sous_dossier" ? "Sibling sous-dossier" : cleanString(item.page_type || item.page_value_label || item.business_importance),
    defectClass: legacyBlocked429 ? "Rate-limit / crawler access" : cleanString(item.primary_defect_class || item.meta_regeneration_gate),
    pageValueLabel: legacyBlocked429 ? evidence.businessValueLabel : cleanString(item.page_value_label),
    businessImportance: legacyBlocked429 ? evidence.businessImportance : cleanString(item.business_importance),
    metaGate: cleanString(item.meta_regeneration_gate),
    scopeRelationship: legacyBlocked429 ? evidence.scopeRelationship : cleanString(item.scope_relationship),
    pageScope: cleanString(item.page_scope),
    evidenceStatus: cleanString(item.evidence_status || item.verification_state),
    needsHelp,
    generalSteps: legacyBlocked429 ? build429Steps(evidence) : buildGeneralSteps(item, recommendation, needsHelp),
  };
}
'''

fixlist, count = re.subn(
    r"function normalizeRecommendation\(item = \{\}, scanRecord = \{\}\) \{.*?\n\}\n\nfunction extractRecommendationEvidence",
    new_normalize + "\nfunction extractRecommendationEvidence",
    fixlist,
    count=1,
    flags=re.S,
)
if count != 1:
    raise RuntimeError("normalizeRecommendation patch did not apply exactly once")

fixlist, count = re.subn(
    r"function isBlocked429\(item = \{\}\) \{.*?\n\}",
    "function isBlocked429(item = {}) {\n  return isRateLimitFinding(item);\n}",
    fixlist,
    count=1,
    flags=re.S,
)
if count != 1:
    raise RuntimeError("isBlocked429 patch did not apply exactly once")

fixlist = replace_once(
    fixlist,
    '''function buildEvidenceItems(recommendation) {
  const items = [];
  if (recommendation.scopeRelationship) items.push({ label: "Scope", value: humanize(recommendation.scopeRelationship) });
''',
    '''function buildEvidenceItems(recommendation) {
  const items = [];
  if (recommendation.pageScope) items.push({ label: "Scope", value: humanize(recommendation.pageScope) });
  else if (recommendation.scopeRelationship) items.push({ label: "Scope", value: humanize(recommendation.scopeRelationship) });
  if (recommendation.evidenceStatus) items.push({ label: "Evidence", value: humanize(recommendation.evidenceStatus) });
''',
    "evidence scope display",
)
fixlist_path.write_text(fixlist, encoding="utf-8")

contract_test_path = ROOT / "tests/frontend/reviewContract.test.mjs"
contract_test = contract_test_path.read_text(encoding="utf-8")
contract_test = replace_once(
    contract_test,
    '''  hasAuthoritativePythonReview,
  selectFinalReviewFixes,
''',
    '''  hasAuthoritativePythonReview,
  isRateLimitFinding,
  selectFinalReviewFixes,
  shouldUseLegacyRateLimitPresentation,
''',
    "reviewContract test imports",
)
if "authoritative rate-limit findings keep backend presentation" not in contract_test:
    contract_test += '''

test("authoritative rate-limit findings keep backend presentation", () => {
  const finding = {
    rule: "rate_limited_page",
    source: "scanner_verified_failed_pages:429",
    priority: "high",
    title: "Check pages blocked by rate limiting",
    page_scope: "cross_cutting",
    page_template_family: "mixed",
    evidence_status: "needs_verification",
  };

  assert.equal(isRateLimitFinding(finding), true);
  assert.equal(
    shouldUseLegacyRateLimitPresentation(
      { ai_review_backend: "python_review_api", python_review_fallback_used: false },
      finding,
    ),
    false,
  );
});

test("legacy and fallback rate-limit findings retain compatibility presentation", () => {
  const finding = { status_code: 429, title: "Too Many Requests" };

  assert.equal(shouldUseLegacyRateLimitPresentation({}, finding), true);
  assert.equal(
    shouldUseLegacyRateLimitPresentation(
      { ai_review_backend: "python_review_api", python_review_fallback_used: true },
      finding,
    ),
    true,
  );
  assert.equal(shouldUseLegacyRateLimitPresentation({}, { rule: "canonical_missing" }), false);
});
'''
contract_test_path.write_text(contract_test, encoding="utf-8")

source_test = '''import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("../../src/pages/FixList.jsx", import.meta.url), "utf8");

test("FixList only rewrites rate-limit presentation for legacy records", () => {
  assert.match(source, /const legacyBlocked429 = shouldUseLegacyRateLimitPresentation\(scanRecord, item\)/);
  assert.match(source, /title = legacyBlocked429 \? build429Title/);
  assert.match(source, /generalSteps: legacyBlocked429 \? build429Steps/);
  assert.doesNotMatch(source, /const blocked429 = isBlocked429\(item\)/);
});
'''
write("tests/frontend/fixListAuthority.test.mjs", source_test)
