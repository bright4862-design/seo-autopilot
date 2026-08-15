export const MAX_BETA_CUSTOMERS = 25;
export const SCAN_ADMISSION_LEASE_MS = 20 * 60 * 1000;

const USER_ID_PATTERN = /^[A-Za-z0-9_-]{3,128}$/;
const REQUEST_ID_PATTERN = /^[A-Za-z0-9_-]{8,180}$/;
const TERMINAL_STATUSES = new Set(["complete", "limited", "failed", "cancelled"]);

export function betaScanAdmissionPolicy() {
  if (String(Deno.env.get("BETA_SCAN_ADMISSION_ENABLED") || "").trim().toLowerCase() !== "true") {
    return { ok: false, code: "scan_admission_paused", allowedUserIds: [] };
  }
  // Admission authority now lives in the Firestore coordinator, whose
  // transactions are documented as atomic with serializable isolation. The
  // previous gate required BASE44_ATOMIC_UPDATE_MANY_CONFIRMED because the
  // Access-row lease below depended on Base44 update atomicity that Base44
  // does not document. Nothing on the live path depends on that any more, so
  // the flag is neither read nor required -- what is required instead is that
  // the coordinator is actually configured. Missing configuration must pause
  // admission rather than silently fall back to the unproven path.
  if (!String(Deno.env.get("SCAN_ADMISSION_COORDINATOR_URL") || "").trim()) {
    return { ok: false, code: "scan_admission_coordinator_unconfigured", allowedUserIds: [] };
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

// ---------------------------------------------------------------------------
// LEGACY: Access-row admission lease. Retained for rollback inspection only.
//
// This path claimed admission with Access.updateMany() and treated
// "updated === 1" as a compare-and-set. Base44 documents updateMany's matched
// and updated counts but not transactional, compare-and-set or linearizable
// semantics, so that read cannot be relied on to elect exactly one winner
// across tabs. The Firestore coordinator replaced it.
//
// Both mutating helpers now refuse unless BETA_LEGACY_ACCESS_LEASE_ENABLED is
// explicitly "true", which no environment sets. decideScanLease is left
// callable because it is pure and its tests document the old semantics.
// ---------------------------------------------------------------------------

export function legacyAccessLeaseEnabled() {
  // Read defensively. These helpers are exercised by Node tests that document
  // the retired semantics, and Deno is not defined there. An unreadable
  // environment must leave the legacy path off, not crash.
  const value = globalThis.Deno?.env?.get?.("BETA_LEGACY_ACCESS_LEASE_ENABLED");
  return String(value || "").trim().toLowerCase() === "true";
}

export async function claimScanLease({ accessEntity, access, identity, nowMs = Date.now(), claimToken }) {
  if (!legacyAccessLeaseEnabled()) {
    return { action: "unavailable", code: "scan_admission_legacy_lease_disabled" };
  }
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
  if (!legacyAccessLeaseEnabled()) return false;
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
