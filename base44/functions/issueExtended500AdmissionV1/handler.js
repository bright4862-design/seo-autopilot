// Authenticated, independent Extended 500 admission boundary.
// NOT a Standard 150 handler, checkout grant, worker or customer 500 release.
// Dependencies are injected for deterministic security-contract tests.
import { mintExtended500AdmissionEvidence } from "./issuer.js";

const IDENTIFIER = /^[A-Za-z0-9_-]{1,128}$/;
const LABEL = "fixlist-extended500-atomic-admission-v1";
const encoder = new TextEncoder();

const failure = (code, status) => ({ status, payload: { success: false, admitted: false, code } });
const ident = (value) => typeof value === "string" && IDENTIFIER.test(value);
function normalizedHost(url) {
  try {
    const parsed = new URL(url);
    if (!["https:", "http:"].includes(parsed.protocol) || !parsed.hostname || parsed.username || parsed.password)
      return "";
    return parsed.hostname.toLowerCase().replace(/^www\./, "").replace(/\.$/, "");
  } catch {
    return "";
  }
}
function validCoordinatorOrigin(value) {
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase();
    if (url.protocol !== "https:" || !host || url.username || url.password
        || url.hash || url.search || !["", "/"].includes(url.pathname)
        || host === "localhost" || host.endsWith(".localhost")
        || /^(127\.|10\.|0\.|192\.168\.|169\.254\.)/.test(host))
      return "";
    return url.origin;
  } catch {
    return "";
  }
}
async function hmac(secretBytes, content) {
  const key = await crypto.subtle.importKey(
    "raw", secretBytes, { name: "HMAC", hash: "SHA-256" }, false, ["sign"],
  );
  return new Uint8Array(await crypto.subtle.sign(
    "HMAC", key, typeof content === "string" ? encoder.encode(content) : content,
  ));
}
export async function extended500CoordinatorSignature(root, stamp, payloadText) {
  const derived = await hmac(encoder.encode(root), LABEL);
  const signature = await hmac(derived, `${stamp}\n${payloadText}`);
  return Array.from(signature, (v) => v.toString(16).padStart(2, "0")).join("");
}

/** Authenticated caller and server-owned Base44 service entities are REQUIRED.
 *
 * No client-body entitlement, paid flag, owner id, mode, URL, request id or
 * grant may influence admission. The ONLY user-supplied field is scan_id.
 */
export async function issueExtended500Admission({
  body, user, entities, secret, fetchImpl = fetch, nowMs = Date.now(),
}) {
  if (!user || !ident(user.id) || typeof user.email !== "string" || !user.email.trim())
    return failure("unauthorized", 401);
  if (!body || typeof body !== "object" || Array.isArray(body)
      || Object.keys(body).length !== 1 || !ident(body.scan_id))
    return failure("invalid_scan_reference", 400);
  if (typeof secret !== "function")
    return failure("issuer_configuration_unavailable", 503);
  const enabled = String(secret("EXTENDED500_ISSUER_ENABLED") || "").trim();
  if (enabled !== "true") return failure("extended500_issuer_disabled", 503);

  const root = String(secret("EXTENDED500_COORDINATOR_SIGNING_KEY") || "");
  const entitlementKey = String(secret("EXTENDED500_ENTITLEMENT_SIGNING_KEY") || "");
  const grantKey = String(secret("EXTENDED500_ADMISSION_SIGNING_KEY") || "");
  const url = validCoordinatorOrigin(String(secret("EXTENDED500_COORDINATOR_URL") || ""));
  if (!url || [root, entitlementKey, grantKey].some((k) => k.length < 32)
      || new Set([root, entitlementKey, grantKey]).size !== 3)
    return failure("issuer_configuration_unavailable", 503);

  // Strict owner+project+ScanRun verification BEFORE fetching any access data
  // or minting a short-lived capability.
  let scan;
  try { scan = await entities.ScanRun.get(body.scan_id); }
  catch { return failure("scan_read_unavailable", 503); }
  if (!scan || scan.id !== body.scan_id || scan.owner_user_id !== user.id
      || scan.scan_mode !== "extended_500" || scan.status !== "queued"
      || !ident(scan.project_id) || !ident(scan.request_id)
      || !ident(scan.idempotency_key) || !Number.isSafeInteger(scan.attempt_count)
      || scan.attempt_count < 1) return failure("owned_extended500_scan_required", 403);

  let project;
  try { project = await entities.BusinessProject.get(scan.project_id); }
  catch { return failure("project_read_unavailable", 503); }
  const host = normalizedHost(scan.website_url);
  const projectHost = normalizedHost(project?.website_url);
  if (!project || project.id !== scan.project_id || project.owner_user_id !== user.id
      || !host || !projectHost || host !== projectHost
      || (scan.normalized_domain && host !== String(scan.normalized_domain).toLowerCase().replace(/^www\./, "").replace(/\.$/, "")))
    return failure("owned_project_domain_mismatch", 403);

  let byOwner, byEmail;
  try {
    [byOwner, byEmail] = await Promise.all([
      entities.Access.filter({ owner_user_id: user.id }),
      entities.Access.filter({ user_email: user.email }),
    ]);
  } catch { return failure("access_read_unavailable", 503); }
  if (!Array.isArray(byOwner) || !Array.isArray(byEmail))
    return failure("access_read_unavailable", 503);
  const rows = [...byOwner, ...byEmail];
  // Both filters can return the same record: remove that overlap only, never
  // combine genuinely independent paid Extended 500 records.
  if (rows.some((row) => !row || !ident(row.id)))
    return failure("access_identity_invalid", 409);
  const distinct = [...new Map(rows.map((row) => [row.id, row])).values()];
  // If two reads disagree about the SAME access id, fail closed.
  for (const row of rows) {
    const duplicate = distinct.find((v) => v.id === row.id);
    if (duplicate && JSON.stringify(duplicate) !== JSON.stringify(row))
      return failure("access_read_conflict", 409);
  }
  const evidence = await mintExtended500AdmissionEvidence({
    user, scan, accessRows: distinct,
    entitlementSigningKey: entitlementKey, grantSigningKey: grantKey, nowMs,
  });
  if (evidence.ok !== true)
    return failure(evidence.reason || "extended500_paid_access_required", 403);

  // Signed POST goes straight from Base44 to the separate Firestore service.
  // The browser never receives the grant or service signing keys.
  const payloadText = JSON.stringify({
    entitlement: evidence.entitlement,
    preflight_grant: evidence.preflight_grant,
  });
  const stamp = String(Math.floor(nowMs / 1000));
  let signature;
  try { signature = await extended500CoordinatorSignature(root, stamp, payloadText); }
  catch { return failure("issuer_signing_failed", 503); }
  let response;
  try {
    response = await fetchImpl(`${url}/reserve`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-fixlist-timestamp": stamp,
        "x-fixlist-signature": signature,
      },
      body: payloadText,
    });
  } catch {
    // The atomic reservation may already exist; caller can retry the SAME
    // ScanRun/request to recover using the coordinator's immutable receipt.
    return failure("reservation_outcome_unknown_retry_same_scan", 503);
  }

  let result = {};
  try { result = await response.json(); } catch { /* fail closed */ }
  if (![200, 202].includes(response.status) || result?.success !== true
      || result.reserved !== true || result.admitted !== false
      || result.worker_execution_enabled !== false
      || !["enqueued", "dispatch_unknown", "dispatch_disabled"].includes(result.state))
    return failure("reservation_not_confirmed", 503);
  return {
    status: response.status,
    payload: {
      success: true, scan_id: scan.id, scan_mode: "extended_500",
      reserved: true, admitted: false, worker_execution_enabled: false,
      dispatch_state: result.state, replayed: result.replayed === true,
    },
  };
}
