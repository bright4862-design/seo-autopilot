export const MAX_BETA_CUSTOMERS = 25;
export const SCAN_ADMISSION_LEASE_MS = 20 * 60 * 1000;

const USER_ID_PATTERN = /^[A-Za-z0-9_-]{3,128}$/;
const REQUEST_ID_PATTERN = /^[A-Za-z0-9_-]{8,180}$/;
const TERMINAL_STATUSES = new Set(["complete", "limited", "failed", "cancelled"]);

export function betaScanAdmissionPolicy() {
  if (String(Deno.env.get("BETA_SCAN_ADMISSION_ENABLED") || "").trim().toLowerCase() !== "true") {
    return { ok: false, code: "scan_admission_paused", allowedUserIds: [] };
  }
  if (String(Deno.env.get("BASE44_ATOMIC_UPDATE_MANY_CONFIRMED") || "").trim().toLowerCase() !== "true") {
    return { ok: false, code: "scan_atomic_admission_unconfirmed", allowedUserIds: [] };
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
  if (!fingerprint || fingerprint.length > 2_000) {
    return { ok: false, code: "scan_request_fingerprint_invalid" };
  }
  return {
    ok: true,
    request_id: requestId,
    idempotency_key: idempotencyKey,
    request_fingerprint: fingerprint,
  };
}

function leaseExpiryMs(access) {
  const parsed = Date.parse(String(access?.scan_claim_expires_at || ""));
  return Number.isFinite(parsed) ? parsed : 0;
}

export function decideScanLease(access, identity, nowMs = Date.now()) {
  const normalized = normalizeAdmissionIdentity(identity);
  if (!normalized.ok) return { action: "invalid", code: normalized.code };

  const token = String(access?.scan_claim_token || "").trim();
  const claimedRequestId = String(access?.scan_claim_request_id || "").trim();
  const claimedFingerprint = String(access?.scan_claim_fingerprint || "").trim();
  const scanId = String(access?.scan_claim_scan_id || "").trim();
  const expired = !token || leaseExpiryMs(access) <= Number(nowMs);
  if (expired) return { action: "claim", previousToken: token };

  if (claimedRequestId === normalized.request_id) {
    if (claimedFingerprint !== normalized.request_fingerprint) {
      return { action: "conflict", code: "scan_request_identity_conflict" };
    }
    if (scanId) return { action: "reuse", scan_id: scanId, claim_token: token };
    return { action: "pending", retry_after: 2, claim_token: token };
  }
  return {
    action: "busy",
    retry_after: Math.max(1, Math.ceil((leaseExpiryMs(access) - Number(nowMs)) / 1000)),
  };
}

function blankOrMissing(field) {
  return { $or: [{ [field]: "" }, { [field]: { $exists: false } }] };
}

function updatedExactlyOne(result) {
  return result?.success === true && Number(result?.updated) === 1;
}

export async function claimScanLease({ accessEntity, access, identity, nowMs = Date.now(), claimToken }) {
  const initial = decideScanLease(access, identity, nowMs);
  if (initial.action !== "claim") return initial;

  const token = String(claimToken || crypto.randomUUID?.() || "").trim();
  if (!token) return { action: "unavailable", code: "scan_claim_token_unavailable" };
  const expiresAt = new Date(Number(nowMs) + SCAN_ADMISSION_LEASE_MS).toISOString();
  const priorToken = String(initial.previousToken || "").trim();
  const query = priorToken
    ? { id: String(access.id), scan_claim_token: priorToken }
    : { id: String(access.id), ...blankOrMissing("scan_claim_token") };
  const result = await accessEntity.updateMany(query, {
    $set: {
      scan_claim_token: token,
      scan_claim_request_id: identity.request_id,
      scan_claim_fingerprint: identity.request_fingerprint,
      scan_claim_scan_id: "",
      scan_claim_expires_at: expiresAt,
    },
  });
  if (updatedExactlyOne(result)) {
    return { action: "leader", claim_token: token, expires_at: expiresAt };
  }

  const current = await accessEntity.get(String(access.id)).catch(() => null);
  if (!current) return { action: "unavailable", code: "scan_admission_state_unavailable" };
  return decideScanLease(current, identity, nowMs);
}

export async function bindScanLease({ accessEntity, accessId, claimToken, scanId }) {
  const result = await accessEntity.updateMany(
    {
      id: String(accessId),
      scan_claim_token: String(claimToken),
      ...blankOrMissing("scan_claim_scan_id"),
    },
    { $set: { scan_claim_scan_id: String(scanId) } },
  );
  return updatedExactlyOne(result);
}

export function scanIsTerminal(scan) {
  return TERMINAL_STATUSES.has(String(scan?.status || "").trim().toLowerCase());
}
