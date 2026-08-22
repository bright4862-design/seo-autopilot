import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  ADMISSION_RELEASE_PENDING,
  ADMISSION_RELEASE_RELEASED,
  ADMISSION_RELEASE_SATISFIED_UNBOUND,
  ADMISSION_RELEASE_SUPERSEDED,
  ADMISSION_RECONCILIATION_VERSION,
  RECONCILE_BATCH_LIMIT,
  RECONCILE_COORDINATOR_CONCURRENCY,
  RECONCILE_COORDINATOR_TIMEOUT_MS,
  RECONCILE_GLOBAL_DEADLINE_MS,
  RECONCILE_HEARTBEAT_AFTER_MS,
  RECONCILE_QUERY_PAGE_LIMIT,
  RECONCILE_QUERY_PAGE_SIZE,
  RECONCILE_QUEUED_AFTER_MS,
  RECONCILE_STARTED_AFTER_MS,
  coordinatorReleaseDecision,
  reconcileAdmissionReleaseCandidate,
  reconciliationDecision,
  releaseExactTerminalAdmission,
  oldestAttemptFirst,
  uniqueRows,
} from "../../base44/functions/durableScanWorkerControl/reconciliation.js";

const control = readFileSync("base44/functions/durableScanWorkerControl/index.ts", "utf8");
const worker = readFileSync("scanner-api/app/main.py", "utf8");
const workerJob = readFileSync("scanner-api/app/scan_job.py", "utf8");

const base = {
  id: "scan-1",
  admission_access_id: "access-1",
  owner_user_id: "owner-1",
  request_id: "request-a",
  idempotency_key: "request-a",
  admission_barrier_generation: 4,
  admission_claim_sequence: 23,
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

test("worker heartbeat closes vanished jobs without shortening the full retry envelope", () => {
  // One Cloud Tasks request may run for 480s and the production queue permits
  // up to 300s backoff. The heartbeat deadline must safely outlast both.
  assert.ok(RECONCILE_HEARTBEAT_AFTER_MS > (480 + 300) * 1000);
  assert.ok(RECONCILE_HEARTBEAT_AFTER_MS < RECONCILE_STARTED_AFTER_MS);
  const startedAt = new Date(now - 20 * 60 * 1000).toISOString();
  const staleHeartbeat = new Date(now - RECONCILE_HEARTBEAT_AFTER_MS - 1).toISOString();
  const stale = reconciliationDecision({
    ...base,
    status: "crawling",
    started_at: startedAt,
    worker_heartbeat_at: staleHeartbeat,
  }, now);
  assert.equal(stale.action, "fail");
  assert.equal(stale.error_code, "worker_heartbeat_timeout");

  const freshHeartbeat = new Date(now - RECONCILE_HEARTBEAT_AFTER_MS + 1).toISOString();
  const live = reconciliationDecision({
    ...base,
    status: "crawling",
    started_at: startedAt,
    worker_heartbeat_at: freshHeartbeat,
  }, now);
  assert.equal(live.action, "skip");
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
  const decision = reconciliationDecision({
    ...base,
    admission_access_id: "",
    admission_barrier_generation: undefined,
    admission_claim_sequence: undefined,
    status: "crawling",
    started_at: "2020-01-01T00:00:00Z",
  }, now);
  assert.deepEqual(decision, { action: "skip", reason: "not_server_admitted" });
});

test("duplicate query rows collapse to one durable scan", () => {
  assert.equal(uniqueRows([{ id: "a" }, { id: "a", status: "queued" }, { id: "b" }]).length, 2);
});

test("worker refreshes signed liveness at pickup and after the crawl handoff", () => {
  assert.match(control, /worker_heartbeat_at: heartbeatAt/);
  const heartbeatRefreshes = worker.match(/scan = await mark_scan_started\(client, scan\)/g) || [];
  assert.ok(heartbeatRefreshes.length >= 2, "worker must refresh liveness before and after the bounded crawl");
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

test("admission reconciliation has an explicit bounded execution contract", () => {
  assert.equal(RECONCILE_BATCH_LIMIT, 25);
  assert.equal(RECONCILE_COORDINATOR_CONCURRENCY, 2);
  assert.equal(RECONCILE_COORDINATOR_TIMEOUT_MS, 5_000);
  assert.equal(RECONCILE_GLOBAL_DEADLINE_MS, 25_000);
  assert.equal(RECONCILE_QUERY_PAGE_SIZE, 50);
  assert.equal(RECONCILE_QUERY_PAGE_LIMIT, 8);
  assert.match(ADMISSION_RECONCILIATION_VERSION, /^admission_reconciliation_v1_/);
});

test("legacy missing release markers are pending and rotate before retried rows", () => {
  const legacy = {
    ...base,
    id: "legacy-terminal",
    status: "complete",
    completed_at: "2026-01-01T00:00:00.000Z",
  };
  assert.deepEqual(
    reconciliationDecision(legacy, now),
    { action: "release", reason: "terminal_release_reconciliation" },
  );
  const ordered = oldestAttemptFirst([
    { ...legacy, id: "retried", admission_release_state: "pending", admission_release_last_attempt_at: "2026-08-21T00:00:00.000Z" },
    { ...legacy, id: "missing" },
    { ...legacy, id: "oldest", admission_release_state: "pending", admission_release_last_attempt_at: "2026-08-20T00:00:00.000Z" },
  ]);
  assert.deepEqual(ordered.map((row) => row.id), ["missing", "oldest", "retried"]);
});

const terminalPending = {
  ...base,
  owner_user_id: "owner-1",
  request_id: "request-a",
  idempotency_key: "request-a",
  status: "failed",
  attempt_count: 3,
  admission_barrier_generation: 4,
  admission_claim_sequence: 23,
  admission_release_state: ADMISSION_RELEASE_PENDING,
};

test("coordinator generation decisions never release a newer scan", () => {
  assert.deepEqual(
    coordinatorReleaseDecision(terminalPending, {
      ok: true,
      lease_active: true,
      admission: {
        state: "bound",
        request_id: "request-a",
        scan_id: terminalPending.id,
        barrier_generation: 4,
        claim_sequence: 23,
      },
    }),
    { action: "release", reason: "exact_bound_scan" },
  );

  assert.deepEqual(
    coordinatorReleaseDecision(terminalPending, {
      ok: true,
      lease_active: true,
      admission: {
        state: "bound",
        request_id: "request-b",
        scan_id: "scan-2",
        barrier_generation: 4,
        claim_sequence: 24,
      },
    }),
    {
      action: "satisfy",
      reason: "newer_coordinator_generation",
      releaseState: ADMISSION_RELEASE_SUPERSEDED,
    },
  );

  const conflict = coordinatorReleaseDecision(terminalPending, {
    ok: true,
    lease_active: true,
    admission: {
      state: "bound",
      request_id: "request-a",
      scan_id: "scan-2",
      barrier_generation: 4,
      claim_sequence: 23,
    },
  });
  assert.equal(conflict.action, "retry");
  assert.equal(conflict.failureCode, "same_request_scan_identity_conflict");
});

test("a merely different request is ambiguous without greater monotonic evidence", () => {
  for (const admission of [
    { state: "bound", request_id: "request-b", scan_id: "scan-2" },
    { state: "bound", request_id: "request-b", scan_id: "scan-2", barrier_generation: 4, claim_sequence: 23 },
    { state: "bound", request_id: "request-b", scan_id: "scan-2", barrier_generation: 3, claim_sequence: 22 },
  ]) {
    const decision = coordinatorReleaseDecision(terminalPending, {
      ok: true,
      lease_active: true,
      admission,
    });
    assert.equal(decision.action, "retry");
    assert.equal(decision.failureCode, "coordinator_generation_ambiguous");
  }
});

test("claimed-but-unbound rows settle only after the exact lease is inactive", () => {
  const active = coordinatorReleaseDecision(terminalPending, {
    ok: true,
    lease_active: true,
    admission: {
      state: "claimed",
      request_id: "request-a",
      scan_id: "",
      barrier_generation: 4,
      claim_sequence: 23,
    },
  });
  assert.deepEqual(active, { action: "pending", reason: "exact_claim_still_active" });

  const expired = coordinatorReleaseDecision(terminalPending, {
    ok: true,
    lease_active: false,
    admission: {
      state: "claimed",
      request_id: "request-a",
      scan_id: "",
      barrier_generation: 4,
      claim_sequence: 23,
    },
  });
  assert.deepEqual(expired, {
    action: "satisfy_unbound",
    reason: "exact_claim_inactive_unbound",
  });
});

function fakeScanEntities(initial) {
  let row = { ...initial };
  const writes = [];
  return {
    writes,
    current: () => ({ ...row }),
    ScanRun: {
      async get(id) {
        return id === row.id ? { ...row } : null;
      },
      async update(id, fields) {
        assert.equal(id, row.id);
        row = { ...row, ...fields };
        writes.push({ ...fields });
        return { ...row };
      },
    },
  };
}

test("normal terminal writers durably verify exact release and never clear provenance", async () => {
  const entities = fakeScanEntities(terminalPending);
  const calls = [];
  const outcome = await releaseExactTerminalAdmission({
    entities: entities.ScanRun,
    scan: terminalPending,
    releaseAdmission: async (payload) => {
      calls.push(payload);
      return {
        ok: true,
        outcome: "released",
        request_id: "request-a",
        scan_id: terminalPending.id,
        barrier_generation: 4,
        claim_sequence: 23,
      };
    },
    now: () => "2026-08-21T12:00:00.000Z",
  });

  assert.equal(outcome.state, ADMISSION_RELEASE_RELEASED);
  assert.deepEqual(calls, [{
    ownerUserId: "owner-1",
    scanId: terminalPending.id,
    terminalStatus: "failed",
    timeoutMs: RECONCILE_COORDINATOR_TIMEOUT_MS,
  }]);
  assert.equal(entities.current().admission_release_state, ADMISSION_RELEASE_RELEASED);
  assert.equal(entities.current().admission_access_id, "access-1");
  assert.equal(entities.current().admission_release_coordinator_request_id, "request-a");
  assert.equal(entities.current().admission_reconciliation_version, ADMISSION_RECONCILIATION_VERSION);
});

test("an HTTP success without exact coordinator echoes stays pending", async () => {
  const entities = fakeScanEntities(terminalPending);
  const outcome = await releaseExactTerminalAdmission({
    entities: entities.ScanRun,
    scan: terminalPending,
    releaseAdmission: async () => ({ ok: true, outcome: "released" }),
    now: () => "2026-08-21T12:00:00.000Z",
  });

  assert.equal(outcome.state, ADMISSION_RELEASE_PENDING);
  assert.equal(outcome.retryable, true);
  assert.equal(entities.current().admission_release_state, ADMISSION_RELEASE_PENDING);
  assert.equal(entities.current().admission_release_failure_code, "admission_release_identity_conflict");
});

test("reconciler refreshes status after a release race before suppressing the old row", async () => {
  const entities = fakeScanEntities(terminalPending);
  const statuses = [
    {
      ok: true,
      lease_active: true,
      admission: {
        state: "bound",
        request_id: "request-a",
        scan_id: terminalPending.id,
        barrier_generation: 4,
        claim_sequence: 23,
      },
    },
    {
      ok: true,
      lease_active: true,
      admission: {
        state: "bound",
        request_id: "request-b",
        scan_id: "scan-2",
        barrier_generation: 4,
        claim_sequence: 24,
      },
    },
  ];
  let statusReads = 0;
  const outcome = await reconcileAdmissionReleaseCandidate({
    entities: entities.ScanRun,
    scan: terminalPending,
    statusAdmission: async () => statuses[statusReads++],
    releaseAdmission: async () => ({ ok: false, failureCode: "scan_identity_conflict", outcomeUnknown: false }),
    satisfyUnboundAdmission: async () => assert.fail("bound release race must not satisfy an unbound claim"),
    now: () => "2026-08-21T12:00:00.000Z",
  });

  assert.equal(statusReads, 2);
  assert.equal(outcome.state, ADMISSION_RELEASE_SUPERSEDED);
  assert.equal(entities.current().admission_release_state, ADMISSION_RELEASE_SUPERSEDED);
});

test("expired exact unbound claims require an exact signed satisfaction echo", async () => {
  const entities = fakeScanEntities(terminalPending);
  const outcome = await reconcileAdmissionReleaseCandidate({
    entities: entities.ScanRun,
    scan: terminalPending,
    statusAdmission: async () => ({
      ok: true,
      lease_active: false,
      admission: {
        state: "claimed",
        request_id: "request-a",
        scan_id: "",
        barrier_generation: 4,
        claim_sequence: 23,
      },
    }),
    releaseAdmission: async () => assert.fail("unbound claims are never released by scan id"),
    satisfyUnboundAdmission: async (payload) => ({
      ok: true,
      outcome: "satisfied_unbound",
      request_id: payload.requestId,
      barrier_generation: payload.barrierGeneration,
      claim_sequence: 23,
    }),
    now: () => "2026-08-21T12:00:00.000Z",
  });

  assert.equal(outcome.state, ADMISSION_RELEASE_SATISFIED_UNBOUND);
  assert.equal(entities.current().admission_release_state, ADMISSION_RELEASE_SATISFIED_UNBOUND);
});

test("a coordinator outage remains durable pending regardless of terminal age", async () => {
  const old = {
    ...terminalPending,
    completed_at: "2026-01-01T00:00:00.000Z",
  };
  const entities = fakeScanEntities(old);
  const outcome = await reconcileAdmissionReleaseCandidate({
    entities: entities.ScanRun,
    scan: old,
    statusAdmission: async () => ({ ok: false, failureCode: "admission_unreachable", outcomeUnknown: true }),
    releaseAdmission: async () => assert.fail("release must not run without exact status"),
    now: () => "2026-08-21T12:00:00.000Z",
  });

  assert.equal(outcome.state, ADMISSION_RELEASE_PENDING);
  assert.equal(outcome.retryable, true);
  assert.equal(entities.current().admission_release_state, ADMISSION_RELEASE_PENDING);
  assert.equal(entities.current().admission_release_failure_code, "admission_unreachable");
});
