import assert from "node:assert/strict";
import test from "node:test";

import { refreshGroupedCountEvidence } from "../../src/lib/groupedCountCopy.js";

test("a grouped result replaces a stale one-page sentence with its final count", () => {
  const result = refreshGroupedCountEvidence({
    current_value: "1 affected page: /gb/import-duty/calculator",
    page_count: 9,
    affected_pages: ["/a", "/b", "/c"],
  });

  assert.equal(result.page_count, 9);
  assert.equal(result.current_value, "9 affected pages in this group.");
});

test("the listed URLs prevent a grouped count from shrinking below visible evidence", () => {
  const result = refreshGroupedCountEvidence({
    current_value: "1 affected page",
    page_count: 1,
    affected_pages: ["/a", "/b", "/c"],
  });

  assert.equal(result.page_count, 3);
  assert.equal(result.current_value, "3 affected pages in this group.");
});

test("a true one-page group uses singular customer copy", () => {
  const result = refreshGroupedCountEvidence({
    page_count: 1,
    affected_pages: ["/a"],
  });

  assert.equal(result.current_value, "1 affected page in this group.");
});
