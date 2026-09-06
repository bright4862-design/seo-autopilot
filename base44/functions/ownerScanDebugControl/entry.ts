// Platform entry point. Base44 deploys base44/functions/{name}/entry.ts only,
// so the handler lives here rather than in an imported module: an import can be
// served from a stale compiled worker, and this file's bytes cannot.
import { createClientFromRequest } from "npm:@base44/sdk@0.8.41";
import { RELEASE_COMPONENT_VERSIONS, RELEASE_FINGERPRINT } from "./generatedReleaseContract.js";
import { FUNCTION_BUILD_ID } from "./generatedBuildId.js";
import { persistExactRelease } from "./admissionRelease.js";

// This literal is intentionally release-sensitive. Base44 has previously reused
// a compiled worker when the routed module stayed byte-identical while an
// imported module changed, so a release that moved only
// generatedReleaseContract.js could leave a stale handler serving. Carrying the
// active fingerprint here guarantees every fingerprint move changes the bytes
// Base44 recompiles. scripts/generate_release_contracts.mjs maintains it.
const BASE44_HANDLER_RELEASE_FINGERPRINT = "053180f4bdc70857";
const BASE44_RUNTIME_ACTIVATION_ID = "owner-debug-sandbox-activation-20260903-v1";

const OWNER_EMAIL = "bright4862@gmail.com";
const OWNER_USER_ID = "6a498da58ef5cec1f5cd4486";
const ADMISSION_LABEL = "fixlist-admission-coordinator-v1";
const ADMISSION_RECONCILIATION_VERSION = RELEASE_COMPONENT_VERSIONS.admission_reconciliation_version;
const COORDINATOR_TIMEOUT_MS = 5_000;
const ACTIVE_STATUSES = new Set(["queued", "crawling", "reviewing"]);
const TERMINAL_STATUSES = new Set(["complete", "limited", "failed", "cancelled"]);

class RequestProblem extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

Deno.serve(async (req) => {
  if (req.method !== "POST") {
    return Response.json({ success: false, error_code: "method_not_allowed", error: "Use POST for owner scan controls.", build_id: FUNCTION_BUILD_ID, runtime_activation_id: BASE44_RUNTIME_ACTIVATION_ID }, { status: 405 });
  }

  try {
    if (RELEASE_FINGERPRINT !== BASE44_HANDLER_RELEASE_FINGERPRINT) {
      throw new RequestProblem(503, "authority_release_activation_mismatch", "Server scan authority release activation is inconsistent.");
    }
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me().catch(() => null);
    requireOwnerAdmin(user);

    const body = unwrap(await req.json().catch(() => ({})));
    const action = cleanText(body?.action, 20).toLowerCase();
    const scanId = cleanId(body?.scan_id);
    if (!scanId) throw new RequestProblem(400, "scan_id_required", "Choose an exact scan first.");
    if (!new Set(["debug", "kill"]).has(action)) {
      throw new RequestProblem(400, "action_invalid", "Choose debug or kill.");
    }

    const entities = base44.asServiceRole.entities;
    let scan = await entities.ScanRun.get(scanId).catch(() => null);
    requireOwnedScan(scan, scanId, user.id);

    if (action === "debug") {
      const admission = await coordinatorStatus(user.id);
      return Response.json({
        success: true,
        action,
        scan: sanitizeScan(scan),
        admission: sanitizeAdmissionResult(admission),
      });
    }

    const expectedAttempt = normalizeAttempt(body?.attempt_count);
    if (!Number.isFinite(Number(body?.attempt_count)) || Number(body?.attempt_count) < 1) {
      throw new RequestProblem(400, "attempt_count_required", "The current scan attempt is required.");
    }
    if (normalizeAttempt(scan?.attempt_count) !== expectedAttempt) {
      throw new RequestProblem(409, "scan_attempt_changed", "A newer scan attempt now owns this row. Refresh before stopping it.");
    }

    let status = cleanText(scan?.status, 30).toLowerCase();
    if (TERMINAL_STATUSES.has(status)) {
      return await terminalReplayResponse({ entities, scan, scanId, action, ownerUserId: user.id });
    }
    if (!ACTIVE_STATUSES.has(status)) {
      throw new RequestProblem(409, "scan_not_stoppable", "This scan is not in a stoppable state.");
    }
    if (scan?.authority_sealed_at || scan?.authority_proof || scan?.release_gate_eligible === true) {
      throw new RequestProblem(409, "scan_authority_already_present", "This scan has authority evidence and cannot be manually cancelled.");
    }

    // Re-read immediately before the terminal write. The attempt fence prevents
    // an old browser tab from cancelling a newer retry of the same ScanRun.
    scan = await entities.ScanRun.get(scanId).catch(() => null);
    requireOwnedScan(scan, scanId, user.id);
    if (normalizeAttempt(scan?.attempt_count) !== expectedAttempt) {
      throw new RequestProblem(409, "scan_attempt_changed", "A newer scan attempt now owns this row. Refresh before stopping it.");
    }
    status = cleanText(scan?.status, 30).toLowerCase();
    if (TERMINAL_STATUSES.has(status)) {
      return await terminalReplayResponse({ entities, scan, scanId, action, ownerUserId: user.id });
    }
    if (!ACTIVE_STATUSES.has(status)) {
      throw new RequestProblem(409, "scan_not_stoppable", "This scan changed state before it could be stopped.");
    }
    if (scan?.authority_sealed_at || scan?.authority_proof || scan?.release_gate_eligible === true) {
      throw new RequestProblem(409, "scan_authority_already_present", "This scan has authority evidence and cannot be manually cancelled.");
    }

    const completedAt = new Date().toISOString();
    const detail = "Manually stopped by the owner debug control.";
    await entities.ScanRun.update(scanId, {
      status: "cancelled",
      status_detail: detail,
      cancelled_reason: "owner_manual_kill",
      error_code: "owner_manual_kill",
      error_message: detail,
      completed_at: completedAt,
      release_gate_eligible: false,
      admission_release_state: "pending",
      admission_release_last_attempt_at: "",
      admission_release_failure_code: "",
      admission_reconciliation_version: ADMISSION_RECONCILIATION_VERSION,
    });

    const persisted = await entities.ScanRun.get(scanId).catch(() => null);
    if (
      !persisted
      || cleanId(persisted.id) !== scanId
      || cleanText(persisted.status, 30).toLowerCase() !== "cancelled"
      || normalizeAttempt(persisted.attempt_count) !== expectedAttempt
      || persisted.release_gate_eligible === true
    ) {
      throw new RequestProblem(500, "owner_kill_persistence_failed", "The manual stop could not be verified.");
    }

    const release = await persistExactRelease({ entities, scan: persisted, release: coordinatorRelease });
    const releasedScan = release?.scanRun || await entities.ScanRun.get(scanId).catch(() => persisted);
    const admission = await coordinatorStatus(user.id);
    console.info("ownerScanDebugControl kill", {
      scan_id: scanId,
      attempt_count: expectedAttempt,
      lease_released: coordinatorLeaseReleased(admission),
    });

    return Response.json({
      success: true,
      action,
      replayed: false,
      scan: sanitizeScan(releasedScan),
      release: sanitizeReleaseResult(release),
      admission: sanitizeAdmissionResult(admission),
      lease_released: coordinatorLeaseReleased(admission),
    });
  } catch (error) {
    return problem(error);
  }
});

function requireOwnerAdmin(user: any) {
  const email = String(user?.email || "").trim().toLowerCase();
  const id = cleanId(user?.id);
  const role = String(user?.role || "").trim().toLowerCase();
  if (email !== OWNER_EMAIL || id !== OWNER_USER_ID || role !== "admin") {
    throw new RequestProblem(403, "owner_debug_forbidden", "Owner scan controls are unavailable to this account.");
  }
}

function requireOwnedScan(scan: any, scanId: string, userId: string) {
  if (!scan || cleanId(scan?.id) !== scanId || cleanId(scan?.owner_user_id || scan?.created_by_id) !== cleanId(userId)) {
    throw new RequestProblem(404, "scan_not_found", "This scan is not available to the owner debug account.");
  }
}

function sanitizeScan(scan: any) {
  return {
    id: cleanId(scan?.id),
    project_id: cleanId(scan?.project_id),
    website_url: cleanText(scan?.website_url, 2000),
    normalized_domain: cleanText(scan?.normalized_domain, 300),
    status: cleanText(scan?.status, 30),
    status_detail: cleanText(scan?.status_detail, 500),
    attempt_count: normalizeAttempt(scan?.attempt_count),
    queued_at: cleanText(scan?.queued_at, 100),
    started_at: cleanText(scan?.started_at, 100),
    worker_heartbeat_at: cleanText(scan?.worker_heartbeat_at, 100),
    reviewing_at: cleanText(scan?.reviewing_at, 100),
    completed_at: cleanText(scan?.completed_at, 100),
    updated_date: cleanText(scan?.updated_date || scan?.updated_at, 100),
    pages_found: finiteNumber(scan?.pages_found),
    pages_crawled: finiteNumber(scan?.pages_crawled),
    pages_retained: finiteNumber(scan?.pages_retained),
    error_code: cleanText(scan?.error_code, 120),
    error_message: cleanText(scan?.error_message, 500),
    release_gate_eligible: scan?.release_gate_eligible === true,
    authority_sealed: Boolean(scan?.authority_sealed_at || scan?.authority_proof),
    admission_access_id: cleanId(scan?.admission_access_id),
    admission_release_state: cleanText(scan?.admission_release_state, 40),
    admission_release_coordinator_request_id: cleanId(scan?.admission_release_coordinator_request_id),
    admission_reconciliation_version: cleanText(scan?.admission_reconciliation_version, 160),
  };
}

// persistExactRelease returns {ok, retryable, failureCode, state}, not the
// {status, body} shape a coordinator HTTP call returns. Sanitizing a release
// through the coordinator sanitizer reported status 0 and an empty error for
// every outcome, so a retryable failure like admission_release_persistence_failed
// reached the owner as "something went wrong" with the reason discarded -- in
// the one tool whose entire purpose is explaining a stuck scan.
// Both terminal branches -- the one before the re-read fence and the one after
// -- answer identically. Keeping one copy means a later change cannot update
// only half of a replay path.
async function terminalReplayResponse({ entities, scan, scanId, action, ownerUserId }: any) {
  const release = await persistExactRelease({ entities, scan, release: coordinatorRelease });
  const admission = await coordinatorStatus(ownerUserId);
  return Response.json({
    success: true,
    action,
    replayed: true,
    scan: sanitizeScan(release?.scanRun || await entities.ScanRun.get(scanId).catch(() => scan)),
    release: sanitizeReleaseResult(release),
    admission: sanitizeAdmissionResult(admission),
    lease_released: coordinatorLeaseReleased(admission),
  });
}

function sanitizeReleaseResult(result: any) {
  return {
    ok: result?.ok === true,
    state: cleanText(result?.state, 40),
    retryable: result?.retryable === true,
    failure_code: cleanText(result?.failureCode, 120),
  };
}

function sanitizeCoordinatorResult(result: any) {
  return {
    ok: result?.ok === true,
    status: Number(result?.status || 0),
    outcome: cleanText(result?.body?.outcome, 80),
    error: cleanText(result?.body?.error || result?.error, 100),
  };
}

function sanitizeAdmissionResult(result: any) {
  const admission = result?.body?.admission && typeof result.body.admission === "object" ? result.body.admission : {};
  return {
    ok: result?.ok === true,
    status: Number(result?.status || 0),
    lease_active: result?.ok === true ? result?.body?.lease_active === true : null,
    state: cleanText(admission?.state, 50),
    scan_id: cleanId(admission?.scan_id),
    request_id: cleanId(admission?.request_id),
    claimed_at: admission?.claimed_at ?? null,
    lease_expires_at: admission?.lease_expires_at ?? null,
    released_at: admission?.released_at ?? null,
    terminal_status: cleanText(admission?.terminal_status, 30),
    error: cleanText(result?.body?.error || result?.error, 100),
  };
}

function coordinatorLeaseReleased(result: any) {
  const admission = sanitizeAdmissionResult(result);
  const coordinatorSettled = admission.ok === true && admission.lease_active === false;
  return coordinatorSettled;
}

async function coordinatorStatus(ownerUserId: string) {
  return callCoordinator("/status", { owner_user_id: ownerUserId });
}

async function coordinatorRelease({ ownerUserId, scanId, terminalStatus }) {
  const result = await callCoordinator("/release", {
    owner_user_id: ownerUserId,
    scan_id: scanId,
    terminal_status: terminalStatus,
  });
  return result?.ok === true ? { ok: true, ...(result.body || {}) } : {
    ok: false,
    outcomeUnknown: result?.outcomeUnknown === true,
    failureCode: cleanText(result?.error || result?.body?.error, 120) || "coordinator_rejected",
  };
}

async function callCoordinator(path: string, payload: Record<string, unknown>) {
  const baseUrl = String(Deno.env.get("SCAN_ADMISSION_COORDINATOR_URL") || "").replace(/\/+$/, "");
  const rootSecret = String(Deno.env.get("SCAN_EVIDENCE_SIGNING_KEY") || "");
  if (!baseUrl || !rootSecret) {
    return { ok: false, status: 0, error: "admission_not_configured", body: {} };
  }

  const payloadText = JSON.stringify(payload);
  const timestamp = String(Math.trunc(Date.now() / 1000));
  let signature = "";
  try {
    signature = await admissionSignature(rootSecret, timestamp, payloadText);
  } catch {
    return { ok: false, status: 0, error: "admission_sign_failed", body: {} };
  }

  let response: Response;
  // The deadline has to outlive the fetch: a coordinator that answers headers
  // and then stalls its body would otherwise hold this request forever, which
  // is exactly the hang the owner is here to diagnose. The timer is cleared
  // once, after the body is read or has failed to read.
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), COORDINATOR_TIMEOUT_MS);
  try {
    response = await fetch(`${baseUrl}${path}`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-fixlist-timestamp": timestamp,
        "x-fixlist-signature": signature,
      },
      body: payloadText,
      signal: controller.signal,
    });
  } catch {
    clearTimeout(timeout);
    return { ok: false, status: 0, error: "admission_unreachable", outcomeUnknown: true, body: {} };
  }

  let body: any = {};
  try {
    body = await response.json();
  } catch {
    body = {};
  } finally {
    clearTimeout(timeout);
  }
  return { ok: response.ok, status: response.status, body };
}

async function admissionSignature(rootSecret: string, timestamp: string, payloadText: string) {
  const derivedKey = await hmacBytes(new TextEncoder().encode(rootSecret), ADMISSION_LABEL);
  const signature = await hmacBytes(derivedKey, `${timestamp}\n${payloadText}`);
  return Array.from(signature, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function hmacBytes(secretBytes: Uint8Array, payloadText: string) {
  const key = await crypto.subtle.importKey(
    "raw",
    secretBytes,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  return new Uint8Array(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(payloadText)));
}

function unwrap(body: any) {
  return body?.data && typeof body.data === "object" ? body.data : body;
}
function cleanId(value: any) {
  const text = String(value || "").trim();
  return /^[a-zA-Z0-9_-]{6,128}$/.test(text) ? text : "";
}
function cleanText(value: any, max = 200) {
  return String(value || "").trim().slice(0, max);
}
function normalizeAttempt(value: any) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(1, Math.trunc(parsed)) : 1;
}
function finiteNumber(value: any) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}
function problem(error: any) {
  const status = Number(error?.status || 500);
  const code = cleanText(error?.code || "owner_scan_control_failed", 80);
  const message = status >= 500
    ? "Owner scan controls are temporarily unavailable."
    : cleanText(error?.message || "The owner scan request could not be completed.", 260);
  if (status >= 500) console.error("ownerScanDebugControl failed", error instanceof Error ? error.name : "unknown_error");
  return Response.json({ success: false, error_code: code, error: message }, { status });
}
