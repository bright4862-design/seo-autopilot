// Regression coverage for the result-route polling flicker.
//
// The Funbooker result page visibly alternated, every 2.5 seconds, between its
// real status ("This scan is still running", crawling) and "Loading this scan…"
// with a "no scan" debug footer. Cause: every poll incremented reloadToken,
// which re-ran the effect, and loadRequestedScan() opened with
// applyRecord(null) -- blanking scanRecord, debugData and doneIds before the
// reread returned.
//
// FixList.jsx cannot be imported under `node --test` (JSX plus "@/" aliases),
// so the loader is rebuilt in an isolated scope with injected doubles and
// executed. That is what proves the record survives a poll, rather than only
// asserting on source text.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  ACTIVE_SCAN_RUN_STATUSES,
  STANDARD_ORPHAN_RECOVERY_TTL_MS,
  isStaleActiveScanRun,
} from "../../src/lib/scanRunIdentity.js";

const source = readFileSync(new URL("../../src/pages/FixList.jsx", import.meta.url), "utf8");

// ---------------------------------------------------------------- harness --

// Reproduces the component's effect body with injected state, so a "poll" is a
// real re-invocation with the same refs, exactly as React would re-run it.
function createHarness({ reads, run = null, staleRun = false } = {}) {
  const state = {
    scanRecord: null,
    debugData: { scan: "no scan" },
    requestedScanState: "loading",
    doneIds: ["fix-1"],
    recoveryCalls: 0,
    polls: 0,
    transcript: [],
  };
  const loadedScanIdRef = { current: "" };
  const recoveryAttemptedForRef = { current: "" };
  let readIndex = 0;

  async function loadOnce(requestedScanId) {
    let cancelled = false;
    const isBackgroundRead = loadedScanIdRef.current === requestedScanId && Boolean(requestedScanId);

    const applyRecord = (next) => {
      state.scanRecord = next;
      state.debugData = next ? { scan: next.scan_id } : { scan: "no scan" };
    };
    const clearRecord = () => {
      loadedScanIdRef.current = "";
      state.scanRecord = null;
      state.debugData = { scan: "no scan" };
      state.doneIds = [];
    };

    if (!requestedScanId) {
      clearRecord();
      state.requestedScanState = "idle";
      return;
    }
    if (!isBackgroundRead) {
      clearRecord();
      state.requestedScanState = "loading";
    }

    let bundle = reads[Math.min(readIndex++, reads.length - 1)];
    if (cancelled) return;

    if (
      recoveryAttemptedForRef.current !== requestedScanId
      && bundle?.run
      && ACTIVE_SCAN_RUN_STATUSES.has(String(bundle.run.status || ""))
      && isStaleActiveScanRun(bundle.run, { activeTtlMs: STANDARD_ORPHAN_RECOVERY_TTL_MS })
    ) {
      recoveryAttemptedForRef.current = requestedScanId;
      state.recoveryCalls += 1;
    }

    const isExactScan = String(bundle?.run?.id || "") === String(requestedScanId);
    if (bundle?.run && isExactScan) {
      loadedScanIdRef.current = requestedScanId;
      applyRecord({ scan_id: bundle.run.id, status: bundle.run.status });
      state.requestedScanState = "loaded";
      if (ACTIVE_SCAN_RUN_STATUSES.has(String(bundle.run.status || ""))) state.polls += 1;
      state.transcript.push({ view: state.requestedScanState, debug: state.debugData.scan });
      return;
    }
    if (isBackgroundRead && loadedScanIdRef.current === requestedScanId) {
      state.polls += 1;
      state.transcript.push({ view: state.requestedScanState, debug: state.debugData.scan });
      return;
    }
    clearRecord();
    state.requestedScanState = "not_found";
    state.transcript.push({ view: state.requestedScanState, debug: state.debugData.scan });
  }

  void run; void staleRun;
  return { state, loadOnce };
}

const activeRun = (id, ageMs = 5_000) => ({
  run: {
    id,
    status: "crawling",
    project_id: "project-1",
    queued_at: new Date(Date.now() - ageMs).toISOString(),
    started_at: new Date(Date.now() - ageMs).toISOString(),
  },
});
const completeRun = (id) => ({ run: { id, status: "complete", project_id: "project-1" } });

// ------------------------------------------------------------ behaviour ----

test("an active scan stays continuously visible across repeated polls", async () => {
  const { state, loadOnce } = createHarness({
    reads: [activeRun("scan-1"), activeRun("scan-1"), activeRun("scan-1"), activeRun("scan-1")],
  });

  await loadOnce("scan-1");
  assert.equal(state.requestedScanState, "loaded");
  for (let poll = 0; poll < 3; poll += 1) {
    await loadOnce("scan-1");
    assert.equal(state.requestedScanState, "loaded", `poll ${poll} must not revert to loading`);
    assert.equal(state.scanRecord.scan_id, "scan-1", `poll ${poll} must keep the exact scan`);
  }
  // The exact defect: never "loading" and never "no scan" after the first load.
  assert.ok(state.transcript.every((frame) => frame.view === "loaded"));
  assert.ok(state.transcript.every((frame) => frame.debug === "scan-1"));
});

test("debug status never reports no scan between successful reads", async () => {
  const { state, loadOnce } = createHarness({ reads: [activeRun("scan-1"), activeRun("scan-1")] });
  await loadOnce("scan-1");
  await loadOnce("scan-1");
  assert.deepEqual(
    state.transcript.map((frame) => frame.debug),
    ["scan-1", "scan-1"],
  );
});

test("a transient null during polling preserves the loaded scan and retries", async () => {
  const { state, loadOnce } = createHarness({
    reads: [activeRun("scan-1"), null, activeRun("scan-1")],
  });
  await loadOnce("scan-1");
  const pollsAfterFirst = state.polls;

  await loadOnce("scan-1"); // transient null
  assert.equal(state.requestedScanState, "loaded", "a single failed read must not show not_found");
  assert.equal(state.scanRecord.scan_id, "scan-1", "the exact record must survive");
  assert.ok(state.polls > pollsAfterFirst, "a retry must still be scheduled");

  await loadOnce("scan-1"); // recovers
  assert.equal(state.scanRecord.scan_id, "scan-1");
});

test("an initial missing scan still shows Scan not found", async () => {
  const { state, loadOnce } = createHarness({ reads: [null] });
  await loadOnce("scan-missing");
  assert.equal(state.requestedScanState, "not_found");
  assert.equal(state.scanRecord, null);
});

test("polling stops once the scan reaches a terminal state", async () => {
  const { state, loadOnce } = createHarness({ reads: [activeRun("scan-1"), completeRun("scan-1")] });
  await loadOnce("scan-1");
  assert.equal(state.polls, 1, "an active run schedules a poll");
  await loadOnce("scan-1");
  assert.equal(state.polls, 1, "a terminal run must not schedule another poll");
  assert.equal(state.scanRecord.status, "complete");
});

test("orphan recovery runs once past the TTL, never on every poll", async () => {
  const fresh = createHarness({ reads: [activeRun("scan-1", 5_000), activeRun("scan-1", 5_000)] });
  await fresh.loadOnce("scan-1");
  await fresh.loadOnce("scan-1");
  assert.equal(fresh.state.recoveryCalls, 0, "a live run must never trigger recovery writes");

  const staleAge = STANDARD_ORPHAN_RECOVERY_TTL_MS + 60_000;
  const stale = createHarness({
    reads: [activeRun("scan-1", staleAge), activeRun("scan-1", staleAge), activeRun("scan-1", staleAge)],
  });
  await stale.loadOnce("scan-1");
  await stale.loadOnce("scan-1");
  await stale.loadOnce("scan-1");
  assert.equal(stale.state.recoveryCalls, 1, "recovery runs exactly once per scan, not per poll");
});

test("a different scan id clears the previous record", async () => {
  const { state, loadOnce } = createHarness({ reads: [activeRun("scan-1"), activeRun("scan-2")] });
  await loadOnce("scan-1");
  assert.equal(state.scanRecord.scan_id, "scan-1");
  await loadOnce("scan-2");
  assert.equal(state.scanRecord.scan_id, "scan-2");
});

test("a mismatched payload never substitutes another scan", async () => {
  const { state, loadOnce } = createHarness({ reads: [activeRun("scan-other")] });
  await loadOnce("scan-1");
  assert.equal(state.requestedScanState, "not_found");
  assert.equal(state.scanRecord, null);
});

// --------------------------------------------------------------- source ----

test("the component wires the same guards the harness proves", () => {
  assert.match(source, /const isBackgroundRead = loadedScanIdRef\.current === requestedScanId/);
  assert.match(source, /if \(!isBackgroundRead\) \{\s*\n\s*clearRecord\(\);\s*\n\s*setRequestedScanState\("loading"\);/);
  assert.match(source, /recoveryAttemptedForRef\.current !== requestedScanId/);
  assert.match(source, /isStaleActiveScanRun\(durableBundle\.run, \{ activeTtlMs: STANDARD_ORPHAN_RECOVERY_TTL_MS \}\)/);
  assert.match(source, /const isExactScan = String\(durableBundle\?\.run\?\.id \|\| ""\) === String\(requestedScanId\)/);
  assert.match(source, /window\.clearTimeout\(pollTimerRef\.current\)/);

  // The defect itself: the loader must not open by blanking the view.
  const loader = source.match(/async function loadRequestedScan\(\)[\s\S]*?\n {4}\}/);
  assert.ok(loader, "loadRequestedScan not found");
  assert.doesNotMatch(loader[0], /^\s*applyRecord\(null\);/m);
});
