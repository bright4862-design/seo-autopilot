import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync("src/pages/FixList.jsx", "utf8");

test("durable failure copy distinguishes access, stalls, saves, and cancellation", () => {
  assert.match(source, /function durableFailureKind/);
  assert.match(source, /rate\.\?limit\|challenge\|bot\.\?protection/);
  assert.match(source, /heartbeat\|stalled\|orphaned\|vanished/);
  assert.match(source, /persist\|save\.\?fail/);
  assert.match(source, /No authoritative result was saved/);
  assert.match(source, /Progress stopped and FixList safely closed the run/);
  assert.match(source, /Crawling finished, but FixList could not persist/);
  assert.match(source, /This scan was stopped before it finished/);
});

test("terminal recovery exposes the durable scan reference", () => {
  assert.match(source, /reference=\{scanRecord\.scan_id \|\| scanRecord\.id\}/);
  assert.match(source, /Scan reference:/);
});
