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

test("an abandoned scan writes a terminal state instead of returning bare", () => {
  const abandonedBranch = scanFormSource.match(
    /const abandoned = err\?\.code === "stale_customer_session"[\s\S]*?\n {6}\}/,
  );
  assert.ok(abandonedBranch, "the abandoned branch is missing from handleSubmit");
  // The exact defect: `return` reached without a durable terminal write.
  assert.match(abandonedBranch[0], /cancelScanRun\(scanRunHandle, err\)/);
  assert.ok(
    abandonedBranch[0].indexOf("cancelScanRun") < abandonedBranch[0].indexOf("return;"),
    "cancelScanRun must run before the abandoned branch returns",
  );
  // The pre-existing failure path must still terminalize too.
  assert.match(scanFormSource, /const failure = await failScanRun\(scanRunHandle, err\)/);
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

  // Ten minutes after the last write: past the recovery threshold.
  const now = Date.parse("2026-08-05T19:38:30.000Z");
  const orphan = {
    status: "crawling",
    queued_at: "2026-08-05T19:28:04.195Z",
    started_at: "2026-08-05T19:28:04.441Z",
    updated_date: "2026-08-05T19:28:04.574000",
  };
  assert.equal(isStaleActiveScanRun(orphan, { now, activeTtlMs: STANDARD_ORPHAN_RECOVERY_TTL_MS }), true);

  // A scan that is genuinely still running in another tab must be left alone.
  // A durable worker mid-crawl writes nothing for minutes; it must survive.
  const live = { status: "crawling", queued_at: "2026-08-05T19:34:30.000Z", started_at: "2026-08-05T19:34:30.000Z" };
  assert.equal(isStaleActiveScanRun(live, { now, activeTtlMs: STANDARD_ORPHAN_RECOVERY_TTL_MS }), false);

  // Persisted evidence is never eligible for recovery.
  for (const status of ["complete", "limited", "failed", "cancelled"]) {
    assert.equal(ACTIVE_SCAN_RUN_STATUSES.has(status), false, `${status} must be terminal`);
  }
});

test("recovery runs on view only after the orphan TTL", () => {
  // The scan form recovers on mount.
  assert.match(scanFormSource, /recoverOrphanedScanRuns\(\{ projectId: project\?\.id \|\| "" \}\)/);
  // The result route keeps a live scan visible, and only attempts recovery once
  // the exact active row is genuinely stale.
  assert.match(fixListSource, /recoveryAttemptedForRef\.current !== requestedScanId/);
  assert.match(fixListSource, /ACTIVE_SCAN_RUN_STATUSES\.has\(String\(durableBundle\.run\.status \|\| ""\)\)/);
  assert.match(fixListSource, /isStaleActiveScanRun\(durableBundle\.run, \{ activeTtlMs: STANDARD_ORPHAN_RECOVERY_TTL_MS \}\)/);
  assert.match(fixListSource, /await recoverOrphanedScanRuns\(\{ projectId: durableBundle\.run\.project_id \|\| "" \}\)/);
  assert.match(fixListSource, /durableBundle = await getScanRunWithFixList\(requestedScanId\) \|\| durableBundle/);

  const recover = scanRunsSource.match(/export async function recoverOrphanedScanRuns[\s\S]*?\n\}/);
  assert.ok(recover, "recoverOrphanedScanRuns is missing from scanRuns.js");
  // Recovery is owner-scoped and threshold-gated.
  assert.match(recover[0], /await currentOwner\(\)/);
  assert.match(recover[0], /activeTtlMs: STANDARD_ORPHAN_RECOVERY_TTL_MS/);
});

test("boundary instrumentation records identity only, never evidence or secrets", () => {
  const logger = scanFormSource.match(/function logScanBoundary[\s\S]*?\n\}/);
  assert.ok(logger, "logScanBoundary is missing from ScanWebsiteForm.jsx");
  assert.doesNotMatch(logger[0], /attestation|proof|token|payload|api_key|secret/i);

  for (const boundary of [
    "scanner_function_start",
    "scanner_function_response",
    "review_function_start",
    "review_function_response",
    "persistence_start",
    "persistence_response",
    "browser_navigation",
    "scan_abandoned",
  ]) {
    assert.match(scanFormSource, new RegExp(`logScanBoundary\\("${boundary}"`), `missing boundary log: ${boundary}`);
  }

  // Navigation to the result route may only happen after a durable terminal result.
  const navIndex = scanFormSource.indexOf('logScanBoundary("browser_navigation"');
  const sealIndex = scanFormSource.indexOf("scan_authority_persistence_failed");
  assert.ok(navIndex > sealIndex, "navigation must follow the durable authority seal check");
});
