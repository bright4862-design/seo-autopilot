import assert from "node:assert/strict";
import test from "node:test";

import { buildPageAccounting } from "../../src/lib/pageAccounting.js";

test("Wecandoo-style named sections and remainder equal all 5,000 pages found", () => {
  const result = buildPageAccounting(
    { pages_found: 5000 },
    [
      { requested_path_prefix: "/atelier", label: "Atelier section", discovered: 2947 },
      { requested_path_prefix: "/ateliers", label: "Ateliers section", discovered: 2051 },
    ],
  );

  assert.equal(result.total, 5000);
  assert.equal(result.namedTotal, 4998);
  assert.equal(result.remainder, 2);
  assert.deepEqual(result.rows.at(-1), {
    key: "other",
    label: "Homepage and other pages",
    path: "",
    count: 2,
  });
  assert.equal(result.rows.reduce((sum, row) => sum + row.count, 0), 5000);
});

test("IKEA-style partial evidence exposes all 783 pages not assigned to a named section", () => {
  const result = buildPageAccounting(
    { pages_found: 1200 },
    [{ requested_path_prefix: "/fr", label: "FR folder", discovered: 417 }],
  );

  assert.equal(result.namedTotal, 417);
  assert.equal(result.remainder, 783);
  assert.equal(result.isPartial, true);
  assert.equal(result.rows.reduce((sum, row) => sum + row.count, 0), 1200);
});

test("duplicate prefixes and over-reported sections never exceed pages_found", () => {
  const result = buildPageAccounting(
    { pages_found: 10 },
    [
      { requested_path_prefix: "/fr", label: "FR folder", discovered: 8 },
      { requested_path_prefix: "/FR", label: "Duplicate FR folder", discovered: 8 },
      { requested_path_prefix: "/en", label: "EN folder", discovered: 20 },
    ],
  );

  assert.deepEqual(result.rows.map(({ key, count }) => ({ key, count })), [
    { key: "/fr", count: 8 },
    { key: "/en", count: 2 },
  ]);
  assert.equal(result.namedTotal, 10);
  assert.equal(result.remainder, 0);
  assert.equal(result.isPartial, true);
});

test("invalid section counts become an explicit other-pages total", () => {
  const result = buildPageAccounting(
    { pages_found: "12" },
    [
      { requested_path_prefix: "/bad", discovered: -5 },
      { requested_path_prefix: "/unknown", discovered: "not-a-number" },
      { requested_path_prefix: "", discovered: 9 },
    ],
  );

  assert.deepEqual(result.rows, [{
    key: "other",
    label: "Homepage and other pages",
    path: "",
    count: 12,
  }]);
  assert.equal(result.namedTotal, 0);
  assert.equal(result.remainder, 12);
  assert.equal(result.isPartial, true);
});

test("an empty discovery result has no invented page rows", () => {
  assert.deepEqual(buildPageAccounting({ pages_found: 0 }, []), {
    total: 0,
    namedTotal: 0,
    remainder: 0,
    rows: [],
    isPartial: false,
  });
});
