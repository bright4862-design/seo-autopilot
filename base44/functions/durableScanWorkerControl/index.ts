import { createClientFromRequest } from "npm:@base44/sdk@0.8.40";
import { verifyAuthoritySeal } from "./authoritySeal.js";
import { releaseAdmission } from "./admissionClient.js";
import { reconciliationDecision, uniqueRows } from "./reconciliation.js";

// Attempts are 1-based; anything unparseable is attempt 1.
function normalizeAttempt(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(1, Math.trunc(parsed)) : 1;
}


const WORKER_VERSION = "scan_job_worker_v1_cloud_tasks";
const CONTROL_VERSION = "durable_standard150_control_v1";
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
    return problemResponse(new RequestProblem(405, "method_not_allowed", "Use POST for durable worker control."));
  }

  try {
    if (String(req.headers.get("X-FixList-Worker") || "") !== WORKER_VERSION) {
      throw new RequestProblem(403, "worker_header_invalid", "The durable worker identity is invalid.");
    }

    const body = await req.json().catch(() => ({}));
    const signedDocument = {
      version: body?.version,
      action: body?.action,
      scan_id: body?.scan_id,
      identity: body?.identity,
      failure: body?.failure,
    };
    const proof = cleanProof(body?.proof);
    const secret = String(Deno.env.get("SCAN_EVIDENCE_SIGNING_KEY") || "");
    if (!secret) throw new RequestProblem(503, "authority_not_configured", "Server scan authority is not configured.");
    if (body?.version !== CONTROL_VERSION || !proof || !await verifyAuthoritySeal(signedDocument, secret, proof)) {
      throw new RequestProblem(409, "worker_control_invalid", "The durable worker control envelope could not be verified.");
    }

    const action = String(body?.action || "");
    const base44 = createClientFromRequest(req);
    const entities = base44.asServiceRole.entities;

    if (action === "read") {
      const scanId = cleanId(body?.scan_id);
      if (!scanId) throw new RequestProblem(400, "worker_scan_id_missing", "The durable scan ID is missing.");
      const scan = await entities.ScanRun.get(scanId).catch(() => null);
      if (!scan) throw new RequestProblem(404, "worker_record_not_found", "The durable scan record was not found.");
      return Response.json({ success: true, workerVersion: WORKER_VERSION, scanRun: scan });
    }

    if (action === "sweep") {
      return Response.json(await reconcileDurableScans(entities));
    }

    if (!["start", "fail"].includes(action)) {
      throw new RequestProblem(400, "worker_action_invalid", "The durable worker action is not supported.");
    }

    const identity = normalizeIdentity(body?.identity);
    if (
      !identity.scan_id
      || !identity.project_id
      || !identity.owner_user_id
      || !identity.request_id
      || !identity.idempotency_key
      || !identity.normalized_domain
    ) {
      throw new RequestProblem(400, "worker_identity_missing", "The durable worker identity is incomplete.");
    }

    const scan = await entities.ScanRun.get(identity.scan_id).catch(() => null);
    const project = await entities.BusinessProject.get(identity.project_id).catch(() => null);
    if (!scan || !project) throw new RequestProblem(404, "worker_record_not_found", "The durable scan project was not found.");
    validateBoundIdentity({ scan, project, identity });

    // Attempt binding. A control call minted for an earlier attempt must not
    // write a failure over the attempt that currently owns the row.
    const claimedAttempt = normalizeAttempt(identity.attempt_count);
    const rowAttempt = normalizeAttempt(scan.attempt_count);
    if (claimedAttempt !== rowAttempt) {
      throw new RequestProblem(409, "superseded_attempt", "A newer attempt owns this scan.");
    }

    if (TERMINAL_STATUSES.has(String(scan.status || "").toLowerCase())) {
      await releaseIfServerAdmitted(scan);
      return Response.json({
        success: true,
        replayed: true,
        workerVersion: WORKER_VERSION,
        scanRun: scan,
      });
    }

    if (action === "start") {
      const currentStatus = String(scan.status || "queued").toLowerCase();
      if (!["queued", "crawling", "reviewing"].includes(currentStatus)) {
        throw new RequestProblem(409, "worker_start_state_invalid", "The durable scan is not startable.");
      }
      const heartbeatAt = new Date().toISOString();
      const startFields = {
        worker_heartbeat_at: heartbeatAt,
      };
      if (currentStatus === "queued") {
        Object.assign(startFields, {
          status: "crawling",
          status_detail: "",
          started_at: cleanText(scan?.started_at, 80) || heartbeatAt,
        });
      }
      await entities.ScanRun.update(identity.scan_id, startFields);
      const persisted = await entities.ScanRun.get(identity.scan_id);
      if (
        !persisted
        || !["crawling", "reviewing"].includes(String(persisted.status || "").toLowerCase())
        || !cleanText(persisted?.started_at, 80)
        || !cleanText(persisted?.worker_heartbeat_at, 80)
        || cleanId(persisted?.id) !== identity.scan_id
        || normalizeAttempt(persisted?.attempt_count) !== claimedAttempt
      ) {
        throw new RequestProblem(500, "worker_start_persistence_failed", "The durable scan start could not be verified.");
      }
      return Response.json({
        success: true,
        replayed: currentStatus !== "queued",
        workerVersion: WORKER_VERSION,
        scanRun: persisted,
      });
    }

    const failure = objectValue(body?.failure);
    const failureCode = cleanCode(failure.code) || "scan_failed";
    const detail = cleanText(failure.detail, 500) || "The scan stopped unexpectedly. No partial result was saved.";
    await entities.ScanRun.update(identity.scan_id, {
      status: "failed",
      status_detail: detail,
      error_code: failureCode,
      error_message: detail,
      completed_at: new Date().toISOString(),
      release_gate_eligible: false,
    });

    const persisted = await entities.ScanRun.get(identity.scan_id);
    if (
      persisted?.status !== "failed"
      || cleanId(persisted?.id) !== identity.scan_id
      || cleanId(persisted?.project_id) !== identity.project_id
      || !recordOwnedById(persisted, identity.owner_user_id)
      || persisted?.release_gate_eligible === true
    ) {
      throw new RequestProblem(500, "worker_failure_persistence_failed", "The durable failure state could not be verified.");
    }
    await releaseIfServerAdmitted(persisted);

    return Response.json({
      success: true,
      replayed: false,
      workerVersion: WORKER_VERSION,
      scanRun: persisted,
    });
  } catch (error) {
    if (error instanceof RequestProblem) return problemResponse(error);
    console.error("durableScanWorkerControl failed", error instanceof Error ? error.name : "unknown_error");
    return problemResponse(new RequestProblem(500, "worker_control_failed", "The durable worker control request failed."));
  }
});

async function reconcileDurableScans(entities) {
  const statuses = ["queued", "crawling", "reviewing", "complete", "limited", "failed", "cancelled"];
  let rows;
  try {
    const groups = await Promise.all(statuses.map((status) => {
      const sort = status === "queued"
        ? "-queued_at"
        : (["crawling", "reviewing"].includes(status) ? "-started_at" : "-completed_at");
      return entities.ScanRun.filter({ status }, sort, 50);
    }));
    rows = uniqueRows(groups.flat());
  } catch {
    throw new RequestProblem(503, "worker_reconciliation_query_failed", "Durable scan reconciliation is temporarily unavailable.");
  }

  const counts = { examined: 0, closed: 0, released: 0, skipped: 0, errors: 0 };
  const nowMs = Date.now();
  for (const candidate of rows) {
    const scanId = cleanId(candidate?.id);
    if (!scanId) continue;
    counts.examined += 1;
    try {
      const fresh = await entities.ScanRun.get(scanId).catch(() => null);
      if (!fresh || cleanId(fresh.id) !== scanId) { counts.skipped += 1; continue; }
      const decision = reconciliationDecision(fresh, nowMs);
      if (decision.action === "skip") { counts.skipped += 1; continue; }
      if (decision.action === "release") {
        if (await releaseIfServerAdmitted(fresh)) counts.released += 1;
        else counts.errors += 1;
        continue;
      }
      const current = await entities.ScanRun.get(scanId).catch(() => null);
      if (!current || cleanId(current.id) !== scanId) { counts.skipped += 1; continue; }
      if (normalizeAttempt(current.attempt_count) !== normalizeAttempt(fresh.attempt_count)) { counts.skipped += 1; continue; }
      const currentDecision = reconciliationDecision(current, nowMs);
      if (currentDecision.action !== "fail" || currentDecision.error_code !== decision.error_code) {
        counts.skipped += 1;
        continue;
      }
      await entities.ScanRun.update(scanId, {
        status: "failed",
        status_detail: currentDecision.detail,
        error_code: currentDecision.error_code,
        error_message: currentDecision.detail,
        completed_at: new Date(nowMs).toISOString(),
        release_gate_eligible: false,
      });
      const persisted = await entities.ScanRun.get(scanId).catch(() => null);
      if (!persisted || String(persisted.status || "").toLowerCase() !== "failed" || persisted.release_gate_eligible === true) {
        counts.errors += 1;
        continue;
      }
      counts.closed += 1;
      if (await releaseIfServerAdmitted(persisted)) counts.released += 1;
      else counts.errors += 1;
    } catch (error) {
      counts.errors += 1;
      console.error("durable scan reconciliation candidate failed", {
        scan_id: scanId,
        error: error instanceof Error ? error.name : "unknown_error",
      });
    }
  }

  return {
    success: counts.errors === 0,
    workerVersion: WORKER_VERSION,
    reconciliation: counts,
  };
}

async function releaseIfServerAdmitted(scan) {
  if (!cleanId(scan?.admission_access_id)) return true;
  const terminalStatus = String(scan?.status || "").trim().toLowerCase();
  if (!TERMINAL_STATUSES.has(terminalStatus)) return false;
  const released = await releaseAdmission({
    ownerUserId: cleanId(scan?.owner_user_id || scan?.created_by_id),
    scanId: cleanId(scan?.id),
    terminalStatus,
  }).catch(() => ({ ok: false, failureCode: "admission_unreachable", outcomeUnknown: true }));
  if (released?.ok && ["released", "already_released"].includes(String(released.outcome || ""))) return true;
  console.error("durableScanWorkerControl admission release failed", {
    scan_id: cleanId(scan?.id),
    terminal_status: terminalStatus,
    failure_code: cleanCode(released?.failureCode) || "admission_release_failed",
    outcome_unknown: released?.outcomeUnknown === true,
  });
  return false;
}

function normalizeIdentity(value) {
  const source = objectValue(value);
  return {
    owner_user_id: cleanId(source.owner_user_id),
    scan_id: cleanId(source.scan_id),
    project_id: cleanId(source.project_id),
    request_id: cleanId(source.request_id),
    idempotency_key: cleanId(source.idempotency_key),
    normalized_domain: normalizeDomain(source.normalized_domain),
    attempt_count: normalizeAttempt(source.attempt_count),
  };
}

function validateBoundIdentity({ scan, project, identity }) {
  const requestMatches = !scan?.request_id || cleanId(scan.request_id) === identity.request_id;
  const idempotencyMatches = !scan?.idempotency_key || cleanId(scan.idempotency_key) === identity.idempotency_key;
  if (
    cleanId(scan?.id) !== identity.scan_id
    || cleanId(scan?.project_id) !== identity.project_id
    || !recordOwnedById(scan, identity.owner_user_id)
    || !recordOwnedById(project, identity.owner_user_id)
    || !requestMatches
    || !idempotencyMatches
    || normalizeDomain(scan?.website_url || scan?.submitted_url) !== identity.normalized_domain
    || normalizeDomain(project?.website_url) !== identity.normalized_domain
  ) {
    throw new RequestProblem(409, "worker_identity_mismatch", "The durable worker request no longer matches this owner-bound scan.");
  }
}

function recordOwnedById(record, ownerId) {
  const owner = cleanId(ownerId);
  return Boolean(owner && (
    cleanId(record?.owner_user_id) === owner
    || cleanId(record?.created_by_id) === owner
  ));
}

function normalizeDomain(value) {
  const raw = cleanText(value, 2_000);
  if (!raw) return "";
  try {
    const parsed = new URL(/^https?:\/\//i.test(raw) ? raw : `https://${raw}`);
    return ["http:", "https:"].includes(parsed.protocol)
      ? parsed.hostname.toLowerCase().replace(/^www\./, "").replace(/\.$/, "")
      : "";
  } catch {
    return "";
  }
}

function objectValue(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function cleanProof(value) {
  const proof = cleanText(value, 64).toLowerCase();
  return /^[a-f0-9]{64}$/.test(proof) ? proof : "";
}

function cleanCode(value) {
  const code = cleanText(value, 120).toLowerCase().replace(/[^a-z0-9_-]/g, "_");
  return /^[a-z0-9][a-z0-9_-]*$/.test(code) ? code : "";
}

function cleanText(value, limit) {
  return typeof value === "string" ? value.trim().slice(0, limit) : "";
}

function cleanId(value) {
  return cleanText(value, 160);
}

function problemResponse(error) {
  return Response.json({ success: false, error_code: error.code, error: error.message }, { status: error.status });
}