/**
 * Extended 500 SERVER-ONLY ScanRun creation contract (R4 candidate).
 *
 * Pure preparation, NOT a Base44 route, database writer, atomic CAS, Cloud
 * Tasks dispatch, entitlement purchase flow, or executable worker. Never call
 * from a customer page. A future isolated service must bind a persisted
 * exact-owner request receipt atomically BEFORE creating the ScanRun, prevent
 * duplicate creates under contention, and verify the row again before queueing.
 *
 * The first candidate supports full-root scans, robots respected, no override.
 * Focused scans and owner override require separately frozen ownership evidence.
 */
import { evaluateExtended500PaidAccess } from "./extended500EntitlementIssuer.js";

export const EXTENDED500_SCAN_MODE = "extended_500";
export const EXTENDED500_DRAFT_VERSION = "extended500_scanrun_draft_v1";
const SAFE_ID = /^[A-Za-z0-9_-]{1,128}$/;
const fail = (code) => ({ ok: false, code });
const safeId = (value) => typeof value === "string" && SAFE_ID.test(value);

function siteOrigin(projectUrl) {
  if (typeof projectUrl !== "string" || projectUrl.length > 2048) return "";
  try {
    const url = new URL(projectUrl);
    const host = url.hostname.toLowerCase().replace(/\.$/, "");
    if (!["http:", "https:"].includes(url.protocol)
        || url.username || url.password || url.port || url.search || url.hash
        || !host || host.length > 253
        || !/^[a-z0-9.-]+$/.test(host) || !host.includes(".")
        || host === "localhost" || host.endsWith(".localhost")
        || host.endsWith(".local") || host.endsWith(".internal")
        || host.endsWith(".test") || host.endsWith(".invalid")
        || host.endsWith(".example")
        || host.startsWith(".") || host.endsWith(".") || host.includes("..")
        || /^[0-9.]+$/.test(host) || host.includes("--.")
        || (url.pathname !== "/" && url.pathname !== "")
    ) return "";
    return `${url.protocol}//${host}/`;
  } catch {
    return "";
  }
}

/**
 * The caller MUST have loaded user, project and Access through service-role
 * authenticated reads. Only requestId is a user-stable correlation ID; it
 * never supplies entitlement, owner, URL, scope, robots or scan mode.
 */
export function buildExtended500QueuedScanDraft({
  user, project, accessRows, requestId, nowMs = Date.now(),
} = {}) {
  if (!user || !safeId(user.id) || !safeId(requestId) || !project
      || !safeId(project.id) || project.owner_user_id !== user.id)
    return fail("owned_project_and_request_required");
  const site = siteOrigin(project.website_url);
  if (!site) return fail("public_root_project_required");
  const paid = evaluateExtended500PaidAccess({ user, accessRows });
  if (!paid.ok) return fail(paid.reason || "extended500_paid_access_required");
  if (!Number.isSafeInteger(nowMs) || nowMs < 0 || nowMs > 8_640_000_000_000_000)
    return fail("invalid_server_time");
  const queuedAt = new Date(nowMs).toISOString();
  const normalizedDomain = new URL(site).hostname.replace(/^www\./, "");
  return {
    ok: true,
    draft_version: EXTENDED500_DRAFT_VERSION,
    record: {
      project_id: project.id,
      owner_user_id: user.id,
      website_url: site,
      submitted_url: site,
      normalized_domain: normalizedDomain,
      scan_mode: EXTENDED500_SCAN_MODE,
      status: "queued",
      scan_source: "extended500_private_candidate",
      request_id: requestId,
      idempotency_key: requestId,
      request_fingerprint: `${EXTENDED500_SCAN_MODE}|${site}|root|respect_robots_txt`,
      attempt_count: 1,
      queued_at: queuedAt,
      respect_robots_txt: true,
      owner_attested_robots_override: false,
      admission_access_id: paid.access.id,
      pages_found: 0,
      pages_crawled: 0,
      pages_retained: 0,
      release_gate_eligible: false,
      review_confidence_state: "not_reviewed",
    },
  };
}

/**
 * Read-only replay classification, NEVER a substitute for transactional create.
 *
 * Caller must query by owner AND request id using service role, then supply
 * ALL matches. A 0-row decision only says a future CAS is needed; it does
 * not authorize an unsafe ScanRun.create(). Terminal rows keep their receipt.
 */
export function classifyExtended500DraftReplay(draft, existingRows) {
  if (!draft || draft.ok !== true || !draft.record
      || !Array.isArray(existingRows)) return fail("replay_inputs_invalid");
  if (!existingRows.length) return { ok: true, decision: "requires_atomic_create" };
  if (existingRows.length !== 1) return fail("duplicate_request_receipts");
  const row = existingRows[0], expected = draft.record;
  if (!row || !safeId(row.id)
      || row.owner_user_id !== expected.owner_user_id
      || row.project_id !== expected.project_id
      || row.request_id !== expected.request_id
      || row.idempotency_key !== expected.idempotency_key
      || row.request_fingerprint !== expected.request_fingerprint
      || row.website_url !== expected.website_url
      || row.normalized_domain !== expected.normalized_domain
      || row.scan_mode !== EXTENDED500_SCAN_MODE
      || row.admission_access_id !== expected.admission_access_id
      || row.attempt_count !== 1
      || row.respect_robots_txt !== true
      || row.owner_attested_robots_override !== false
      || (row.path_prefix != null && row.path_prefix !== "")
      || !["queued", "crawling", "reviewing", "complete", "limited", "failed", "cancelled"].includes(row.status))
    return fail("extended500_request_replay_conflict");
  return {
    ok: true,
    decision: ["queued", "crawling", "reviewing"].includes(row.status)
      ? "matching_existing_scan" : "terminal_receipt_not_reusable",
    scan_id: row.id,
  };
}
