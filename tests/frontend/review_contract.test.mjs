import test from "node:test";
import assert from "node:assert/strict";

import { getPriorityLabel } from "../../src/lib/friendlyLabels.js";
import { normalizeActionPriority, normalizeFindingEvidence, normalizeReviewEvidenceState, normalizeReviewScope } from "../../src/lib/reviewContract.js";

test("compact actions preserve critical priority", () => {
  assert.equal(normalizeActionPriority("critical"), "critical");
  assert.equal(normalizeActionPriority("high"), "high");
  assert.equal(normalizeActionPriority("medium"), "medium");
  assert.equal(normalizeActionPriority("low"), "low");
});

test("unknown compact action priorities fall back safely", () => {
  assert.equal(normalizeActionPriority("urgent"), "medium");
  assert.equal(normalizeActionPriority(""), "medium");
});

test("the customer-facing label contract accepts critical", () => {
  assert.equal(getPriorityLabel("critical"), "High impact");
  assert.equal(getPriorityLabel("high"), "High impact");
});

test("sitewide scope does not masquerade as a template family", () => {
  assert.deepEqual(
    normalizeReviewScope({ page_scope: "sitewide", page_template_family: "loan_program", affected_pages: ["/a", "/b"] }, "standard"),
    { page_scope: "sitewide", page_template_family: "" },
  );
});

test("cross-cutting evidence keeps the mixed compatibility marker", () => {
  assert.deepEqual(
    normalizeReviewScope({ page_template_family: "mixed", affected_pages: ["/a", "/b"] }, "standard"),
    { page_scope: "cross_cutting", page_template_family: "mixed" },
  );
});

test("normal reviewed findings retain their family", () => {
  assert.deepEqual(
    normalizeReviewScope({ page_scope: "family", page_template_family: "loan_program", affected_pages: ["/a", "/b"] }, "standard"),
    { page_scope: "family", page_template_family: "loan_program" },
  );
});




test("rate-limit findings retain a needs-verification contract", () => {
  assert.deepEqual(
    normalizeFindingEvidence({ rule: "rate_limited_page", source: "scanner_verified_failed_pages:429" }),
    {
      evidence_status: "needs_verification",
      verification_state: "needs_verification",
      limitation_code: "rate_limit_requires_log_confirmation",
    },
  );
});


test("explicit finding evidence is preserved", () => {
  assert.deepEqual(
    normalizeFindingEvidence({ rule: "canonical_missing", evidence_status: "sample_based", verification_state: "sample_based", limitation_code: "sample_only" }),
    {
      evidence_status: "sample_based",
      verification_state: "sample_based",
      limitation_code: "sample_only",
    },
  );
});


test("blocked review state survives frontend record normalization", () => {
  const state = normalizeReviewEvidenceState({
    scan_status: "blocked_or_incomplete",
    review_confidence_state: "blocked_access_needs_verification",
    score_is_provisional: true,
    access_evidence_state: "blocked",
    website_health_report: { health_grade: "Blocked / incomplete" },
  });
  assert.deepEqual(state, {
    scan_status: "blocked_or_incomplete",
    review_confidence_state: "blocked_access_needs_verification",
    score_is_provisional: true,
    access_evidence_state: "blocked",
  });
});


test("partial access limitations remain provisional in the saved contract", () => {
  assert.deepEqual(
    normalizeReviewEvidenceState({ scan_status: "complete_with_access_limitations" }),
    {
      scan_status: "complete_with_access_limitations",
      review_confidence_state: "partial_access_needs_verification",
      score_is_provisional: true,
      access_evidence_state: "partial_access_limited",
    },
  );
});
