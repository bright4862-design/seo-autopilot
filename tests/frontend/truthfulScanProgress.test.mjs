import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(
  new URL("../../src/components/scan/TruthfulScanProgress.jsx", import.meta.url),
  "utf8",
);

test("truthful scan progress consumes the shared presentation model", () => {
  assert.match(source, /scanProgressModel/);
  assert.match(source, /progress\.phaseLabel/);
  assert.match(source, /progress\.countLabel/);
  assert.match(source, /progress\.canLeavePage/);
});

test("truthful scan progress does not invent crawler denominators or own scan state", () => {
  assert.doesNotMatch(source, /150/);
  assert.doesNotMatch(source, /pagesFound/);
  assert.doesNotMatch(source, /pages discovered/);
  assert.doesNotMatch(source, /fetch\(/);
  assert.doesNotMatch(source, /getScanRun/);
  assert.doesNotMatch(source, /setInterval/);
  assert.doesNotMatch(source, /base44/);
});

test("leave-page reassurance is gated by the explicit durable model flag", () => {
  assert.match(source, /progress\.canLeavePage \?/);
  assert.match(source, /running in the background/);
});
