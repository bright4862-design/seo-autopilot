import { createClientFromRequest } from "npm:@base44/sdk@0.8.40";
import { RELEASE_FINGERPRINT } from "./generatedReleaseContract.js";
import { verifyAuthoritySeal } from "./authoritySeal.js";
import {
  finishReconciliationInvocation,
  releaseAdmission,
  satisfyUnboundAdmission,
  startReconciliationInvocation,
  statusAdmission,
} from "./admissionClient.js";
import {
  ADMISSION_RECONCILIATION_VERSION,
  RECONCILE_BATCH_LIMIT,
  RECONCILE_COORDINATOR_CONCURRENCY,
  RECONCILE_COORDINATOR_TIMEOUT_MS,
  RECONCILE_GLOBAL_DEADLINE_MS,
  RECONCILE_QUERY_PAGE_LIMIT,
  RECONCILE_QUERY_PAGE_SIZE,
  admissionReleaseIdentity,
  mapWithConcurrency,
  oldestAttemptFirst,
  reconcileAdmissionReleaseCandidate,
  reconciliationDecision,
  releaseExactTerminalAdmission,
  uniqueRows,
} from "./reconciliation.js";

// Attempts are 1-based; anything unparseable is attempt 1.
function normalizeAttempt(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(1, Math.trunc(parsed)) : 1;
}


const BASE44_HANDLER_RELEASE_FINGERPRINT = "0fa7d98734efb3f2";
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
    if (RELEASE_FINGERPRINT !== BASE44_HANDLER_RELEASE_FINGERPRINT) {
      throw new RequestProblem(503, "control_release_activation_mismatch", "Server worker-control release activation is inconsistent.");
    }
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
      await releaseIfServerAdmitted(entities, scan);
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
    await releaseIfServerAdmitted(entities, persisted);

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
  const sourceSha = String(Deno.env.get("FIXLIST_RELEASE_SOURCE_SHA") || "").trim();
  if (!/^[a-f0-9]{40}$/.test(sourceSha)) {
    throw new RequestProblem(503, "worker_reconciliation_source_invalid", "Durable scan reconciliation source identity is unavailable.");
  }
  const invocationId = `reconcile_${Date.now().toString(36)}_${crypto.randomUUID().replace(/-/g, "")}`;
  const started = await startReconciliationInvocation({
    invocationId,
    sourceSha,
    leaseSeconds: 60,
    timeoutMs: RECONCILE_COORDINATOR_TIMEOUT_MS,
  }).catch(() => ({ ok: false, failureCode: "admission_unreachable" }));
  if (!exactReconciliationInvocation(started, { invocationId, sourceSha, state: "live" })) {
    throw new RequestProblem(503, "worker_reconciliation_tracking_failed", "Durable scan reconciliation tracking is unavailable.");
  }

  let payload;
  let finishOutcome = "retryable_failure";
  try {
    payload = await runReconciliationSweep(entities);
    finishOutcome = payload.success === true ? "success" : "retryable_failure";
  } catch (error) {
    await finishReconciliationInvocation({
      invocationId,
      sourceSha,
      outcome: "retryable_failure",
      timeoutMs: RECONCILE_COORDINATOR_TIMEOUT_MS,
    }).catch(() => null);
    throw error;
  }

  const finished = await finishReconciliationInvocation({
    invocationId,
    sourceSha,
    outcome: finishOutcome,
    timeoutMs: RECONCILE_COORDINATOR_TIMEOUT_MS,
  }).catch(() => ({ ok: false, failureCode: "admission_unreachable" }));
  if (!exactReconciliationInvocation(finished, { invocationId, sourceSha, state: "finished" })) {
    payload.success = false;
    payload.reconciliation.errors += 1;
    payload.reconciliation.retryable += 1;
    payload.reconciliation.invocation_finish_failed = 1;
  }
  return payload;
}

async function runReconciliationSweep(entities) {
  const startedAt = Date.now();
  const deadlineMs = startedAt + RECONCILE_GLOBAL_DEADLINE_MS;
  const nowMs = startedAt;
  const counts: Record<string, number> = {
    examined: 0,
    closed: 0,
    released: 0,
    superseded: 0,
    satisfied_unbound: 0,
    pending: 0,
    retryable: 0,
    skipped: 0,
    errors: 0,
    query_pages: 0,
    candidates: 0,
    deadline_reached: 0,
  };
  let rows;
  try {
    const queried = await collectReconciliationCandidates(entities.ScanRun, nowMs, deadlineMs);
    rows = queried.rows;
    counts.query_pages = queried.queryPages;
  } catch {
    throw new RequestProblem(503, "worker_reconciliation_query_failed", "Durable scan reconciliation is temporarily unavailable.");
  }
  const candidates = oldestAttemptFirst(uniqueRows(rows)).slice(0, RECONCILE_BATCH_LIMIT);
  counts.candidates = candidates.length;

  const mapped = await mapWithConcurrency(
    candidates,
    RECONCILE_COORDINATOR_CONCURRENCY,
    async (candidate) => reconcileOneCandidate(entities, candidate, nowMs),
    deadlineMs,
  );
  counts.examined = mapped.processed;
  if (mapped.deadlineReached) counts.deadline_reached = 1;
  for (const result of mapped.results.filter(Boolean)) {
    if (result.closed) counts.closed += 1;
    if (result.state === "released") counts.released += 1;
    else if (result.state === "superseded") counts.superseded += 1;
    else if (result.state === "satisfied_unbound") counts.satisfied_unbound += 1;
    else if (result.pending) counts.pending += 1;
    else if (result.skipped) counts.skipped += 1;
    if (result.retryable) counts.retryable += 1;
    if (result.error) counts.errors += 1;
  }
  if (counts.deadline_reached) counts.retryable += 1;
  return {
    success: counts.errors === 0 && counts.retryable === 0,
    workerVersion: WORKER_VERSION,
    reconciliation: counts,
  };
}

async function collectReconciliationCandidates(scans, nowMs, deadlineMs) {
  const descriptors = [
    ...["complete", "limited", "failed", "cancelled"].map((status) => ({
      query: { status },
      sort: "admission_release_last_attempt_at",
    })),
    { query: { status: "queued" }, sort: "queued_at" },
    { query: { status: "crawling" }, sort: "started_at" },
    { query: { status: "reviewing" }, sort: "started_at" },
  ];
  const rows: any[] = [];
  let queryPages = 0;
  let page = 0;
  const exhausted = new Set<number>();
  while (
    queryPages < RECONCILE_QUERY_PAGE_LIMIT
    && exhausted.size < descriptors.length
    && Date.now() < deadlineMs
  ) {
    const descriptorIndex = page % descriptors.length;
    const offsetPage = Math.trunc(page / descriptors.length);
    page += 1;
    if (exhausted.has(descriptorIndex)) continue;
    const descriptor = descriptors[descriptorIndex];
    const group = await scans.filter(
      descriptor.query,
      descriptor.sort,
      RECONCILE_QUERY_PAGE_SIZE,
      offsetPage * RECONCILE_QUERY_PAGE_SIZE,
    );
    queryPages += 1;
    if (!Array.isArray(group) || group.length < RECONCILE_QUERY_PAGE_SIZE) exhausted.add(descriptorIndex);
    for (const row of group || []) {
      const decision = reconciliationDecision(row, nowMs);
      if (decision.action === "release" || decision.action === "fail") rows.push(row);
    }
  }
  return { rows, queryPages };
}

async function reconcileOneCandidate(entities, candidate, nowMs) {
  const scanId = cleanId(candidate?.id);
  if (!scanId) return { skipped: true };
  try {
    let fresh = await entities.ScanRun.get(scanId).catch(() => null);
    if (!fresh || cleanId(fresh.id) !== scanId) return { skipped: true };
    let decision = reconciliationDecision(fresh, nowMs);
    if (decision.action === "skip") return { skipped: true };
    let closed = false;
    if (decision.action === "fail") {
      const snapshot = admissionReleaseIdentity(fresh);
      const current = await entities.ScanRun.get(scanId).catch(() => null);
      decision = reconciliationDecision(current, nowMs);
      if (!sameAdmissionGeneration(current, snapshot) || decision.action !== "fail") return { skipped: true };
      const completedAt = new Date(nowMs).toISOString();
      await entities.ScanRun.update(scanId, {
        status: "failed",
        status_detail: decision.detail,
        error_code: decision.error_code,
        error_message: decision.detail,
        completed_at: completedAt,
        release_gate_eligible: false,
        admission_release_state: "pending",
        admission_release_last_attempt_at: "",
        admission_release_failure_code: "",
        admission_reconciliation_version: ADMISSION_RECONCILIATION_VERSION,
      });
      fresh = await entities.ScanRun.get(scanId).catch(() => null);
      if (
        !sameAdmissionGeneration(fresh, snapshot)
        || String(fresh?.status || "").toLowerCase() !== "failed"
        || fresh?.release_gate_eligible === true
      ) return { error: true, retryable: true };
      closed = true;
    }

    const outcome = await reconcileAdmissionReleaseCandidate({
      entities: entities.ScanRun,
      scan: fresh,
      statusAdmission,
      releaseAdmission,
      satisfyUnboundAdmission,
    });
    if (outcome?.retryable) {
      console.error("durable scan admission reconciliation retryable", {
        scan_id: scanId,
        failure_code: closedReleaseFailureCode(outcome?.failureCode),
      });
    }
    return { ...outcome, closed, error: outcome?.retryable === true };
  } catch (error) {
    console.error("durable scan reconciliation candidate failed", {
      scan_id: scanId,
      error: error instanceof Error ? error.name : "unknown_error",
    });
    return { error: true, retryable: true };
  }
}

async function releaseIfServerAdmitted(entities, scan) {
  const terminalStatus = String(scan?.status || "").trim().toLowerCase();
  if (!TERMINAL_STATUSES.has(terminalStatus)) return false;
  const released = await releaseExactTerminalAdmission({
    entities: entities.ScanRun,
    scan,
    releaseAdmission,
  });
  if (released?.ok === true) return true;
  console.error("durableScanWorkerControl admission release failed", {
    scan_id: cleanId(scan?.id),
    terminal_status: terminalStatus,
    failure_code: closedReleaseFailureCode(released?.failureCode),
  });
  return false;
}

function sameAdmissionGeneration(scan, expected) {
  const current = admissionReleaseIdentity(scan);
  return Boolean(
    current.scanId === expected.scanId
    && current.ownerUserId === expected.ownerUserId
    && current.requestId === expected.requestId
    && current.idempotencyKey === expected.idempotencyKey
    && current.attemptCount === expected.attemptCount
    && current.barrierGeneration === expected.barrierGeneration
    && current.claimSequence === expected.claimSequence
  );
}

function exactReconciliationInvocation(result, expected) {
  const invocation = result?.invocation;
  return Boolean(
    result?.ok === true
    && invocation && typeof invocation === "object"
    && String(invocation?.version || "") === "admission_reconciliation_invocation_v1"
    && String(invocation?.invocation_id || "") === expected.invocationId
    && String(invocation?.source_sha || "") === expected.sourceSha
    && String(invocation?.state || "") === expected.state
  );
}

function closedReleaseFailureCode(value) {
  const safe = new Set([
    "admission_release_failed",
    "admission_release_identity_invalid",
    "admission_release_identity_conflict",
    "admission_release_persistence_failed",
    "admission_release_scan_changed",
    "admission_status_unavailable",
    "admission_unreachable",
    "admission_disabled",
    "admission_not_configured",
    "admission_sign_failed",
    "coordinator_rejected",
    "coordinator_unavailable",
    "coordinator_generation_ambiguous",
    "coordinator_lease_state_ambiguous",
    "coordinator_state_ambiguous",
    "same_request_scan_identity_conflict",
    "scan_identity_conflict",
    "scan_not_bound",
    "barrier_generation_conflict",
    "admission_satisfy_unbound_unavailable",
    "admission_satisfy_identity_conflict",
    "admission_reconciliation_invalid",
  ]);
  const candidate = String(value || "").trim().toLowerCase();
  return safe.has(candidate) ? candidate : "admission_release_failed";
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
