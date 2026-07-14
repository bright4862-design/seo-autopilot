import assert from "node:assert/strict";
import test from "node:test";

import {
  hasAuthoritativePythonReview,
  isRateLimitFinding,
  normalizeReviewEvidenceState,
  selectFinalReviewFixes,
  shouldUseLegacyRateLimitPresentation,
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

test("insufficient classifier evidence stays provisional in the frontend contract", () => {
  assert.deepEqual(
    normalizeReviewEvidenceState({ scan_status: "inconclusive_insufficient_evidence" }),
    {
      scan_status: "inconclusive_insufficient_evidence",
      review_confidence_state: "insufficient_evidence",
      score_is_provisional: true,
      access_evidence_state: "insufficient_evidence",
    },
  );
});
