const REQUEST_ID_PATTERN = /^[A-Za-z0-9_-]{8,180}$/;
const TERMINAL_STATUSES = new Set(["complete", "limited", "failed", "cancelled"]);

export function scanIntakeEnabled(intakeValue) {
  return String(intakeValue || "") === "true";
}

export function betaScanAdmissionPolicy(intakeValue, admissionValue) {
  if (!scanIntakeEnabled(intakeValue)) {
    return { ok: false, code: "scan_intake_paused" };
  }
  if (String(admissionValue || "") !== "true") {
    return { ok: false, code: "scan_admission_paused" };
  }
  const coordinatorUrl = String(Deno.env.get("SCAN_ADMISSION_COORDINATOR_URL") || "").trim();
  const signingKey = String(Deno.env.get("SCAN_EVIDENCE_SIGNING_KEY") || "");
  if (!coordinatorUrl || !signingKey) {
    return { ok: false, code: "scan_admission_configuration_invalid" };
  }
  // Membership is entitlement-owned. An active owner-bound Access grant is the
  // invitation; scan admission must not maintain a second static user list.
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
