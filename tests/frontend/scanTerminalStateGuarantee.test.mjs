// Regression coverage for the orphaned-ScanRun defect.
//
// A customer retry produced ScanRun 6a738ec426769e4b5789f15d: created, moved to
// "crawling" 255ms later, then never touched again -- zero pages, no error, no
// FixList, and a permanent "This scan is still running" screen. The scanner was
// never reached. Execution stopped in the browser between beginScanRun() and the
// gateway call, and the catch block returned without writing a terminal state.
//
// Two defects produced that row and both are covered here:
//   1. assertCurrentScanSession treated an empty browser pointer as proof that
//      the customer switched project, aborting a scan the server still owned.
//   2. The abandoned branch of handleSubmit returned bare, so the durable row
//      kept the non-terminal "crawling" status forever.
//
// ScanWebsiteForm.jsx cannot be imported under `node --test` (JSX plus "@/"
// aliases), so the session guard is rebuilt in an isolated scope and executed --
// which is what proves the pointer rule actually changed, rather than only
// asserting on source text.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  ACTIVE_SCAN_RUN_STATUSES,
  STANDARD_ACTIVE_SCAN_TTL_MS,
  STANDARD_ORPHAN_RECOVERY_TTL_MS,
  isStaleActiveScanRun,
} from "../../src/lib/scanRunIdentity.js";

const scanFormSource = readFileSync(
  new URL("../../src/components/scan/ScanWebsiteForm.jsx", import.meta.url),
  "utf8",
);
const scanRunsSource = readFileSync(
  new URL("../../src/lib/scanRuns.js", import.meta.url),
  "utf8",
);
const fixListSource = readFileSync(
  new URL("../../src/pages/FixList.jsx", import.meta.url),
  "utf8",
);
const dispatcherSource = readFileSync(new URL("../../base44/functions/startStandardScanJob/entry.ts", import.meta.url), "utf8");
const workerControlSource = readFileSync(new URL("../../base44/functions/durableScanWorkerControl/entry.ts", import.meta.url), "utf8");
const durablePersistenceSource = readFileSync(new URL("../../base44/functions/persistDurableScanAuthority/entry.ts", import.meta.url), "utf8");

// Rebuild assertCurrentScanSession in an isolated scope with injected doubles.
const guardMatch = scanFormSource.match(
  /async function assertCurrentScanSession\(identity, epoch, epochRef\) \{[\s\S]*?\n\}/,
);
assert.ok(guardMatch, "could not extract assertCurrentScanSession from ScanWebsiteForm.jsx");
const buildGuard = new Function(
  "base44",
  "readCustomerActiveProject",
  `${guardMatch[0]}\nreturn assertCurrentScanSession;`,
);

function guardWith({ currentUserId, storedProjectId }) {
  return buildGuard(
    { auth: { me: async () => ({ id: currentUserId }) } },
    () => storedProjectId,
  );
}

const IDENTITY = Object.freeze({ ownerId: "owner-1", projectId: "project-1" });

test("a missing active-project pointer never abandons a scan the server still owns", async () => {
  // Private-mode storage, an evicted key, and a boundary event that cleared
  // caches all read back as "". None of them prove a project switch.
  const guard = guardWith({ currentUserId: "owner-1", storedProjectId: "" });
  await guard(IDENTITY, 1, { current: 1 });
});

test("a pointer naming a different project still aborts the scan", async () => {
  const guard = guardWith({ currentUserId: "owner-1", storedProjectId: "project-2" });
  await assert.rejects(
    () => guard(IDENTITY, 1, { current: 1 }),
    (error) => error.code === "stale_customer_session",
  );
});

test("a changed signed-in owner still aborts the scan", async () => {
  const guard = guardWith({ currentUserId: "owner-2", storedProjectId: "project-1" });
  await assert.rejects(
    () => guard(IDENTITY, 1, { current: 1 }),
    (error) => error.code === "stale_customer_session",
  );
});

test("a superseded request epoch still aborts the scan", async () => {
  const guard = guardWith({ currentUserId: "owner-1", storedProjectId: "project-1" });
  await assert.rejects(
    () => guard(IDENTITY, 1, { current: 2 }),
    (error) => error.code === "stale_customer_session",
  );
});

test("an abandoned browser never overwrites server-owned terminal state", () => {
  const abandonedBranch = scanFormSource.match(
    /const abandoned = err\?\.code === "stale_customer_session"[\s\S]*?\n {6}\}/,
  );
  assert.ok(abandonedBranch, "the abandoned branch is missing from handleSubmit");
  assert.match(abandonedBranch[0], /durable_worker_owned: Boolean\(scanId\)/);
  assert.doesNotMatch(abandonedBranch[0], /cancelScanRun|failScanRun|ScanRun\.(?:create|update)/);
  assert.match(dispatcherSource, /failOwnedScanRun\(\{/);
  assert.match(workerControlSource, /status: "failed"/);
  assert.match(durablePersistenceSource, /persistedScan\?\.status === "complete"/);
});

test("cancelScanRun closes the row truthfully without fabricating evidence", () => {
  const cancel = scanRunsSource.match(/export async function cancelScanRun[\s\S]*?\n\}/);
  assert.ok(cancel, "cancelScanRun is missing from scanRuns.js");
  assert.match(cancel[0], /status: "cancelled"/);
  assert.match(cancel[0], /completed_at: new Date\(\)\.toISOString\(\)/);
  assert.match(cancel[0], /release_gate_eligible: false/);
  // No result, score, page count, or scanner identity may be invented.
  assert.doesNotMatch(cancel[0], /pages_crawled|health_score|scanner_version|authority_proof|fix_list_id/);
});

test("the browser never creates, updates, or consumes paid access", () => {
  assert.doesNotMatch(scanFormSource, /recordScanUsed|scans_used|Access\.create|Access\.update/);
});

test("orphan recovery closes abandoned runs well before the replay TTL", () => {
  assert.ok(
    STANDARD_ORPHAN_RECOVERY_TTL_MS < STANDARD_ACTIVE_SCAN_TTL_MS,
    "recovery must be faster than the conservative replay window",
  );
  // Recovery must never fail a live durable worker. The worker envelope is
  // 210s crawl + 60s review/persist = 270s, plus queue delivery and cold
  // start, so the threshold sits well above it.
  assert.ok(STANDARD_ORPHAN_RECOVERY_TTL_MS > 270_000);

  // More than 35 minutes after the last write: past the recovery threshold.
  const now = Date.parse("2026-08-05T20:10:30.000Z");
  const orphan = {
    status: "crawling",
    queued_at: "2026-08-05T19:28:04.195Z",
    started_at: "2026-08-05T19:28:04.441Z",
    updated_date: "2026-08-05T19:28:04.574000",
  };
  assert.equal(isStaleActiveScanRun(orphan, { now, activeTtlMs: STANDARD_ORPHAN_RECOVERY_TTL_MS }), true);

  // A scan that is genuinely still running in another tab must be left alone.
  // A durable worker mid-crawl writes nothing for minutes; it must survive.
  const live = { status: "crawling", queued_at: "2026-08-05T20:05:30.000Z", started_at: "2026-08-05T20:05:30.000Z" };
  assert.equal(isStaleActiveScanRun(live, { now, activeTtlMs: STANDARD_ORPHAN_RECOVERY_TTL_MS }), false);

  // Persisted evidence is never eligible for recovery.
  for (const status of ["complete", "limited", "failed", "cancelled"]) {
    assert.equal(ACTIVE_SCAN_RUN_STATUSES.has(status), false, `${status} must be terminal`);
  }
});

test("customer views never terminalize delayed scans", () => {
  // Queue/worker watchdogs own terminal recovery. Merely opening a customer
  // view must remain read-only even when a scan has been delayed for minutes.
  assert.doesNotMatch(scanFormSource, /recoverOrphanedScanRuns/);
  assert.doesNotMatch(fixListSource, /recoverOrphanedScanRuns|isStaleActiveScanRun|recoveryAttemptedForRef/);
  assert.match(fixListSource, /ACTIVE_SCAN_RUN_STATUSES\.has\(String\(durableBundle\.run\.status \|\| ""\)\)/);

  const recover = scanRunsSource.match(/export async function recoverOrphanedScanRuns[\s\S]*?\n\}/);
  assert.ok(recover, "recoverOrphanedScanRuns is missing from scanRuns.js");
  // The legacy helper remains threshold- and owner-scoped while callers move
  // to the server watchdog; no customer route invokes it.
  assert.match(recover[0], /await currentOwner\(\)/);
  assert.match(recover[0], /activeTtlMs: STANDARD_ORPHAN_RECOVERY_TTL_MS/);
});

test("boundary instrumentation records identity only around server admission and read-only recovery", () => {
  const logger = scanFormSource.match(/function logScanBoundary[\s\S]*?\n\}/);
  assert.ok(logger, "logScanBoundary is missing from ScanWebsiteForm.jsx");
  assert.doesNotMatch(logger[0], /attestation|proof|token|payload|api_key|secret/i);
  for (const boundary of [
    "async_job_submit",
    "async_job_accepted",
    "browser_recovered_saved_result",
    "async_job_browser_error_no_terminal_write",
    "scan_abandoned",
  ]) {
    assert.match(scanFormSource, new RegExp(`logScanBoundary\\("${boundary}"`), `missing boundary log: ${boundary}`);
  }
  assert.doesNotMatch(scanFormSource, /logScanBoundary\("scanner_function_start"|logScanBoundary\("review_function_start"|logScanBoundary\("persistence_start"/);
  assert.ok(scanFormSource.indexOf("assertServerAdmissionIdentity(jobData") < scanFormSource.indexOf('logScanBoundary("async_job_accepted"'));
});
