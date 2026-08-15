import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const harness = readFileSync("scripts/standard150-ramp-harness.py", "utf8");
const worker = readFileSync("scanner-api/app/main.py", "utf8");

test("load harness exercises server-owned admission and never creates ScanRun directly", () => {
  assert.match(harness, /startStandardScanJob/);
  assert.match(harness, /getCustomerScanResult/);
  assert.doesNotMatch(harness, /entities\/ScanRun[^\n]*POST|create_scan_run|ScanRun\.create/);
  assert.doesNotMatch(harness, /scan_id[^\n]*startStandardScanJob/);
  assert.match(harness, /--double-submit/);
  assert.match(harness, /scan_admission_busy/);
});

test("durable worker emits load-quality counters keyed by scan id", () => {
  assert.match(worker, /emit\(\s*"scan_job_crawl_completed"/);
  assert.match(worker, /scan_id=scan_id/);
  assert.match(worker, /\*\*scan_metrics\(result\)/);
  assert.match(harness, /jsonPayload\.event="scan_job_crawl_completed"/);
  assert.match(harness, /rate_limited_pages/);
  assert.match(harness, /server_error_pages/);
});
