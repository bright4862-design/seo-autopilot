export const MAX_BETA_CUSTOMERS = 25;

const USER_ID_PATTERN = /^[A-Za-z0-9_-]{3,128}$/;
const REQUEST_ID_PATTERN = /^[A-Za-z0-9_-]{8,180}$/;
const TERMINAL_STATUSES = new Set(["complete", "limited", "failed", "cancelled"]);

export function betaScanAdmissionPolicy() {
  if (String(Deno.env.get("BETA_SCAN_ADMISSION_ENABLED") || "").trim().toLowerCase() !== "true") {
    return { ok: false, code: "scan_admission_paused", allowedUserIds: [] };
  }
  const coordinatorUrl = String(Deno.env.get("SCAN_ADMISSION_COORDINATOR_URL") || "").trim();
  const signingKey = String(Deno.env.get("SCAN_EVIDENCE_SIGNING_KEY") || "");
  if (!coordinatorUrl || !signingKey) {
    return { ok: false, code: "scan_admission_configuration_invalid", allowedUserIds: [] };
  }
  const allowedUserIds = Array.from(new Set(
    String(Deno.env.get("BETA_COHORT_ALLOWED_USER_IDS") || "")
      .split(/[\s,]+/)
      .map((value) => value.trim())
      .filter(Boolean),
  ));
  if (
    allowedUserIds.length < 1
    || allowedUserIds.length > MAX_BETA_CUSTOMERS
    || allowedUserIds.some((userId) => !USER_ID_PATTERN.test(userId))
  ) {
    return { ok: false, code: "scan_admission_configuration_invalid", allowedUserIds: [] };
  }
  return { ok: true, code: "", allowedUserIds };
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
