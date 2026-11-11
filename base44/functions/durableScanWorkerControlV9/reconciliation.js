import { RELEASE_COMPONENT_VERSIONS } from "./generatedReleaseContract.js";

export const RECONCILE_QUEUED_AFTER_MS = 30 * 60 * 1000;
export const RECONCILE_STARTED_AFTER_MS = 35 * 60 * 1000;
// One Cloud Tasks delivery may run for 480s and the retry queue permits 300s
// backoff. Fifteen minutes spans both with headroom.
export const RECONCILE_HEARTBEAT_AFTER_MS = 15 * 60 * 1000;

export const RECONCILE_BATCH_LIMIT = 25;
export const RECONCILE_QUERY_PAGE_SIZE = 50;
export const RECONCILE_QUERY_PAGE_LIMIT = 8;
export const RECONCILE_COORDINATOR_CONCURRENCY = 2;
export const RECONCILE_COORDINATOR_TIMEOUT_MS = 5_000;
export const RECONCILE_GLOBAL_DEADLINE_MS = 25_000;

export const ADMISSION_RELEASE_PENDING = "pending";
export const ADMISSION_RELEASE_RELEASED = "released";
export const ADMISSION_RELEASE_SUPERSEDED = "superseded";
export const ADMISSION_RELEASE_SATISFIED_UNBOUND = "satisfied_unbound";
export const ADMISSION_RECONCILIATION_VERSION = RELEASE_COMPONENT_VERSIONS.admission_reconciliation_version;

const TERMINAL = new Set(["complete", "limited", "failed", "cancelled"]);
const SETTLED_RELEASE_STATES = new Set([
  ADMISSION_RELEASE_RELEASED,
  ADMISSION_RELEASE_SUPERSEDED,
  ADMISSION_RELEASE_SATISFIED_UNBOUND,
]);
const RELEASE_OUTCOMES = new Set(["released", "already_released"]);
const SATISFY_OUTCOMES = new Set(["satisfied_unbound", "already_satisfied_unbound"]);
const SAFE_RELEASE_FAILURE_CODES = new Set([
  "admission_release_failed",
  "admission_release_identity_invalid",
  "admission_release_identity_conflict",
  "admission_release_persistence_failed",
  "admission_release_scan_changed",
  "admission_status_unavailable",
  "admission_unreachable",
  "admission_disabled",
  "admission_not_configured",
  "admission_sign_failed",
  "coordinator_rejected",
  "coordinator_unavailable",
  "coordinator_generation_ambiguous",
  "coordinator_lease_state_ambiguous",
  "coordinator_state_ambiguous",
  "same_request_scan_identity_conflict",
  "scan_identity_conflict",
  "scan_not_bound",
  "barrier_generation_conflict",
  "admission_satisfy_unbound_unavailable",
  "admission_satisfy_identity_conflict",
  "admission_reconciliation_invalid",
]);

function text(value, limit = 180) {
  return typeof value === "string" ? value.trim().slice(0, limit) : "";
}

function code(value, fallback = "admission_release_failed") {
  const normalized = text(value, 120).toLowerCase();
  return SAFE_RELEASE_FAILURE_CODES.has(normalized) ? normalized : fallback;
}

function nonNegativeInteger(value) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 0 ? parsed : null;
}

function normalizeAttempt(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(1, Math.trunc(parsed)) : 1;
}

function timestampMs(value) {
  const parsed = Date.parse(text(value));
  return Number.isFinite(parsed) ? parsed : null;
}

function terminalStatus(value) {
  const status = text(value, 30).toLowerCase();
  return TERMINAL.has(status) ? status : "";
}

export function admissionReleaseIdentity(scan = {}) {
  return {
    scanId: text(scan?.id),
    ownerUserId: text(scan?.owner_user_id || scan?.created_by_id),
    requestId: text(scan?.request_id),
    idempotencyKey: text(scan?.idempotency_key || scan?.request_id),
    attemptCount: normalizeAttempt(scan?.attempt_count),
    barrierGeneration: nonNegativeInteger(scan?.admission_barrier_generation),
    claimSequence: nonNegativeInteger(scan?.admission_claim_sequence),
    terminalStatus: terminalStatus(scan?.status),
  };
}

function exactReleaseIdentity(scan, expected) {
  const current = admissionReleaseIdentity(scan);
  return Boolean(
    current.scanId
    && current.ownerUserId
    && current.requestId
    && current.idempotencyKey === current.requestId
    && current.scanId === expected.scanId
    && current.ownerUserId === expected.ownerUserId
    && current.requestId === expected.requestId
    && current.idempotencyKey === expected.idempotencyKey
    && current.attemptCount === expected.attemptCount
    && current.barrierGeneration === expected.barrierGeneration
    && current.claimSequence === expected.claimSequence
    && current.terminalStatus === expected.terminalStatus
  );
}

function hasAdmissionGeneration(scan) {
  const identity = admissionReleaseIdentity(scan);
  return Boolean(
    identity.scanId
    && identity.ownerUserId
    && identity.requestId
    && identity.idempotencyKey === identity.requestId
    && identity.barrierGeneration !== null
    && identity.claimSequence !== null
  );
}

export function reconciliationDecision(scan = {}, nowMs = Date.now()) {
  if (!hasAdmissionGeneration(scan)) {
    return { action: "skip", reason: "not_server_admitted" };
  }
  const now = Number(nowMs);
  if (!Number.isFinite(now)) return { action: "skip", reason: "invalid_now" };
  const status = text(scan?.status).toLowerCase();

  if (TERMINAL.has(status)) {
    if (SETTLED_RELEASE_STATES.has(text(scan?.admission_release_state))) {
      return { action: "skip", reason: "admission_release_satisfied" };
    }
    return { action: "release", reason: "terminal_release_reconciliation" };
  }

  if (status === "queued") {
    const queued = timestampMs(scan?.queued_at || scan?.created_date || scan?.created_at);
    if (queued === null) return { action: "skip", reason: "queued_timestamp_missing" };
    if (now - queued <= RECONCILE_QUEUED_AFTER_MS) return { action: "skip", reason: "queued_within_budget" };
    return {
      action: "fail",
      reason: "queued_timeout",
      error_code: "scan_queue_reconciliation_timeout",
      detail: "This scan stayed in the queue too long and was safely stopped. Please start a new scan.",
    };
  }

  if (status === "crawling" || status === "reviewing") {
    const started = timestampMs(scan?.started_at);
    if (started === null) {
      const queued = timestampMs(scan?.queued_at || scan?.created_date || scan?.created_at);
      if (queued === null || now - queued <= RECONCILE_STARTED_AFTER_MS) {
        return { action: "skip", reason: "start_timestamp_missing_within_budget" };
      }
      return {
        action: "fail",
        reason: "missing_start_timeout",
        error_code: "worker_reconciliation_timeout",
        detail: "This scan did not reach a verified worker start and was safely stopped. Please start a new scan.",
      };
    }
    if (now - started > RECONCILE_STARTED_AFTER_MS) {
      return {
        action: "fail",
        reason: "worker_timeout",
        error_code: "worker_reconciliation_timeout",
        detail: "This scan exceeded the durable worker recovery window and was safely stopped. Please start a new scan.",
      };
    }

    const heartbeat = timestampMs(scan?.worker_heartbeat_at);
    if (heartbeat !== null) {
      if (now - heartbeat > RECONCILE_HEARTBEAT_AFTER_MS) {
        return {
          action: "fail",
          reason: "worker_heartbeat_timeout",
          error_code: "worker_heartbeat_timeout",
          detail: "The scan worker stopped reporting progress and was safely stopped. Please start a new scan.",
        };
      }
      return { action: "skip", reason: "worker_heartbeat_within_budget" };
    }
    return { action: "skip", reason: "worker_within_budget" };
  }

  return { action: "skip", reason: "status_not_reconcilable" };
}

export function uniqueRows(rows = []) {
  return [...new Map(
    (Array.isArray(rows) ? rows : [])
      .filter((row) => row && text(row.id))
      .map((row) => [text(row.id), row]),
  ).values()];
}

function newerGeneration(current, expected) {
  const barrier = nonNegativeInteger(current?.barrier_generation);
  const sequence = nonNegativeInteger(current?.claim_sequence);
  if (barrier === null || sequence === null) return false;
  return barrier > expected.barrierGeneration
    || (barrier === expected.barrierGeneration && sequence > expected.claimSequence);
}

function exactCoordinatorGeneration(admission, expected) {
  return text(admission?.request_id) === expected.requestId
    && nonNegativeInteger(admission?.barrier_generation) === expected.barrierGeneration
    && nonNegativeInteger(admission?.claim_sequence) === expected.claimSequence;
}

/**
 * Decide from one fresh coordinator status. A different request is not newer
 * merely because its id differs; supersession requires monotonic generation
 * evidence greater than the ScanRun's persisted claim identity.
 */
export function coordinatorReleaseDecision(scan = {}, statusResult = {}) {
  const expected = admissionReleaseIdentity(scan);
  if (
    !expected.scanId || !expected.ownerUserId || !expected.requestId
    || expected.idempotencyKey !== expected.requestId
    || expected.barrierGeneration === null || expected.claimSequence === null
  ) {
    return { action: "retry", failureCode: "admission_release_identity_invalid" };
  }
  if (statusResult?.ok !== true) {
    return {
      action: "retry",
      failureCode: code(statusResult?.failureCode, "admission_status_unavailable"),
    };
  }
  const admission = statusResult?.admission;
  if (!admission || typeof admission !== "object") {
    return { action: "retry", failureCode: "coordinator_generation_ambiguous" };
  }

  if (!exactCoordinatorGeneration(admission, expected)) {
    if (text(admission?.request_id) !== expected.requestId && newerGeneration(admission, expected)) {
      return {
        action: "satisfy",
        reason: "newer_coordinator_generation",
        releaseState: ADMISSION_RELEASE_SUPERSEDED,
      };
    }
    return { action: "retry", failureCode: "coordinator_generation_ambiguous" };
  }

  const state = text(admission?.state, 40).toLowerCase();
  const coordinatorScanId = text(admission?.scan_id);
  if (state === "bound") {
    if (coordinatorScanId === expected.scanId) return { action: "release", reason: "exact_bound_scan" };
    return { action: "retry", failureCode: "same_request_scan_identity_conflict" };
  }
  if (state === "claimed" && !coordinatorScanId) {
    if (statusResult?.lease_active === true) return { action: "pending", reason: "exact_claim_still_active" };
    if (statusResult?.lease_active === false) return { action: "satisfy_unbound", reason: "exact_claim_inactive_unbound" };
    return { action: "retry", failureCode: "coordinator_lease_state_ambiguous" };
  }
  if (state === "released" && (!coordinatorScanId || coordinatorScanId === expected.scanId)) {
    return {
      action: "satisfy",
      reason: "exact_generation_already_released",
      releaseState: ADMISSION_RELEASE_RELEASED,
    };
  }
  return { action: "retry", failureCode: "coordinator_state_ambiguous" };
}

function exactReleaseResponse(result, expected) {
  return Boolean(
    result?.ok === true
    && RELEASE_OUTCOMES.has(text(result?.outcome, 80).toLowerCase())
    && text(result?.request_id) === expected.requestId
    && text(result?.scan_id) === expected.scanId
    && nonNegativeInteger(result?.barrier_generation) === expected.barrierGeneration
    && nonNegativeInteger(result?.claim_sequence) === expected.claimSequence
  );
}

function exactSatisfyResponse(result, expected) {
  return Boolean(
    result?.ok === true
    && SATISFY_OUTCOMES.has(text(result?.outcome, 80).toLowerCase())
    && text(result?.request_id) === expected.requestId
    && nonNegativeInteger(result?.barrier_generation) === expected.barrierGeneration
    && nonNegativeInteger(result?.claim_sequence) === expected.claimSequence
  );
}

async function persistReleaseState({ entities, expected, fields }) {
  const fresh = await entities.get(expected.scanId).catch(() => null);
  if (!exactReleaseIdentity(fresh, expected)) return false;
  if (SETTLED_RELEASE_STATES.has(text(fresh?.admission_release_state))) {
    return text(fresh?.admission_release_state) === text(fields?.admission_release_state);
  }
  await entities.update(expected.scanId, {
    ...fields,
    admission_reconciliation_version: ADMISSION_RECONCILIATION_VERSION,
  });
  const persisted = await entities.get(expected.scanId).catch(() => null);
  return exactReleaseIdentity(persisted, expected)
    && text(persisted?.admission_release_state) === text(fields?.admission_release_state)
    && text(persisted?.admission_reconciliation_version) === ADMISSION_RECONCILIATION_VERSION;
}

async function persistPending({ entities, expected, attemptedAt, failureCode, outcome = "" }) {
  const persisted = await persistReleaseState({
    entities,
    expected,
    fields: {
      admission_release_state: ADMISSION_RELEASE_PENDING,
      admission_release_last_attempt_at: attemptedAt,
      admission_release_outcome: text(outcome, 80),
      admission_release_failure_code: code(failureCode),
    },
  });
  return {
    ok: false,
    retryable: true,
    state: ADMISSION_RELEASE_PENDING,
    failureCode: code(failureCode),
    persisted,
  };
}

export async function releaseExactTerminalAdmission({
  entities,
  scan,
  releaseAdmission,
  now = () => new Date().toISOString(),
} = {}) {
  if (SETTLED_RELEASE_STATES.has(text(scan?.admission_release_state))) {
    return { ok: true, replayed: true, state: text(scan.admission_release_state) };
  }
  const expected = admissionReleaseIdentity(scan);
  const attemptedAt = String(now());
  if (
    !entities || typeof entities.get !== "function" || typeof entities.update !== "function"
    || typeof releaseAdmission !== "function"
    || !expected.scanId || !expected.ownerUserId || !expected.requestId
    || expected.idempotencyKey !== expected.requestId
    || expected.barrierGeneration === null || expected.claimSequence === null
    || !expected.terminalStatus
  ) {
    return { ok: false, retryable: true, state: ADMISSION_RELEASE_PENDING, failureCode: "admission_release_identity_invalid" };
  }

  let result;
  try {
    result = await releaseAdmission({
      ownerUserId: expected.ownerUserId,
      scanId: expected.scanId,
      terminalStatus: expected.terminalStatus,
      timeoutMs: RECONCILE_COORDINATOR_TIMEOUT_MS,
    });
  } catch {
    result = { ok: false, outcomeUnknown: true, failureCode: "admission_unreachable" };
  }
  if (!exactReleaseResponse(result, expected)) {
    return persistPending({
      entities,
      expected,
      attemptedAt,
      failureCode: result?.ok === true
        ? "admission_release_identity_conflict"
        : code(result?.failureCode),
      outcome: result?.outcome,
    });
  }

  const persisted = await persistReleaseState({
    entities,
    expected,
    fields: {
      admission_release_state: ADMISSION_RELEASE_RELEASED,
      admission_release_reconciled_at: attemptedAt,
      admission_release_last_attempt_at: attemptedAt,
      admission_release_coordinator_request_id: expected.requestId,
      admission_release_outcome: text(result.outcome, 80),
      admission_release_failure_code: "",
    },
  });
  return persisted
    ? { ok: true, retryable: false, state: ADMISSION_RELEASE_RELEASED, outcome: text(result.outcome, 80) }
    : { ok: false, retryable: true, state: ADMISSION_RELEASE_PENDING, failureCode: "admission_release_persistence_failed" };
}

async function persistSatisfaction({ entities, expected, state, reason, attemptedAt }) {
  const persisted = await persistReleaseState({
    entities,
    expected,
    fields: {
      admission_release_state: state,
      admission_release_reconciled_at: attemptedAt,
      admission_release_last_attempt_at: attemptedAt,
      admission_release_coordinator_request_id: expected.requestId,
      admission_release_outcome: reason,
      admission_release_failure_code: "",
    },
  });
  return persisted
    ? { ok: true, retryable: false, state, outcome: reason }
    : { ok: false, retryable: true, state: ADMISSION_RELEASE_PENDING, failureCode: "admission_release_persistence_failed" };
}

async function applyStatusDecision({
  decision,
  entities,
  scan,
  expected,
  releaseAdmission,
  satisfyUnboundAdmission,
  now,
}) {
  const attemptedAt = String(now());
  if (decision.action === "satisfy") {
    return persistSatisfaction({
      entities,
      expected,
      state: decision.releaseState,
      reason: decision.reason,
      attemptedAt,
    });
  }
  if (decision.action === "pending") {
    const persisted = await persistReleaseState({
      entities,
      expected,
      fields: {
        admission_release_state: ADMISSION_RELEASE_PENDING,
        admission_release_last_attempt_at: attemptedAt,
        admission_release_outcome: decision.reason,
        admission_release_failure_code: "",
      },
    });
    return { ok: persisted, retryable: false, pending: true, state: ADMISSION_RELEASE_PENDING, outcome: decision.reason };
  }
  if (decision.action === "satisfy_unbound") {
    if (typeof satisfyUnboundAdmission !== "function") {
      return persistPending({
        entities,
        expected,
        attemptedAt,
        failureCode: "admission_satisfy_unbound_unavailable",
      });
    }
    let result;
    try {
      result = await satisfyUnboundAdmission({
        ownerUserId: expected.ownerUserId,
        requestId: expected.requestId,
        barrierGeneration: expected.barrierGeneration,
        timeoutMs: RECONCILE_COORDINATOR_TIMEOUT_MS,
      });
    } catch {
      result = { ok: false, outcomeUnknown: true, failureCode: "admission_unreachable" };
    }
    if (!exactSatisfyResponse(result, expected)) {
      return persistPending({
        entities,
        expected,
        attemptedAt,
        failureCode: result?.ok === true
          ? "admission_satisfy_identity_conflict"
          : code(result?.failureCode),
        outcome: result?.outcome,
      });
    }
    return persistSatisfaction({
      entities,
      expected,
      state: ADMISSION_RELEASE_SATISFIED_UNBOUND,
      reason: text(result.outcome, 80),
      attemptedAt,
    });
  }
  if (decision.action === "release") {
    return releaseExactTerminalAdmission({ entities, scan, releaseAdmission, now });
  }
  return persistPending({
    entities,
    expected,
    attemptedAt,
    failureCode: decision.failureCode || "coordinator_state_ambiguous",
  });
}

export async function reconcileAdmissionReleaseCandidate({
  entities,
  scan,
  statusAdmission,
  releaseAdmission,
  satisfyUnboundAdmission,
  now = () => new Date().toISOString(),
} = {}) {
  const expected = admissionReleaseIdentity(scan);
  if (!entities || typeof statusAdmission !== "function") {
    return { ok: false, retryable: true, state: ADMISSION_RELEASE_PENDING, failureCode: "admission_reconciliation_invalid" };
  }
  let status;
  try {
    status = await statusAdmission({
      ownerUserId: expected.ownerUserId,
      timeoutMs: RECONCILE_COORDINATOR_TIMEOUT_MS,
    });
  } catch {
    status = { ok: false, outcomeUnknown: true, failureCode: "admission_unreachable" };
  }
  const decision = coordinatorReleaseDecision(scan, status);
  const outcome = await applyStatusDecision({
    decision,
    entities,
    scan,
    expected,
    releaseAdmission,
    satisfyUnboundAdmission,
    now,
  });
  if (decision.action !== "release" || outcome?.ok === true) return outcome;

  // A failed release can race the next accepted claim. Refresh status and only
  // close this row when the coordinator proves a strictly newer generation.
  let refreshed;
  try {
    refreshed = await statusAdmission({
      ownerUserId: expected.ownerUserId,
      timeoutMs: RECONCILE_COORDINATOR_TIMEOUT_MS,
    });
  } catch {
    refreshed = { ok: false, outcomeUnknown: true, failureCode: "admission_unreachable" };
  }
  const refreshedDecision = coordinatorReleaseDecision(scan, refreshed);
  return applyStatusDecision({
    decision: refreshedDecision,
    entities,
    scan,
    expected,
    releaseAdmission,
    satisfyUnboundAdmission,
    now,
  });
}

export function oldestAttemptFirst(rows = []) {
  return [...rows].sort((left, right) => {
    const leftAttempt = timestampMs(left?.admission_release_last_attempt_at) ?? Number.NEGATIVE_INFINITY;
    const rightAttempt = timestampMs(right?.admission_release_last_attempt_at) ?? Number.NEGATIVE_INFINITY;
    if (leftAttempt !== rightAttempt) return leftAttempt - rightAttempt;
    const leftCreated = timestampMs(left?.created_date || left?.queued_at) ?? 0;
    const rightCreated = timestampMs(right?.created_date || right?.queued_at) ?? 0;
    return leftCreated - rightCreated;
  });
}

export async function mapWithConcurrency(items, concurrency, worker, deadlineMs = Number.POSITIVE_INFINITY) {
  const source = [...items];
  const results = new Array(source.length);
  let cursor = 0;
  async function run() {
    while (cursor < source.length && Date.now() < deadlineMs) {
      const index = cursor;
      cursor += 1;
      results[index] = await worker(source[index], index);
    }
  }
  const count = Math.max(1, Math.min(Number(concurrency) || 1, source.length || 1));
  await Promise.all(Array.from({ length: count }, run));
  return { results, processed: cursor, deadlineReached: cursor < source.length };
}
