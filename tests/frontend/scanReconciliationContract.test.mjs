import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  RECONCILE_QUEUED_AFTER_MS,
  RECONCILE_STARTED_AFTER_MS,
  reconciliationDecision,
  uniqueRows,
} from "../../base44/functions/durableScanWorkerControl/reconciliation.js";

const control = readFileSync("base44/functions/durableScanWorkerControl/index.ts", "utf8");
const worker = readFileSync("scanner-api/app/main.py", "utf8");
const workerJob = readFileSync("scanner-api/app/scan_job.py", "utf8");

const base = {
  id: "scan-1",
  admission_access_id: "access-1",
  attempt_count: 1,
  queued_at: "2026-08-15T10:00:00.000Z",
};
const now = Date.parse("2026-08-15T11:00:00.000Z");

test("queued scans are not reconciled until the queue budget is genuinely stale", () => {
  const freshNow = Date.parse(base.queued_at) + RECONCILE_QUEUED_AFTER_MS - 1;
  assert.equal(reconciliationDecision({ ...base, status: "queued" }, freshNow).action, "skip");
  const stale = reconciliationDecision({ ...base, status: "queued" }, now);
  assert.equal(stale.action, "fail");
  assert.equal(stale.error_code, "scan_queue_reconciliation_timeout");
});

test("worker reconciliation sits after the normal drain/retry envelope", () => {
  assert.ok(RECONCILE_STARTED_AFTER_MS > 30 * 60 * 1000);
  const startedAt = new Date(now - RECONCILE_STARTED_AFTER_MS - 1).toISOString();
  const stale = reconciliationDecision({ ...base, status: "crawling", started_at: startedAt }, now);
  assert.equal(stale.action, "fail");
  assert.equal(stale.error_code, "worker_reconciliation_timeout");
});

test("terminal rows are release-reconciled but never rewritten", () => {
  const terminal = reconciliationDecision({
    ...base,
    status: "complete",
    completed_at: new Date(now - 60_000).toISOString(),
  }, now);
  assert.deepEqual(terminal, { action: "release", reason: "terminal_release_reconciliation" });
});

test("non-server-admitted legacy rows are never touched", () => {
  const decision = reconciliationDecision({ ...base, admission_access_id: "", status: "crawling", started_at: "2020-01-01T00:00:00Z" }, now);
  assert.deepEqual(decision, { action: "skip", reason: "not_server_admitted" });
});

test("duplicate query rows collapse to one durable scan", () => {
  assert.equal(uniqueRows([{ id: "a" }, { id: "a", status: "queued" }, { id: "b" }]).length, 2);
});

test("signed sweep is parameter-free and cannot crawl", () => {
  assert.match(control, /action === "sweep"/);
  assert.match(control, /reconcileDurableScans\(entities\)/);
  assert.match(workerJob, /build_control_envelope\("sweep", signing_key\)/);
  assert.match(worker, /@app\.post\("\/scan-reconcile"\)/);
  const route = worker.split('@app.post("/scan-reconcile")', 2)[1].split('@app.post("/scan-job-drain")', 1)[0];
  assert.doesNotMatch(route, /run_scan\(|run_review\(|complete_authority\(/);
  assert.match(route, /reconcile_stale_scans\(client\)/);
});
