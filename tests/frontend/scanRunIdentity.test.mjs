import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { mergePersistedScanRunRecord } from "../../src/lib/persistedScanRecord.js";
import {
  STANDARD_ACTIVE_SCAN_TTL_MS,
  ScanRunConflictError,
  buildScanRequestIdentity,
  buildStaleScanRetryFields,
  normalizeScanTarget,
  resolveScanRunReplay,
} from "../../src/lib/scanRunIdentity.js";

const scanForm = readFileSync("src/components/scan/ScanWebsiteForm.jsx", "utf8");
const activeProject = readFileSync("src/lib/activeProject.js", "utf8");
const scanRuns = readFileSync("src/lib/scanRuns.js", "utf8");
const wrapper = readFileSync("base44/functions/runAdvancedScan/entry.ts", "utf8");
const scanRunSchema = JSON.parse(readFileSync("base44/entities/ScanRun.jsonc", "utf8"));

test("same request key and normalized target reuses the durable ScanRun", () => {
  const identity = buildScanRequestIdentity({
    websiteUrl: "HTTPS://Example.com/pricing#top",
    scanMode: "advanced",
    requestId: "req-1",
    idempotencyKey: "req-1",
  });
  const run = {
    id: "scan-1",
    request_id: "req-1",
    website_url: "https://example.com/pricing",
    scan_mode: "advanced",
    status: "complete",
  };
  const replay = resolveScanRunReplay({ requestRuns: [run], activeRuns: [], identity });
  assert.equal(replay.action, "reuse");
  assert.equal(replay.reason, "request_replay");
  assert.equal(replay.run.id, "scan-1");
  assert.equal(normalizeScanTarget("example.com/pricing#other"), "https://example.com/pricing");
});

test("same request key with a conflicting target or mode fails closed", () => {
  const identity = buildScanRequestIdentity({
    websiteUrl: "https://example.com/other",
    scanMode: "advanced",
    requestId: "req-1",
  });
  assert.throws(
    () => resolveScanRunReplay({
      requestRuns: [{ request_id: "req-1", website_url: "https://example.com/pricing", scan_mode: "advanced" }],
      activeRuns: [],
      identity,
    }),
    ScanRunConflictError,
  );
});

test("fresh active work for the same normalized target and mode is reused", () => {
  const identity = buildScanRequestIdentity({ websiteUrl: "example.com", scanMode: "advanced", requestId: "req-new" });
  const now = Date.parse("2026-08-01T20:00:00.000Z");
  const active = { id: "scan-active", request_id: "req-old", website_url: "https://example.com/", scan_mode: "advanced", status: "crawling", started_at: new Date(now - STANDARD_ACTIVE_SCAN_TTL_MS + 1).toISOString() };
  const replay = resolveScanRunReplay({ requestRuns: [], activeRuns: [active], identity, now });
  assert.equal(replay.action, "reuse");
  assert.equal(replay.reason, "active_target");
  assert.equal(replay.run.id, "scan-active");
});

test("stale active work no longer blocks a new Standard scan", () => {
  const identity = buildScanRequestIdentity({ websiteUrl: "example.com", scanMode: "advanced", requestId: "req-new" });
  const now = Date.parse("2026-08-01T20:00:00.000Z");
  const stale = { id: "scan-stale", request_id: "req-old", website_url: "https://example.com/", scan_mode: "advanced", status: "reviewing", reviewing_at: new Date(now - STANDARD_ACTIVE_SCAN_TTL_MS - 1).toISOString() };
  const replay = resolveScanRunReplay({ requestRuns: [], activeRuns: [stale], identity, now });
  assert.equal(replay.action, "create");
  assert.equal(replay.reason, "stale_active");
  assert.deepEqual(replay.staleRuns.map((run) => run.id), ["scan-stale"]);
});

test("stale candidates do not hide a later fresh active replay", () => {
  const identity = buildScanRequestIdentity({ websiteUrl: "example.com", scanMode: "advanced", requestId: "req-new" });
  const now = Date.parse("2026-08-01T20:00:00.000Z");
  const stale = { id: "scan-stale", website_url: "https://example.com/", scan_mode: "advanced", status: "queued", queued_at: new Date(now - STANDARD_ACTIVE_SCAN_TTL_MS - 1).toISOString() };
  const fresh = { id: "scan-fresh", website_url: "https://example.com/", scan_mode: "advanced", status: "crawling", started_at: new Date(now - 1_000).toISOString() };
  const replay = resolveScanRunReplay({ requestRuns: [], activeRuns: [stale, fresh], identity, now });
  assert.equal(replay.action, "reuse");
  assert.equal(replay.run.id, "scan-fresh");
  assert.deepEqual(replay.staleRuns.map((run) => run.id), ["scan-stale"]);
});

test("legacy active rows without a valid timestamp cannot block forever", () => {
  const identity = buildScanRequestIdentity({ websiteUrl: "example.com", scanMode: "advanced", requestId: "req-new" });
  const undated = { id: "scan-undated", website_url: "https://example.com/", scan_mode: "advanced", status: "queued", queued_at: "not-a-date" };
  const replay = resolveScanRunReplay({ requestRuns: [], activeRuns: [undated], identity, now: Date.parse("2026-08-01T20:00:00.000Z") });
  assert.equal(replay.action, "create");
  assert.deepEqual(replay.staleRuns.map((run) => run.id), ["scan-undated"]);
});

test("an exact stale request retries the same durable row instead of staying active forever", () => {
  const identity = buildScanRequestIdentity({ websiteUrl: "example.com", scanMode: "advanced", requestId: "req-exact" });
  const keyed = { id: "scan-exact", request_id: "req-exact", website_url: "https://example.com/", scan_mode: "advanced", status: "crawling", started_at: "2020-01-01T00:00:00.000Z" };
  const replay = resolveScanRunReplay({ requestRuns: [keyed], activeRuns: [keyed], identity, now: Date.parse("2026-08-01T20:00:00.000Z") });
  assert.equal(replay.action, "retry_same_run");
  assert.equal(replay.reason, "stale_request");
  assert.equal(replay.run.id, "scan-exact");
  assert.deepEqual(replay.staleRuns, []);
});

test("stale request retry keeps its key and clears terminal state for a numbered attempt", () => {
  const identity = buildScanRequestIdentity({ websiteUrl: "example.com", scanMode: "advanced", requestId: "req-exact" });
  const retry = buildStaleScanRetryFields(
    { attempt_count: 2, error_code: "old_failure", completed_at: "2026-08-01T18:00:00.000Z" },
    identity,
    { now: Date.parse("2026-08-01T20:00:00.000Z") },
  );
  assert.equal(retry.request_id, "req-exact");
  assert.equal(retry.idempotency_key, "req-exact");
  assert.equal(retry.attempt_count, 3);
  assert.equal(retry.status, "crawling");
  assert.equal(retry.started_at, "2026-08-01T20:00:00.000Z");
  assert.equal(retry.completed_at, "");
  assert.equal(retry.error_code, "");
});

test("stale exact-request recovery restarts only after updating the existing row", () => {
  assert.match(scanRuns, /replay\.action === "retry_same_run"/);
  assert.match(scanRuns, /ScanRun\.update\(run\.id, retryFields\)/);
  assert.match(scanRuns, /buildStaleScanRetryFields\(run, identity\)/);
  assert.match(scanRuns, /replayReason: "stale_request_retry"/);
  assert.match(scanRuns, /replayed: false/);
  assert.match(scanRuns, /cross-browser\/process[\s\S]*exact-once can be claimed/);
});

test("ScanRun schema remains compatible with legacy empty project ids until a backfill is proven", () => {
  assert.deepEqual(scanRunSchema.required, ["project_id", "website_url"]);
  assert.equal(scanRunSchema.properties.project_id.type, "string");
  assert.equal(Object.hasOwn(scanRunSchema.properties.project_id, "minLength"), false);
});

test("form ensures an owner-bound domain project before creating the ScanRun", () => {
  const ensureIndex = scanForm.indexOf("await ensureScanProject");
  const beginIndex = scanForm.indexOf("await beginScanRun");
  assert.ok(ensureIndex >= 0 && ensureIndex < beginIndex);
  assert.match(scanForm, /projectId: scanProject\.id/);
  assert.match(activeProject, /BusinessProject\.filter\([\s\S]*owner_user_id: user\.id/);
  assert.match(activeProject, /const projectFields = \{[\s\S]*owner_user_id: user\.id/);
  assert.match(activeProject, /BusinessProject\.create\(projectFields\)/);
  assert.match(activeProject, /normalizedScanDomain\(candidate\.website_url\) === domain/);
  assert.match(scanRuns, /if \(!String\(projectId \|\| ""\)\.trim\(\)\)/);
  assert.match(scanRuns, /error_code: "stale_active_scan"/);
});

test("active replays reopen the exact durable scan instead of a nonexistent history view", () => {
  assert.match(scanForm, /navigate\(`\/dashboard\?scan_id=\$\{encodeURIComponent\(scanId\)\}`\)/);
  assert.doesNotMatch(scanForm, /Reopen it from scan history/);
});

test("form persists identity before network work and Standard always respects robots", () => {
  assert.ok(scanForm.indexOf("await beginScanRun") < scanForm.indexOf("callBase44Function(ADVANCED_SCANNER_FUNCTION"));
  assert.match(scanForm, /const requestId = createScanRequestId\(\)/);
  assert.match(scanForm, /request_id: requestId/);
  assert.match(scanForm, /idempotency_key: idempotencyKey/);
  assert.match(scanForm, /respect_robots_txt: true/);
  assert.doesNotMatch(scanForm, /respect_robots_txt: false/);
  assert.match(scanRuns, /scan_id: created\.id/);
  assert.match(scanRuns, /resolveScanRunReplay/);
});

test("Base44 wrapper forwards and echoes durable identity at the Cloud Run boundary", () => {
  for (const field of ["request_id", "idempotency_key", "scan_id", "scan_run_id", "submitted_url", "normalized_domain", "respect_robots_txt"]) {
    assert.match(wrapper, new RegExp(`${field}:`), `missing ${field}`);
  }
  assert.match(wrapper, /toPythonAdvancedScanResponse\(pythonAttempt\.result, scanMode, requestIdentity\.fields\)/);
  assert.match(wrapper, /\.\.\.requestIdentity/);
});

test("durable reload mapping keeps entity id as scan id and request identity", () => {
  const merged = mergePersistedScanRunRecord(
    { id: "local", request_id: "req-1" },
    { id: "scan-1", request_id: "req-1", fix_list_id: "fix-1" },
  );
  assert.equal(merged.scan_id, "scan-1");
  assert.equal(merged.scan_run_id, "scan-1");
  assert.equal(merged.request_id, "req-1");
  assert.equal(merged.fix_list_id, "fix-1");
  assert.match(scanRuns, /scan_id: run\.id/);
  assert.match(scanRuns, /FixItem\.filter\(\{ fix_list_id: fixList\.id/);
});
