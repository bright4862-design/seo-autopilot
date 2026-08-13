// Retry-safety contract for the durable Cloud Tasks path (PR #114, B1/B2/B4).
//
// Cloud Tasks tombstones a task name after completion/deletion, so a retry that
// reused the attempt-1 name would be swallowed and attempt 2 would never run.
// Task identity is therefore bound to (scan_id, attempt_count), and the same
// attempt number is carried and verified through every hop so a task minted for
// an old attempt cannot crawl, fail, persist, charge, or finalise a newer one.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  normalizeAttemptCount,
  taskNameForScan,
} from "../../base44/functions/startStandardScanJob/cloudTasks.js";

const QUEUE = "projects/seo-autopilot-501517/locations/europe-west1/queues/standard150-scans";
const dispatcher = readFileSync(new URL("../../base44/functions/startStandardScanJob/entry.ts", import.meta.url), "utf8");
const control = readFileSync(new URL("../../base44/functions/durableScanWorkerControl/index.ts", import.meta.url), "utf8");
const persist = readFileSync(new URL("../../base44/functions/persistDurableScanAuthority/index.ts", import.meta.url), "utf8");
const workerMain = readFileSync(new URL("../../scanner-api/app/main.py", import.meta.url), "utf8");
const workerJob = readFileSync(new URL("../../scanner-api/app/scan_job.py", import.meta.url), "utf8");

// 1. attempt 1 and attempt 2 create different task names
test("attempt 1 and attempt 2 produce different task names", () => {
  const a1 = taskNameForScan(QUEUE, "6a748d5f9e8a27963ae678dc", 1);
  const a2 = taskNameForScan(QUEUE, "6a748d5f9e8a27963ae678dc", 2);
  assert.notEqual(a1, a2, "a retry must not collide with the tombstoned attempt-1 name");
  assert.equal(a1, `${QUEUE}/tasks/standard150-6a748d5f9e8a27963ae678dc-a1`);
  assert.equal(a2, `${QUEUE}/tasks/standard150-6a748d5f9e8a27963ae678dc-a2`);
});

test("the same scan and attempt stays idempotent", () => {
  assert.equal(taskNameForScan(QUEUE, "scan-1", 2), taskNameForScan(QUEUE, "scan-1", 2));
  // A missing attempt means attempt 1, never a distinct name.
  assert.equal(taskNameForScan(QUEUE, "scan-1"), taskNameForScan(QUEUE, "scan-1", 1));
  for (const bad of [null, undefined, "", "x", 0, -3, 1.7, NaN]) {
    assert.equal(normalizeAttemptCount(bad) >= 1, true, `attempt must stay 1-based: ${String(bad)}`);
  }
  assert.equal(normalizeAttemptCount(3.9), 3);
});

test("task names cannot be injected through scan id or attempt", () => {
  assert.equal(taskNameForScan(QUEUE, "../../evil", 1), `${QUEUE}/tasks/standard150-evil-a1`);
  assert.equal(taskNameForScan(QUEUE, "a/b?c=d", 2), `${QUEUE}/tasks/standard150-abcd-a2`);
});

// 2. an old attempt cannot mutate a newer ScanRun
test("attempt_count is bound end to end", () => {
  assert.match(dispatcher, /normalizeAttemptCount\(context\.scan\?\.attempt_count\)/);
  assert.match(dispatcher, /attemptCount,/);
  assert.match(dispatcher, /attempt_count: attemptCount,/);
  assert.match(workerMain, /attempt_count: int = 1/);
  assert.match(workerMain, /job_attempt = normalize_attempt\(payload\.attempt_count\)/);
  assert.match(workerJob, /"attempt_count": str\(current_attempt\(scan\)\)/);
  for (const source of [control, persist]) {
    assert.match(source, /attempt_count: normalizeAttempt\(source\.attempt_count\)/);
    assert.match(source, /claimedAttempt !== rowAttempt/);
    assert.match(source, /superseded_attempt/);
  }
});

test("a superseded task stops before crawling, failing or charging", () => {
  assert.match(workerMain, /if is_superseded_attempt\(scan, job_attempt\)/);
  const guard = workerMain.match(/if is_superseded_attempt\(scan, job_attempt\)[\s\S]*?\n {12}\}/);
  assert.ok(guard, "the superseded guard is missing");
  assert.match(guard[0], /"skipped": "superseded_attempt"/);
  // It must sit before the crawl, scoped to the /scan-job worker (the legacy
  // synchronous /scan endpoint also calls run_scan and must not be matched).
  const workerBody = workerMain.slice(workerMain.indexOf('async def scan_job('));
  assert.ok(workerBody.length > 0, "the scan_job endpoint is missing");
  assert.ok(
    workerBody.indexOf("is_superseded_attempt(scan, job_attempt)") < workerBody.indexOf("await run_scan("),
    "the superseded check must run before the crawl",
  );
  // Every failure write is attempt-bound.
  const callCount = (workerMain.match(/await write_terminal_failure\(/g) || []).length;
  const boundCount = (workerMain.match(/attempt_count=job_attempt/g) || []).length;
  assert.ok(callCount >= 3, `expected the failure call sites, found ${callCount}`);
  assert.equal(boundCount, callCount, "every failure write must bind the task's attempt");
  assert.match(workerJob, /if attempt_count is not None and is_superseded_attempt\(scan, attempt_count\)/);
});

// 3 + 4. same-attempt partial authority resumes; terminal authority immutable
test("same-attempt partial authority resumes, terminal outcomes stay immutable", () => {
  assert.match(persist, /authority_immutable/);
  assert.match(persist, /terminal_authority_rejected/);
  assert.match(persist, /scanStatus === "complete"/);
  assert.match(persist, /scan\.authority_proof === authorityProof && scan\.fix_list_id/);
  assert.match(persist, /normalizeAttempt\(scan\.authority_attempt_count \?\? rowAttempt\) !== claimedAttempt/);
  assert.ok((persist.match(/await assertAttemptStillActive\(/g) || []).length >= 2);
  assert.match(workerJob, /"already_sealed": True/);
  assert.match(workerJob, /if already_terminal\(fresh\) and has_authority_proof\(fresh\)/);
});

// 5. retries reconcile rows but never touch paid access
test("retries reconcile authority rows without touching paid access", () => {
  assert.match(persist, /upsertSingleFixList/);
  assert.match(persist, /reconcileFixItems/);
  assert.match(persist, /for \(const duplicate of rows\)/);
  assert.match(persist, /for \(const duplicate of items\.slice\(1\)\)/);
  assert.doesNotMatch(persist, /ensureAllowanceConsumed|entities\.Access|scans_used/);
  assert.ok(
    persist.indexOf("authority_persistence_incomplete") < persist.indexOf("await entities.ScanRun.update(identity.scan_id, scanRunFields)"),
    "the terminal write must follow complete authority verification",
  );
  assert.match(persist, /const \{ attempt_count: _stagedAttempt, \.\.\.scanRunFields \} = rows\.scanRun/);
  assert.doesNotMatch(persist, /ScanRun\.update\(identity\.scan_id, rows\.scanRun\)/);
});

// 6. no direct Cloud Run -> Base44 entity calls
test("the worker never touches Base44 entities directly", () => {
  assert.doesNotMatch(workerJob, /\/entities\//);
  assert.doesNotMatch(workerMain, /\/entities\//);
  // All persistence goes through the signed control/completion functions.
  assert.match(workerJob, /durableScanWorkerControl/);
  assert.match(workerJob, /persistDurableScanAuthority/);
  assert.doesNotMatch(workerJob, /"aiReviewScan"/);
  assert.doesNotMatch(workerJob, /"persistScanAuthority"/);
});

test("no temporary PR114 patch machinery remains", () => {
  assert.doesNotMatch(dispatcher, /pr114/i);
});
