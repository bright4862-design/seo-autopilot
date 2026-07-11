import assert from "node:assert/strict";
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
