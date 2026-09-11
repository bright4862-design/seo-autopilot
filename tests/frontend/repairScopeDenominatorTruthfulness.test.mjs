import assert from "node:assert/strict";
import test from "node:test";

import { repairScopeSummary } from "../../src/lib/repairPresentation.js";


test("general repair scope does not recreate a ratio when backend coverage is incomparable", () => {
  const item = {
    page_count: 5,
    priority_context: {
      affected_checked: 5,
      checked_eligible: 20,
      checked_coverage: null,
    },
  };

  assert.equal(repairScopeSummary(item), "5 pages");
});


test("searchable repair scope does not recreate a ratio when backend searchable coverage is incomparable", () => {
  const item = {
    page_count: 5,
    priority_context: {
      indexable_affected: 3,
      indexable_checked_eligible: 10,
      searchable_coverage: null,
      affected_checked: 5,
      checked_eligible: 20,
      checked_coverage: null,
    },
  };

  assert.equal(repairScopeSummary(item), "5 pages");
});


test("repair scope keeps an N-of-M sentence when backend explicitly validated the same universe", () => {
  const item = {
    page_count: 5,
    priority_context: {
      affected_checked: 5,
      checked_eligible: 20,
      checked_coverage: 0.25,
    },
  };

  assert.equal(repairScopeSummary(item), "5 of 20 relevant pages checked");
});
