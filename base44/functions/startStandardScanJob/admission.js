const REQUEST_ID_PATTERN = /^[A-Za-z0-9_-]{8,180}$/;
const TERMINAL_STATUSES = new Set(["complete", "limited", "failed", "cancelled"]);

/**
 * Whether the scan-admission subsystem is configured and open.
 *
 * This answers "is admission working?", never "may this person scan?".
 *
 * A static 25-entry BETA_COHORT_ALLOWED_USER_IDS allowlist used to decide who
 * could scan. That does not scale past a hand-managed cohort and it duplicated
 * a decision entitlement already owns: with 100+ members, a second list has to
 * be edited for every signup and silently locks out anyone missing from it.
 *
 * Entitlement is now the invitation. evaluatePaidAccess() in entitlement.js is
 * the single gate, and it already accepts exactly three grant sources --
 * stripe_checkout, owner_test and manual_grant -- each requiring an active
 * grant bound to the caller's own id and email. Access rows are admin-only for
 * create, update and delete, so a customer cannot grant themselves one.
 *
 * Concurrency is a separate axis and is enforced elsewhere: the Firestore
 * coordinator allows one active scan per owner, and the Cloud Tasks queue caps
 * how many scans execute at once across all owners. Neither is an identity
 * check, and neither belongs here.
 */
export function betaScanAdmissionPolicy() {
  if (String(Deno.env.get("BETA_SCAN_ADMISSION_ENABLED") || "").trim().toLowerCase() !== "true") {
    return { ok: false, code: "scan_admission_paused" };
  }
  const coordinatorUrl = String(Deno.env.get("SCAN_ADMISSION_COORDINATOR_URL") || "").trim();
  const signingKey = String(Deno.env.get("SCAN_EVIDENCE_SIGNING_KEY") || "");
  if (!coordinatorUrl || !signingKey) {
    return { ok: false, code: "scan_admission_configuration_invalid" };
  }
  return { ok: true, code: "" };
}

export function normalizeAdmissionIdentity(value = {}) {
  const requestId = String(value.request_id || value.idempotency_key || "").trim();
  const idempotencyKey = String(value.idempotency_key || requestId).trim();
  const fingerprint = String(value.request_fingerprint || "").trim();
  if (!REQUEST_ID_PATTERN.test(requestId)) {
    return { ok: false, code: "scan_request_id_invalid" };
  }
  if (requestId !== idempotencyKey) {
    return { ok: false, code: "scan_request_identity_conflict" };
  }
  if (!fingerprint || fingerprint.length > 512) {
    return { ok: false, code: "scan_request_fingerprint_invalid" };
  }
  return {
    ok: true,
    request_id: requestId,
    idempotency_key: idempotencyKey,
    request_fingerprint: fingerprint,
  };
}

export function scanIsTerminal(scan) {
  return TERMINAL_STATUSES.has(String(scan?.status || "").trim().toLowerCase());
}
