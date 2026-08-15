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

test("an abandoned scan leaves the durable row to the server", () => {
  const abandonedBranch = scanFormSource.match(
    /const abandoned = err\?\.code === "stale_customer_session"[\s\S]*?\n {6}\}/,
  );
  assert.ok(abandonedBranch, "the abandoned branch is missing from handleSubmit");

  // Inverted deliberately. Browser-side terminalization was the defect, not the
  // fix: it closed Pretto 6a7f68d74633a26189302346 after eight minutes only
  // because a tab happened to be open, while Funbooker 6a7f67bdee7f1e82ce6b418c
  // stayed "crawling" at 0/0 because none was. A durable row exists only after
  // the server has accepted the request, and from that moment the worker and
  // the watchdog own its outcome.
  assert.doesNotMatch(abandonedBranch[0], /cancelScanRun/);
  assert.match(abandonedBranch[0], /logScanBoundary\("scan_abandoned"/);
  assert.doesNotMatch(scanFormSource, /await failScanRun/);
  assert.doesNotMatch(scanFormSource, /await cancelScanRun/);
});

test("no browser code path can mutate a ScanRun", () => {
  // Every write helper still exported by scanRuns.js refuses before touching an
  // entity, so a stale bundle in a customer's browser cannot terminalize a row.
  for (const fn of [
    "cancelScanRun",
    "recoverOrphanedScanRuns",
    "beginScanRun",
    "markScanRunReviewing",
    "completeScanRun",
    "failScanRun",
  ]) {
    assert.match(
      scanRunsSource,
      new RegExp(`export async function ${fn}[\\s\\S]{0,400}?assertBrowserScanRunWritesDisabled\\("${fn}"\\)`),
      `${fn} must refuse before any entity write`,
    );
  }
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

test("boundary instrumentation records identity only, never evidence or secrets", () => {
  const logger = scanFormSource.match(/function logScanBoundary[\s\S]*?\n\}/);
  assert.ok(logger, "logScanBoundary is missing from ScanWebsiteForm.jsx");
  assert.doesNotMatch(logger[0], /attestation|proof|token|payload|api_key|secret/i);

  // Scanner, review and persistence boundaries moved to the server with the
  // work they instrumented. What the browser still owns is submission,
  // acceptance and abandonment.
  for (const boundary of [
    "async_job_submit",
    "async_job_accepted",
    "async_job_browser_error_no_terminal_write",
    "scan_abandoned",
  ]) {
    assert.match(scanFormSource, new RegExp(`logScanBoundary\\("${boundary}"`), `missing boundary log: ${boundary}`);
  }

  // Navigation now follows server acceptance, not a browser-side seal check:
  // the authority seal is written by persistDurableScanAuthority, and the
  // browser reads the sealed result back through the result route.
  const acceptIndex = scanFormSource.indexOf('logScanBoundary("async_job_accepted"');
  const navIndex = scanFormSource.indexOf("navigate(`/dashboard?scan_id=");
  assert.ok(acceptIndex > -1 && navIndex > acceptIndex, "navigation must follow server acceptance");
});
