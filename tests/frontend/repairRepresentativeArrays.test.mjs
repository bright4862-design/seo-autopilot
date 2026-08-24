import assert from "node:assert/strict";
import test from "node:test";

import { firstFailedRepairInvariant } from "../../base44/functions/persistDurableScanAuthority/repairInvariants.js";

function sitewide(overrides = {}) {
  return {
    rule: "canonical_missing",
    page_scope: "sitewide",
    page_template_family: "",
    affected_pages: ["/", "/loans/dscr", "/loans/bridge", "/blog/a", "/blog/b"],
    page_count: 5,
    family_breakdown: { homepage: 1, loan_program: 2, guide_article: 2 },
    representative_pages_by_family: {
      homepage: ["/"],
      loan_program: ["/loans/dscr", "/loans/bridge"],
      guide_article: ["/blog/a", "/blog/b"],
    },
    affected_pages_complete: true,
    affected_reported: 5,
    affected_observed: 5,
    affected_eligible: 5,
    checked_eligible: 150,
    indexable_affected: 5,
    indexable_checked_eligible: 150,
    ...overrides,
  };
}

test("sitewide repairs may carry multiple verified representatives per family", () => {
  assert.equal(firstFailedRepairInvariant(sitewide()), "");
});

test("every representative in an array must still be an affected page", () => {
  assert.equal(
    firstFailedRepairInvariant(sitewide({
      representative_pages_by_family: {
        homepage: ["/"],
        loan_program: ["/loans/dscr", "/not-affected"],
        guide_article: ["/blog/a", "/blog/b"],
      },
    })),
    "representative_is_not_an_affected_page",
  );
});

test("legacy single representative strings remain valid", () => {
  assert.equal(firstFailedRepairInvariant(sitewide({
    representative_pages_by_family: { homepage: "/", loan_program: "/loans/dscr", guide_article: "/blog/a" },
  })), "");
});
