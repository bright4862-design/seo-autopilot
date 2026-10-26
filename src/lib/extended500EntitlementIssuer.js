// Isolated server-only Extended 500 entitlement issuer library. NOT routed,
// not imported by Standard 150 and not a customer-supplied access assertion.
// A future Base44 service-role endpoint must authenticate user and load these
// Access + ScanRun records from the server before calling this module.
import { createAuthoritySeal } from "../../base44/functions/persistDurableScanAuthority/authoritySeal.js";

export const EXTENDED500_ACCESS_PLAN_ID = "extended500_lifetime";
export const EXTENDED500_ACCESS_APP_ID = "6a498732ec779dfaaeab0e53";
export const EXTENDED500_ENTITLEMENT_VERSION = "extended500_paid_entitlement_v1";
export const EXTENDED500_PREFLIGHT_VERSION = "extended500_preflight_grant_v1";
export const EXTENDED500_PREFLIGHT_AUDIENCE = "fixlist_extended500_worker";
const STRICT_ID = /^[A-Za-z0-9_-]{1,128}$/;

function fail(reason) { return { ok: false, reason }; }
function id(value) { return typeof value === "string" && STRICT_ID.test(value); }
function domain(url) {
  try { return new URL(url).hostname.toLowerCase().replace(/^www\./, "").replace(/\.$/, ""); }
  catch { return ""; }
}
function paidAccessRecord(record, user) {
  if (!record || !user || !id(record.id) || !id(user.id)
      || record.owner_user_id !== user.id
      || String(record.user_email || "").trim().toLowerCase() !== String(user.email || "").trim().toLowerCase()
      || !String(user.email || "").trim()
      || record.app_id !== EXTENDED500_ACCESS_APP_ID
      || record.plan_id !== EXTENDED500_ACCESS_PLAN_ID
      || record.access_status !== "active" || record.has_full_access !== true
      || record.grant_source !== "stripe_checkout"
      || !id(record.stripe_checkout_session_id)
      || !Number.isFinite(Date.parse(String(record.paid_at || "")))) return false;
  return true;
}

export function evaluateExtended500Entitlement({ user, accessRows, scan }) {
  // No owner_test, manual_grant, checkout_pending, or Standard 150 preview.
  // Duplicated or conflicting access records fail closed, not first-match.
  // Other paid products may coexist. Only the independently issued 500-plan
  // rows count toward uniqueness, and any duplicate 500 grant is a conflict.
  const rows = (Array.isArray(accessRows) ? accessRows : [])
    .filter((row) => row?.plan_id === EXTENDED500_ACCESS_PLAN_ID);
  if (!user || !scan || !id(user.id) || !id(scan.id) || scan.owner_user_id !== user.id
      || scan.scan_mode !== "extended_500" || scan.status !== "queued"
      || !id(scan.project_id) || !id(scan.request_id) || !id(scan.idempotency_key)
      || !Number.isSafeInteger(scan.attempt_count) || scan.attempt_count < 1
      || !domain(scan.website_url)) return fail("scan_identity_invalid");
  if (rows.length !== 1 || !paidAccessRecord(rows[0], user)) return fail("extended500_paid_access_required");
  return { ok: true, access: rows[0] };
}

export async function mintExtended500AdmissionEvidence(
  { user, accessRows, scan, entitlementSigningKey, grantSigningKey, nowMs = Date.now() },
) {
  const allowed = evaluateExtended500Entitlement({ user, accessRows, scan });
  if (!allowed.ok) return allowed;
  if (typeof entitlementSigningKey !== "string" || entitlementSigningKey.length < 32
      || typeof grantSigningKey !== "string" || grantSigningKey.length < 32
      || entitlementSigningKey === grantSigningKey) return fail("signing_roots_unavailable");
  if (!Number.isSafeInteger(nowMs) || nowMs < 0) return fail("invalid_issue_time");

  const issuedAt = new Date(nowMs).toISOString();
  const expiresAt = new Date(nowMs + 120_000).toISOString();
  const access = allowed.access;
  const common = {
    owner_user_id: scan.owner_user_id,
    scan_id: scan.id, project_id: scan.project_id,
    request_id: scan.request_id, idempotency_key: scan.idempotency_key,
    attempt_count: scan.attempt_count,
  };
  const entitlement = {
    version: EXTENDED500_ENTITLEMENT_VERSION,
    plan_id: EXTENDED500_ACCESS_PLAN_ID,
    scan_mode: "extended_500", entitlement_state: "active_paid",
    ...common, access_id: access.id,
    issued_at: issuedAt, expires_at: expiresAt,
  };
  const robotsRespect = scan.respect_robots_txt;
  const robotsOverride = scan.owner_attested_robots_override;
  if (typeof robotsRespect !== "boolean" || typeof robotsOverride !== "boolean"
      || robotsOverride !== (robotsRespect === false)) return fail("frozen_robots_policy_invalid");
  const grant = {
    version: EXTENDED500_PREFLIGHT_VERSION,
    audience: EXTENDED500_PREFLIGHT_AUDIENCE,
    canonical_mode: "extended_500", ...common,
    website_url: scan.website_url,
    path_prefix: scan.path_prefix || null,
    respect_robots_txt: robotsRespect,
    owner_attested_robots_override: robotsOverride,
    issued_at: issuedAt, expires_at: expiresAt,
  };
  try {
    return {
      ok: true,
      entitlement: { ...entitlement, proof: await createAuthoritySeal(entitlement, entitlementSigningKey) },
      preflight_grant: { ...grant, proof: await createAuthoritySeal(grant, grantSigningKey) },
    };
  } catch {
    return fail("signing_failed");
  }
}
