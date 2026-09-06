import { createClientFromRequest } from "npm:@base44/sdk@0.8.40";
import { secrets } from "base44:runtime";
import { verifyAuthoritySeal } from "./workerEnvelope.js";
import { RELEASE_COMPONENT_VERSIONS, RELEASE_FINGERPRINT } from "./generatedReleaseContract.js";
import { FUNCTION_BUILD_ID } from "./generatedBuildId.js";
const BASE44_RUNTIME_ACTIVATION_ID = "limited-result-prod-reactivation-20260903-v1";
import {
  buildLimitedResultSnapshot,
  createLimitedResultProof,
  hasCompleteAcceptanceEvidence,
  limitedRowsFromSnapshot,
  requiresCompleteAcceptanceEvidence,
  MAX_LIMITED_FIXES,
} from "./limitedResultIntegrity.js";

function mutableScanAdmissionSecret(name) {
  try {
    return secrets.get(name);
  } catch {
    return "";
  }
}

function mutableScanAdmissionValue() {
  return mutableScanAdmissionSecret("BETA_SCAN_ADMISSION_ENABLED");
}

/**
 * Persist a scan that saw real evidence but not enough to be authoritative.
 *
 * Deliberately a separate package from persistDurableScanAuthority. Branching
 * that function to accept provisional data would put the authority seal one
 * boolean away from covering a scan that is not authoritative; here there is no
 * authority path to weaken, because none exists in this file.
 */

const BASE44_HANDLER_RELEASE_FINGERPRINT = "821d211419fd327e";
const WORKER_VERSION = "scan_job_worker_v1_cloud_tasks";
const LIMITED_COMPLETION_VERSION = "durable_standard150_limited_v1";
const LIMITED_COVERAGE_STATES = new Set(["limited_coverage", "inventory_unproven", "access_limited"]);

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
    return Response.json({ success: false, error_code: "method_not_allowed", error: "Use POST to persist a limited scan result.", build_id: FUNCTION_BUILD_ID, runtime_activation_id: BASE44_RUNTIME_ACTIVATION_ID }, { status: 405 });
  }

  try {
    if (RELEASE_FINGERPRINT !== BASE44_HANDLER_RELEASE_FINGERPRINT) {
      throw new RequestProblem(503, "limited_release_activation_mismatch", "Server limited-result release activation is inconsistent.");
    }
    assertWorkerHeader(req);
    const serviceBase44 = createClientFromRequest(req);
    const entities = serviceBase44.asServiceRole.entities;
    const body = await req.json().catch(() => ({}));
    const signedDocument = {
      version: body?.version,
      identity: body?.identity,
      scan: body?.scan,
      review: body?.review,
    };
    const proof = cleanProof(body?.proof);
    const secret = String(mutableScanAdmissionSecret("SCAN_EVIDENCE_SIGNING_KEY") || "");
    if (!secret) throw new RequestProblem(503, "limited_not_configured", "Server result integrity is not configured.");
    if (body?.version !== LIMITED_COMPLETION_VERSION || !proof || !await verifyAuthoritySeal(signedDocument, secret, proof)) {
      throw new RequestProblem(409, "worker_envelope_invalid", "The limited-result envelope could not be verified.");
    }

    const identity = normalizeIdentity(body?.identity);
    const scanResult = objectValue(body?.scan);
    const review = objectValue(body?.review);
    if (!identity.scan_id || !identity.project_id || !identity.owner_user_id) {
      throw new RequestProblem(400, "worker_identity_missing", "The limited-result identity is incomplete.");
    }

    // A limited result is only for a scan the coverage assessment actually
    // limited. Anything else belongs on the authority path or is a failure.
    if (!LIMITED_COVERAGE_STATES.has(String(review?.coverage_state || ""))) {
      throw new RequestProblem(409, "limited_state_not_eligible", "This scan is not in a limited coverage state.");
    }
    if (review?.release_gate_eligible === true || review?.score_is_provisional === false) {
      throw new RequestProblem(409, "limited_claims_authority", "A limited result cannot claim release eligibility.");
    }

    const scan = await entities.ScanRun.get(identity.scan_id).catch(() => null);
    if (!scan) throw new RequestProblem(404, "limited_record_not_found", "The durable scan was not found.");

    const claimedAttempt = normalizeAttempt(identity.attempt_count);
    if (claimedAttempt !== normalizeAttempt(scan.attempt_count)) {
      throw new RequestProblem(409, "superseded_attempt", "A newer attempt owns this scan.");
    }
    const scanStatus = String(scan.status || "").toLowerCase();
    if (["complete", "failed", "cancelled"].includes(scanStatus)) {
      throw new RequestProblem(409, "terminal_result_rejected", "This scan attempt is already terminal.");
    }
    if (cleanProof(scan.authority_proof)) {
      // An authoritative row must never be reachable from this path.
      throw new RequestProblem(409, "authority_immutable", "This scan already carries an authority proof.");
    }

    // One stable timestamp from durable state, so a retry rebuilds the same
    // payload and reaches the same proof instead of creating a second result.
    if (requiresCompleteAcceptanceEvidence(scanStatus, scan.result_integrity_version)
      && !hasCompleteAcceptanceEvidence(scanResult, review)) {
      throw new RequestProblem(
        409,
        "limited_acceptance_evidence_incomplete",
        "The scan did not produce complete measured acceptance evidence.",
      );
    }

    const sealedAt = cleanText(scan.result_integrity_sealed_at, 80) || stableTimestamp(scan);
    const workerScope = scanResult?.technical_audit_summary?.crawl_scope
      && typeof scanResult.technical_audit_summary.crawl_scope === "object"
      ? scanResult.technical_audit_summary.crawl_scope
      : {};
    const effectivePathPrefix = cleanText(
      workerScope?.effective_path_prefix
        || scanResult?.effective_path_prefix
        || scan.path_prefix
        || scan.requested_path_prefix,
      1_000,
    );
    const limitedScanResult = {
      ...scanResult,
      worker_source_sha: cleanText(body?.worker_source_sha, 80),
      scope_type: String(scan.scope_type || ""),
      parent_scan_id: String(scan.parent_scan_id || ""),
      requested_origin: String(scan.requested_origin || ""),
      requested_path_prefix: String(scan.requested_path_prefix || scan.path_prefix || ""),
      effective_path_prefix: effectivePathPrefix,
      path_prefix: String(scan.path_prefix || scan.requested_path_prefix || ""),
      discovered_from: String(scan.discovered_from || ""),
      user_confirmed: scan.user_confirmed === true,
    };
    const snapshot = buildLimitedResultSnapshot({
      identity,
      scan: limitedScanResult,
      review,
      now: sealedAt,
      version: scanStatus === "limited"
        ? cleanText(scan.result_integrity_version, 160) || undefined
        : undefined,
    });
    if (!snapshot.eligible_for_limited_result) {
      throw new RequestProblem(409, "limited_result_has_no_evidence", "There is no useful evidence to persist.");
    }
    const integrityProof = await createLimitedResultProof(snapshot, secret);

    if (scanStatus === "limited" && cleanProof(scan.result_integrity_proof) === integrityProof && scan.fix_list_id) {
      const release = await persistLimitedAdmissionRelease(entities, scan);
      const replayedScan = release?.scanRun || await entities.ScanRun.get(identity.scan_id).catch(() => scan);
      return Response.json({
        success: true,
        replayed: true,
        workerVersion: WORKER_VERSION,
        scanId: identity.scan_id,
        fixListId: scan.fix_list_id,
        resultIntegrityVerified: true,
        scanRun: replayedScan,
      });
    }

    const rowsWithoutListId = limitedRowsFromSnapshot(snapshot, { proof: integrityProof });
    const fixList = await upsertSingleFixList(entities, rowsWithoutListId.fixList, identity, scan);
    if (!fixList?.id) throw new RequestProblem(500, "limited_persistence_failed", "The limited FixList could not be saved.");

    const rows = limitedRowsFromSnapshot(snapshot, { fixListId: fixList.id, proof: integrityProof });
    await reconcileFixItems(entities, fixList.id, rows.fixItems);
    await assertAttemptStillActive(entities, identity.scan_id, claimedAttempt);

    await entities.ScanRun.update(identity.scan_id, rows.scanRun);
    const persistedScan = await entities.ScanRun.get(identity.scan_id);
    const persistedFixList = await entities.FixList.get(fixList.id);
    const persistedItems = rows.fixItems.length > 0
      ? await entities.FixItem.filter({ fix_list_id: fixList.id }, "created_date", MAX_LIMITED_FIXES)
      : [];

    const persisted = Boolean(
      persistedScan?.status === "limited"
      && persistedScan?.release_gate_eligible === false
      && persistedScan?.score_is_provisional === true
      && !cleanProof(persistedScan?.authority_proof)
      && cleanProof(persistedScan?.result_integrity_proof) === integrityProof
      && persistedScan?.fix_list_id === fixList.id
      && persistedFixList?.is_authoritative === false
      && cleanProof(persistedFixList?.result_integrity_proof) === integrityProof
      && persistedItems.length === rows.fixItems.length
      && persistedItems.every((item) => cleanProof(item?.result_integrity_proof) === integrityProof)
    );
    if (!persisted) {
      throw new RequestProblem(500, "limited_persistence_incomplete", "The limited result rows were not completely saved.");
    }

    const release = await persistLimitedAdmissionRelease(entities, persistedScan);
    const releasedScan = release?.scanRun || await entities.ScanRun.get(identity.scan_id).catch(() => persistedScan);

    return Response.json({
      success: true,
      replayed: false,
      workerVersion: WORKER_VERSION,
      scanId: identity.scan_id,
      fixListId: fixList.id,
      resultIntegrityVerified: true,
      scanRun: releasedScan,
    });
  } catch (error) {
    if (error instanceof RequestProblem) return problemResponse(error);
    console.error("persistLimitedScanResult failed", error instanceof Error ? error.name : "unknown_error");
    return problemResponse(new RequestProblem(500, "limited_result_failed", "The limited scan result could not be saved."));
  }
});

async function upsertSingleFixList(entities, desired, identity, scan) {
  const existingId = cleanId(scan?.fix_list_id);
  if (existingId) {
    const existing = await entities.FixList.get(existingId).catch(() => null);
    if (existing?.id) {
      await entities.FixList.update(existing.id, desired);
      return await entities.FixList.get(existing.id);
    }
  }
  const owned = await entities.FixList
    .filter({ scan_run_id: identity.scan_id, project_id: identity.project_id }, "-created_date", 1)
    .catch(() => []);
  if (owned?.[0]?.id) {
    await entities.FixList.update(owned[0].id, desired);
    return await entities.FixList.get(owned[0].id);
  }
  return await entities.FixList.create(desired);
}

async function reconcileFixItems(entities, fixListId, desiredRows) {
  const existing = await entities.FixItem.filter({ fix_list_id: fixListId }, "created_date", MAX_LIMITED_FIXES).catch(() => []);
  const existingIds = new Set((existing || []).map((row) => String(row?.fix_id || "")).filter(Boolean));
  for (const row of desiredRows) {
    if (existingIds.has(String(row.fix_id))) continue;
    await entities.FixItem.create(row);
  }
}

async function assertAttemptStillActive(entities, scanId, claimedAttempt) {
  const fresh = await entities.ScanRun.get(scanId).catch(() => null);
  if (!fresh || normalizeAttempt(fresh.attempt_count) !== claimedAttempt) {
    throw new RequestProblem(409, "superseded_attempt", "A newer attempt took over while saving.");
  }
}

const ADMISSION_LABEL = "fixlist-admission-coordinator-v1";
const RELEASE_OUTCOMES = new Set(["released", "already_released"]);
const SAFE_RELEASE_ERRORS = new Set([
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

function releaseIdentity(scan) {
  return {
    scanId: cleanId(scan?.id),
    ownerUserId: cleanId(scan?.owner_user_id || scan?.created_by_id),
    requestId: cleanId(scan?.request_id),
    idempotencyKey: cleanId(scan?.idempotency_key || scan?.request_id),
    attemptCount: normalizeAttempt(scan?.attempt_count),
    barrierGeneration: nonNegativeInteger(scan?.admission_barrier_generation),
    claimSequence: nonNegativeInteger(scan?.admission_claim_sequence),
    status: String(scan?.status || "").toLowerCase(),
  };
}

function exactReleaseIdentity(scan, expected) {
  const current = releaseIdentity(scan);
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

function releaseFailureCode(value) {
  const code = cleanText(value, 120).toLowerCase();
  return SAFE_RELEASE_ERRORS.has(code) ? code : "admission_release_failed";
}

async function persistLimitedAdmissionRelease(entities, scan) {
  if (!cleanId(scan?.admission_access_id)) return { ok: true, skipped: true };
  if (["released", "superseded", "satisfied_unbound"].includes(String(scan?.admission_release_state || ""))) {
    return { ok: true, replayed: true, state: scan.admission_release_state, scanRun: scan };
  }
  const expected = releaseIdentity(scan);
  if (
    expected.status !== "limited" || !expected.scanId || !expected.ownerUserId || !expected.requestId
    || expected.idempotencyKey !== expected.requestId
    || expected.barrierGeneration === null || expected.claimSequence === null
  ) return { ok: false, retryable: true, failureCode: "admission_release_identity_invalid" };

  const attemptedAt = new Date().toISOString();
  const result = await releaseAdmission(expected);
  const outcome = cleanText(result?.outcome, 80).toLowerCase();
  const exactResponse = Boolean(
    result?.ok === true && RELEASE_OUTCOMES.has(outcome)
    && cleanId(result?.request_id) === expected.requestId
    && cleanId(result?.scan_id) === expected.scanId
    && nonNegativeInteger(result?.barrier_generation) === expected.barrierGeneration
    && nonNegativeInteger(result?.claim_sequence) === expected.claimSequence
  );
  const fresh = await entities.ScanRun.get(expected.scanId).catch(() => null);
  if (!exactReleaseIdentity(fresh, expected)) {
    return { ok: false, retryable: true, failureCode: "admission_release_scan_changed" };
  }
  const fields = exactResponse ? {
    admission_release_state: "released",
    admission_release_reconciled_at: attemptedAt,
    admission_release_last_attempt_at: attemptedAt,
    admission_release_coordinator_request_id: expected.requestId,
    admission_release_outcome: outcome,
    admission_release_failure_code: "",
    admission_reconciliation_version: RELEASE_COMPONENT_VERSIONS.admission_reconciliation_version,
  } : {
    admission_release_state: "pending",
    admission_release_last_attempt_at: attemptedAt,
    admission_release_outcome: outcome,
    admission_release_failure_code: result?.ok === true
      ? "admission_release_identity_conflict"
      : releaseFailureCode(result?.failureCode),
    admission_reconciliation_version: RELEASE_COMPONENT_VERSIONS.admission_reconciliation_version,
  };
  await entities.ScanRun.update(expected.scanId, fields);
  const persisted = await entities.ScanRun.get(expected.scanId).catch(() => null);
  if (!exactReleaseIdentity(persisted, expected)) {
    return { ok: false, retryable: true, failureCode: "admission_release_persistence_failed" };
  }
  return exactResponse
    ? { ok: true, state: "released", scanRun: persisted }
    : { ok: false, retryable: true, failureCode: fields.admission_release_failure_code, scanRun: persisted };
}

async function releaseAdmission(expected) {
  const baseUrl = String(mutableScanAdmissionSecret("SCAN_ADMISSION_COORDINATOR_URL") || "").replace(/\/+$/, "");
  const root = String(mutableScanAdmissionSecret("SCAN_EVIDENCE_SIGNING_KEY") || "");
  if (!baseUrl || !root || String(mutableScanAdmissionValue() || "") !== "true") {
    return { ok: false, failureCode: "admission_not_configured" };
  }
  const payloadText = JSON.stringify({
    owner_user_id: expected.ownerUserId,
    scan_id: expected.scanId,
    terminal_status: expected.status,
  });
  const timestamp = String(Math.trunc(Date.now() / 1000));
  let signature;
  try {
    const derived = await hmacBytes(new TextEncoder().encode(root), ADMISSION_LABEL);
    signature = bytesToHex(await hmacBytes(derived, `${timestamp}\n${payloadText}`));
  } catch {
    return { ok: false, failureCode: "admission_sign_failed" };
  }
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5_000);
  let response;
  try {
    response = await fetch(`${baseUrl}/release`, {
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
    return { ok: false, outcomeUnknown: true, failureCode: "admission_unreachable" };
  } finally {
    clearTimeout(timeout);
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) return {
    ok: false,
    outcomeUnknown: response.status >= 500,
    failureCode: releaseFailureCode(body?.error || "coordinator_rejected"),
  };
  return { ok: true, ...body };
}

async function hmacBytes(secretBytes, payloadText) {
  const key = await crypto.subtle.importKey(
    "raw",
    secretBytes,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  return new Uint8Array(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(payloadText)));
}

function bytesToHex(bytes) {
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function nonNegativeInteger(value) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 0 ? parsed : null;
}

function stableTimestamp(scan) {
  return cleanText(scan?.started_at, 80) || cleanText(scan?.created_date, 80) || new Date().toISOString();
}

function assertWorkerHeader(req: Request) {
  if (String(req.headers.get("X-FixList-Worker") || "") !== WORKER_VERSION) {
    throw new RequestProblem(403, "worker_header_invalid", "The durable worker identity is invalid.");
  }
}

function normalizeIdentity(value) {
  const source = objectValue(value);
  return {
    owner_user_id: cleanId(source.owner_user_id),
    scan_id: cleanId(source.scan_id),
    project_id: cleanId(source.project_id),
    request_id: cleanId(source.request_id),
    attempt_count: source.attempt_count,
    normalized_domain: cleanText(source.normalized_domain, 400),
  };
}

function normalizeAttempt(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(1, Math.trunc(parsed)) : 1;
}

function objectValue(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function cleanId(value) {
  return String(value || "").trim().slice(0, 160);
}

function cleanText(value, limit) {
  return typeof value === "string" ? value.trim().slice(0, limit) : "";
}

function cleanProof(value) {
  const proof = String(value || "").trim().toLowerCase();
  return /^[a-f0-9]{64}$/.test(proof) ? proof : "";
}

function problemResponse(problem: RequestProblem) {
  return Response.json(
    { success: false, error_code: problem.code, error_message: problem.message },
    { status: problem.status },
  );
}
