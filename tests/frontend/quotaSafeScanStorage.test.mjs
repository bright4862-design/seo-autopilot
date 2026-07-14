import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const main = readFileSync("src/main.jsx", "utf8");
const recovery = readFileSync("src/lib/scanStorageRecovery.js", "utf8");
const model = readFileSync("src/lib/scanRunModel.js", "utf8");
const schema = readFileSync("base44/entities/ScanRun.jsonc", "utf8");

test("scan recovery boundaries load before the application", () => {
  assert.match(main, /import ['"]@\/lib\/scanStorageRecovery['"]/);
});

test("browser quota errors cannot invalidate a completed scan", () => {
  assert.match(recovery, /QuotaExceededError/);
  assert.match(recovery, /durable scan history remains authoritative/);
  assert.match(recovery, /return undefined/);
  assert.doesNotMatch(recovery, /throw new Error/);
});

test("browser scan records use canonical arrays and compact history", () => {
  assert.match(recovery, /recommendations,/);
  assert.match(recovery, /pages,/);
  assert.match(recovery, /function compactHistoryEntry/);
  assert.match(recovery, /storage_key:/);
  assert.match(recovery, /startsWith\(SCAN_RECORD_PREFIX\)/);
  assert.doesNotMatch(recovery, /fixes: recommendations/);
  assert.doesNotMatch(recovery, /findings: recommendations/);
  assert.doesNotMatch(recovery, /scanned_pages: pages/);
});

test("scanner responses are capped by selected mode before consumers receive them", () => {
  assert.match(recovery, /function capScannerContainer/);
  assert.match(recovery, /container\.pages_crawled = pagesCrawled/);
  assert.match(recovery, /slice\(0, limit\)/);
});

test("durable ScanRun keeps release authority markers and caps pages", () => {
  for (const field of [
    "scanner_build_revision",
    "advanced_scan_backend",
    "deno_fallback_used",
    "review_evidence_calibration_version",
    "ai_review_backend",
    "python_review_fallback_used",
    "release_gate_eligible",
  ]) {
    assert.match(model, new RegExp(`${field}:`));
    assert.match(schema, new RegExp(`"${field}"`));
  }
  assert.match(model, /pages_crawled: Math\.min\(pageLimit/);
});
