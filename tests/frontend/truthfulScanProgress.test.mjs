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
  assert.match(source, /leave this page and return to the scan from your history/);
});

test("saved-scan escape link cannot appear before durable background execution is proven", () => {
  assert.match(source, /showSavedScanLink\s*&&\s*progress\.canLeavePage\s*&&\s*typeof onOpenSavedScan === "function"/s);
  assert.match(source, /canOpenSavedScan \?/);
});

test("elapsed time does not imply the scan is slow or has started", () => {
  assert.doesNotMatch(source, /taking longer than usual/i);
  assert.match(source, /progress\.status === "queued"/);
  assert.match(source, /updates when your scan starts/);
});

test("scan status announcements stay polite instead of repeatedly interrupting assistive technology", () => {
  assert.match(source, /role="status" aria-live="polite"/);
  assert.doesNotMatch(source, /aria-live="assertive"/);
});

test("the ticking elapsed time stays outside the live phase announcement", () => {
  assert.match(source, /<p\b[^>]*role="status"[^>]*>\{phase\}<\/p>/);
  assert.doesNotMatch(source, /<div\b[^>]*aria-live=/);
});
