const TERMINAL = new Set(["complete", "limited", "failed", "cancelled"]);
const RELEASED = new Set(["released", "already_released"]);
const SAFE_FAILURES = new Set([
  "admission_disabled",
  "admission_not_configured",
  "admission_sign_failed",
  "admission_unreachable",
  "coordinator_rejected",
  "coordinator_unavailable",
  "claim_not_found",
  "scan_not_bound",
  "scan_identity_conflict",
  "barrier_generation_conflict",
]);

function text(value, limit = 160) {
  return typeof value === "string" ? value.trim().slice(0, limit) : "";
}

function integer(value) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 0 ? parsed : null;
}

function attempt(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(1, Math.trunc(parsed)) : 1;
}

function failureCode(value) {
  const normalized = text(value, 120).toLowerCase();
  return SAFE_FAILURES.has(normalized) ? normalized : "admission_release_failed";
}

function identity(scan = {}) {
  const status = text(scan?.status, 30).toLowerCase();
  return {
    scanId: text(scan?.id),
    ownerUserId: text(scan?.owner_user_id || scan?.created_by_id),
    requestId: text(scan?.request_id),
    idempotencyKey: text(scan?.idempotency_key || scan?.request_id),
    attemptCount: attempt(scan?.attempt_count),
    barrierGeneration: integer(scan?.admission_barrier_generation),
    claimSequence: integer(scan?.admission_claim_sequence),
    status: TERMINAL.has(status) ? status : "",
  };
}

function exact(scan, expected) {
  const current = identity(scan);
  return Boolean(
    current.scanId === expected.scanId
    && current.ownerUserId === expected.ownerUserId
    && current.requestId === expected.requestId
    && current.idempotencyKey === expected.idempotencyKey
    && current.attemptCount === expected.attemptCount
    && current.barrierGeneration === expected.barrierGeneration
    && current.claimSequence === expected.claimSequence
    && current.status === expected.status
  );
}

async function persistPending(entities, expected, attemptedAt, code, outcome = "") {
  const fresh = await entities.ScanRun.get(expected.scanId).catch(() => null);
  if (!exact(fresh, expected)) return false;
  if (["released", "superseded", "satisfied_unbound"].includes(text(fresh?.admission_release_state))) return true;
  await entities.ScanRun.update(expected.scanId, {
    admission_release_state: "pending",
    admission_release_last_attempt_at: attemptedAt,
    admission_release_outcome: text(outcome, 80),
    admission_release_failure_code: failureCode(code),
  });
  return true;
}

/** Owner cancellation uses the same exact-generation fence as every worker terminal path. */
export async function persistExactRelease({ entities, scan, release, now = () => new Date().toISOString() } = {}) {
  if (!text(scan?.admission_access_id)) return { ok: true, skipped: true };
  if (["released", "superseded", "satisfied_unbound"].includes(text(scan?.admission_release_state))) {
    return { ok: true, replayed: true, state: text(scan.admission_release_state) };
  }
  const expected = identity(scan);
  if (
    !expected.scanId || !expected.ownerUserId || !expected.requestId
    || expected.idempotencyKey !== expected.requestId
    || expected.barrierGeneration === null || expected.claimSequence === null
    || !expected.status || typeof release !== "function"
  ) return { ok: false, retryable: true, failureCode: "admission_release_identity_invalid" };

  const attemptedAt = String(now());
  let result;
  try {
    result = await release({
      ownerUserId: expected.ownerUserId,
      scanId: expected.scanId,
      terminalStatus: expected.status,
    });
  } catch {
    result = { ok: false, outcomeUnknown: true, failureCode: "admission_unreachable" };
  }
  const outcome = text(result?.outcome, 80).toLowerCase();
  const exactResponse = Boolean(
    result?.ok === true && RELEASED.has(outcome)
    && text(result?.request_id) === expected.requestId
    && text(result?.scan_id) === expected.scanId
    && integer(result?.barrier_generation) === expected.barrierGeneration
    && integer(result?.claim_sequence) === expected.claimSequence
  );
  if (!exactResponse) {
    const code = result?.ok === true ? "admission_release_identity_conflict" : failureCode(result?.failureCode);
    await persistPending(entities, expected, attemptedAt, code, outcome);
    return { ok: false, retryable: true, failureCode: code };
  }

  const fresh = await entities.ScanRun.get(expected.scanId).catch(() => null);
  if (!exact(fresh, expected)) return { ok: false, retryable: true, failureCode: "admission_release_scan_changed" };
  await entities.ScanRun.update(expected.scanId, {
    admission_release_state: "released",
    admission_release_reconciled_at: attemptedAt,
    admission_release_last_attempt_at: attemptedAt,
    admission_release_coordinator_request_id: expected.requestId,
    admission_release_outcome: outcome,
    admission_release_failure_code: "",
  });
  const persisted = await entities.ScanRun.get(expected.scanId).catch(() => null);
  if (!exact(persisted, expected) || text(persisted?.admission_release_state) !== "released") {
    return { ok: false, retryable: true, failureCode: "admission_release_persistence_failed" };
  }
  return { ok: true, state: "released", scanRun: persisted };
}
