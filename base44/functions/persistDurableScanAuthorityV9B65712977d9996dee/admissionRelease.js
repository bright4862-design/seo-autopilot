import { RELEASE_COMPONENT_VERSIONS } from "./generatedReleaseContract.js";

const TERMINAL_STATUSES = new Set(["complete", "limited", "failed", "cancelled"]);
const RELEASE_OUTCOMES = new Set(["released", "already_released"]);
const SAFE_FAILURE_CODES = new Set([
  "admission_disabled",
  "admission_not_configured",
  "admission_sign_failed",
  "admission_unreachable",
  "coordinator_rejected",
  "coordinator_unavailable",
  "invalid_signature",
  "invalid_timestamp",
  "stale_request",
  "claim_not_found",
  "scan_not_bound",
  "scan_identity_conflict",
  "request_conflict",
  "admission_release_identity_conflict",
  "admission_release_scan_changed",
  "admission_release_persistence_failed",
]);

function text(value, limit = 160) {
  return typeof value === "string" ? value.trim().slice(0, limit) : "";
}

function code(value) {
  const normalized = text(value, 120).toLowerCase().replace(/[^a-z0-9_-]/g, "_");
  return SAFE_FAILURE_CODES.has(normalized) ? normalized : "admission_release_failed";
}

function attempt(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(1, Math.trunc(parsed)) : 1;
}

function nonNegativeInteger(value) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 0 ? parsed : null;
}

function terminalStatus(value) {
  const normalized = text(value, 30).toLowerCase();
  return TERMINAL_STATUSES.has(normalized) ? normalized : "";
}

export function releaseIdentity(scan = {}) {
  return {
    scan_id: text(scan?.id),
    owner_user_id: text(scan?.owner_user_id || scan?.created_by_id),
    request_id: text(scan?.request_id),
    idempotency_key: text(scan?.idempotency_key || scan?.request_id),
    attempt_count: attempt(scan?.attempt_count),
    barrier_generation: nonNegativeInteger(scan?.admission_barrier_generation),
    claim_sequence: nonNegativeInteger(scan?.admission_claim_sequence),
    status: terminalStatus(scan?.status),
  };
}

export function exactReleaseIdentity(scan, expected) {
  const current = releaseIdentity(scan);
  return Boolean(
    current.scan_id
    && current.owner_user_id
    && current.request_id
    && current.idempotency_key === current.request_id
    && current.scan_id === expected.scan_id
    && current.owner_user_id === expected.owner_user_id
    && current.request_id === expected.request_id
    && current.idempotency_key === expected.idempotency_key
    && current.attempt_count === expected.attempt_count
    && current.barrier_generation === expected.barrier_generation
    && current.claim_sequence === expected.claim_sequence
    && current.status === expected.status
  );
}

/**
 * Release one exact terminal coordinator generation and durably record it.
 *
 * The coordinator response must echo the request and scan identities that its
 * transaction released. A successful HTTP status without those identities is
 * intentionally retryable: it cannot prove which owner generation moved.
 */
export async function persistExactAdmissionRelease({
  entities,
  scan,
  terminalStatus: requestedStatus,
  release,
  now = () => new Date().toISOString(),
} = {}) {
  if (!text(scan?.admission_access_id)) return { ok: true, skipped: true, state: "not_server_admitted" };
  if (text(scan?.admission_release_state) === "released") {
    return { ok: true, replayed: true, state: "released" };
  }

  const expected = releaseIdentity(scan);
  const status = terminalStatus(requestedStatus || expected.status);
  if (
    !entities?.ScanRun
    || typeof entities.ScanRun.get !== "function"
    || typeof entities.ScanRun.update !== "function"
    || typeof release !== "function"
    || !expected.scan_id
    || !expected.owner_user_id
    || !expected.request_id
    || expected.idempotency_key !== expected.request_id
    || expected.barrier_generation === null
    || expected.claim_sequence === null
    || !status
    || status !== expected.status
  ) {
    return { ok: false, retryable: true, failureCode: "admission_release_identity_invalid" };
  }

  const attemptedAt = String(now());
  let result;
  try {
    result = await release({
      ownerUserId: expected.owner_user_id,
      scanId: expected.scan_id,
      terminalStatus: status,
    });
  } catch {
    result = { ok: false, outcomeUnknown: true, failureCode: "admission_unreachable" };
  }

  const outcome = text(result?.outcome, 80).toLowerCase();
  const coordinatorRequestId = text(result?.request_id);
  const coordinatorScanId = text(result?.scan_id);
  const coordinatorBarrierGeneration = nonNegativeInteger(result?.barrier_generation);
  const coordinatorClaimSequence = nonNegativeInteger(result?.claim_sequence);
  const exactCoordinatorGeneration = Boolean(
    result?.ok === true
    && RELEASE_OUTCOMES.has(outcome)
    && coordinatorRequestId === expected.request_id
    && coordinatorScanId === expected.scan_id
    && coordinatorBarrierGeneration === expected.barrier_generation
    && coordinatorClaimSequence === expected.claim_sequence
  );

  if (!exactCoordinatorGeneration) {
    await persistRetryableAttempt({
      entities,
      expected,
      attemptedAt,
      failureCode: result?.ok === true
        ? "admission_release_identity_conflict"
        : code(result?.failureCode),
      outcome,
    });
    return {
      ok: false,
      retryable: true,
      failureCode: result?.ok === true
        ? "admission_release_identity_conflict"
        : code(result?.failureCode),
      outcomeUnknown: result?.outcomeUnknown === true,
    };
  }

  const fresh = await entities.ScanRun.get(expected.scan_id).catch(() => null);
  if (!exactReleaseIdentity(fresh, expected)) {
    return { ok: false, retryable: true, failureCode: "admission_release_scan_changed" };
  }

  await entities.ScanRun.update(expected.scan_id, {
    admission_release_state: "released",
    admission_release_reconciled_at: attemptedAt,
    admission_release_last_attempt_at: attemptedAt,
    admission_release_coordinator_request_id: coordinatorRequestId,
    admission_release_outcome: outcome,
    admission_release_failure_code: "",
    admission_reconciliation_version: RELEASE_COMPONENT_VERSIONS.admission_reconciliation_version,
  });
  const persisted = await entities.ScanRun.get(expected.scan_id).catch(() => null);
  if (
    !exactReleaseIdentity(persisted, expected)
    || text(persisted?.admission_release_state) !== "released"
    || text(persisted?.admission_release_coordinator_request_id) !== expected.request_id
    || !RELEASE_OUTCOMES.has(text(persisted?.admission_release_outcome, 80))
  ) {
    return { ok: false, retryable: true, failureCode: "admission_release_persistence_failed" };
  }
  return { ok: true, state: "released", outcome, scanRun: persisted };
}

async function persistRetryableAttempt({ entities, expected, attemptedAt, failureCode, outcome }) {
  const fresh = await entities.ScanRun.get(expected.scan_id).catch(() => null);
  if (!exactReleaseIdentity(fresh, expected)) return false;
  if (["released", "superseded", "satisfied_unbound"].includes(text(fresh?.admission_release_state))) return true;
  await entities.ScanRun.update(expected.scan_id, {
    admission_release_state: "pending",
    admission_release_last_attempt_at: attemptedAt,
    admission_release_outcome: text(outcome, 80),
    admission_release_failure_code: code(failureCode),
    admission_reconciliation_version: RELEASE_COMPONENT_VERSIONS.admission_reconciliation_version,
  });
  return true;
}
