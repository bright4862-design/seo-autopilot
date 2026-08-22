import assert from "node:assert/strict";
import test from "node:test";

import { buildCustomerProjection } from "../../base44/functions/getCustomerScanResult/projection.js";
import { RELEASE_FINGERPRINT } from "../../src/lib/generatedReleaseContract.js";

/**
 * Patch D - a saved scan never shows a ratio that cannot be true.
 *
 * The scans already sealed in production carry 126/1, 35/30 and 47/6. Those
 * records are immutable: their seal covers the numbers, so the numbers cannot be
 * corrected in place and the browser must not recompute an authority it does not
 * hold. What it can do is refuse to render an impossible ratio.
 *
 * So the server derives a validity verdict per repair and suppresses the ratio
 * where the arithmetic fails, leaving a neutral absolute count. A customer sees
 * "126 checked pages are affected" rather than "126 of 1", and the signed prose
 * is left untouched for owner diagnostics rather than being parsed apart here.
 */

function run() {
  return {
    id: "scan_historical",
    status: "complete",
    release_gate_eligible: true,
    score_is_provisional: false,
    beta_revision_fingerprint: RELEASE_FINGERPRINT,
  };
}

const FIX_LIST = { id: "fl_historical", is_authoritative: true };

function historicalFix(overrides = {}) {
  return {
    fix_id: "fix_orphans",
    rule: "potential_orphan_pages",
    issue_title: "Link orphaned pages",
    priority: "medium",
    page_scope: "family",
    page_template_family: "homepage",
    affected_pages: Array.from({ length: 126 }, (unused, index) => `/w${index}`),
    page_count: 126,
    priority_reason: "126 of 1 searchable homepage pages checked are affected.",
    // Coverage counts live in priority_context, which is where the sealed rows
    // actually carry them.
    priority_context: {
      affected_checked: 126,
      checked_eligible: 1,
      checked_coverage: 126,
      ...(overrides.priority_context || {}),
    },
    ...overrides,
  };
}

function project(fix) {
  return buildCustomerProjection({
    run: run(),
    fixList: FIX_LIST,
    fixItems: [fix],
    fullAccess: true,
    authorityVerified: true,
  }).fixItems[0];
}

test("an impossible historical ratio is not rendered", () => {
  const item = project(historicalFix());

  assert.equal(item.priority_context.checked_coverage, null, "126 of 1 must not reach the customer");
  assert.equal(item.coverage_context_validity, "invalid");
});

test("the customer still sees how many pages are affected", () => {
  /** Suppressing the ratio must not suppress the finding. */
  const item = project(historicalFix());

  assert.equal(item.priority_context.affected_checked, 126);
  assert.equal(item.page_count, 126);
});

test("the impossible prose is replaced rather than shown", () => {
  const item = project(historicalFix());

  assert.doesNotMatch(item.priority_reason, /126 of 1/);
  assert.match(item.priority_reason, /126 checked pages are affected/);
  assert.match(item.coverage_context_note, /unavailable for this saved scan/i);
});

test("a valid historical ratio is left exactly as it was sealed", () => {
  const item = project(historicalFix({
    affected_pages: ["/p0", "/p1", "/p2", "/p3", "/p4"],
    page_count: 5,
    priority_context: { affected_checked: 5, checked_eligible: 20, checked_coverage: 0.25 },
    page_template_family: "product_page",
    priority_reason: "5 of 20 product pages checked are affected.",
  }));

  assert.equal(item.coverage_context_validity, "valid");
  assert.equal(item.priority_context.checked_coverage, 0.25);
  assert.equal(item.priority_reason, "5 of 20 product pages checked are affected.");
});

test("a ratio with no denominator is neither valid nor impossible", () => {
  const item = project(historicalFix({
    affected_pages: ["/a", "/b"],
    page_count: 2,
    priority_context: { affected_checked: 2, checked_eligible: null, checked_coverage: null },
    priority_reason: "2 checked pages are affected.",
  }));

  assert.equal(item.coverage_context_validity, "unmeasured");
  assert.equal(item.priority_context.checked_coverage, null);
  assert.equal(item.priority_reason, "2 checked pages are affected.");
});

test("the searchable ratio is suppressed on the same evidence", () => {
  const item = project(historicalFix({
    priority_context: { affected_checked: 126, checked_eligible: 1, checked_coverage: 126,
      indexable_affected: 126, indexable_checked_eligible: 1, searchable_coverage: 126 },
  }));

  assert.equal(item.priority_context.searchable_coverage, null);
});

test("a Pretto-shaped 35 of 30 is suppressed", () => {
  const item = project(historicalFix({
    affected_pages: Array.from({ length: 35 }, (unused, index) => `/loan/${index}`),
    page_count: 35,
    priority_context: { affected_checked: 35, checked_eligible: 30, checked_coverage: 35 / 30 },
    page_template_family: "loan_program",
    priority_reason: "35 of 30 loan pages checked are affected.",
  }));

  assert.equal(item.coverage_context_validity, "invalid");
  assert.equal(item.priority_context.checked_coverage, null);
  assert.doesNotMatch(item.priority_reason, /35 of 30/);
});
