import { createClientFromRequest } from "npm:@base44/sdk@0.8.40";
import { createAuthoritySeal, verifyAuthoritySeal } from "./authoritySeal.js";
import { authorityRowsFromSnapshot } from "./authorityRows.js";
import { buildAuthoritySnapshot, firstFailedAuthorityPredicate } from "./authoritySnapshot.js";
import { releaseAdmission } from "./admissionClient.js";

// Attempts are 1-based; anything unparseable is attempt 1. Mirrors
// normalize_attempt in scanner-api/app/scan_job.py.
function normalizeAttempt(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(1, Math.trunc(parsed)) : 1;
}


const WORKER_VERSION = "scan_job_worker_v1_cloud_tasks";
const COMPLETION_VERSION = "durable_standard150_completion_v1";
const MAX_FIX_ITEMS = 100;

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
    return problemResponse(new RequestProblem(405, "method_not_allowed", "Use POST to persist durable scan authority."));
  }

  try {
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
    const secret = String(Deno.env.get("SCAN_EVIDENCE_SIGNING_KEY") || "");
    if (!secret) throw new RequestProblem(503, "authority_not_configured", "Server scan authority is not configured.");
    if (body?.version !== COMPLETION_VERSION || !proof || !await verifyAuthoritySeal(signedDocument, secret, proof)) {
      throw new RequestProblem(409, "worker_envelope_invalid", "The durable worker completion envelope could not be verified.");
    }

    const identity = normalizeIdentity(body?.identity);
    const scanResult = objectValue(body?.scan);
    const review = objectValue(body?.review);
    if (!identity.scan_id || !identity.project_id || !identity.owner_user_id || !identity.normalized_domain) {
      throw new RequestProblem(400, "worker_identity_missing", "The durable worker identity is incomplete.");
    }

    const scan = await entities.ScanRun.get(identity.scan_id).catch(() => null);
    const project = await entities.BusinessProject.get(identity.project_id).catch(() => null);
    if (!scan || !project) throw new RequestProblem(404, "authority_record_not_found", "The durable scan project was not found.");
    validateCurrentIdentity({ scan, project, identity, scanResult });

    const failedPredicate = firstFailedAuthorityPredicate(scanResult, review);
    if (failedPredicate) {
      throw new RequestProblem(409, `authority_snapshot_not_eligible__${failedPredicate}`, "The reviewed scan is not release-authoritative.");
    }

    const stableSealedAt = stableTimestamp(scan);
    const snapshot = buildAuthoritySnapshot({
      scan: scanResult,
      review,
      identity,
      userId: identity.owner_user_id,
      now: stableSealedAt,
    });
    const authorityProof = await createAuthoritySeal(snapshot, secret);
    // Attempt binding. The signed identity carries the attempt this worker was
    // minted for; the durable row carries the attempt that currently owns it.
    // A task from an earlier attempt must not persist, finalise or charge.
    const claimedAttempt = normalizeAttempt(identity.attempt_count);
    const rowAttempt = normalizeAttempt(scan.attempt_count);
    if (claimedAttempt !== rowAttempt) {
      throw new RequestProblem(409, "superseded_attempt", "A newer attempt owns this scan.");
    }

    const scanStatus = String(scan.status || "").toLowerCase();
    if (["failed", "cancelled", "limited"].includes(scanStatus)) {
      throw new RequestProblem(409, "terminal_authority_rejected", "This scan attempt is already terminal.");
    }
    if (scanStatus === "complete") {
      if (scan.authority_proof === authorityProof && scan.fix_list_id) {
        await releaseIfServerAdmitted(scan);
        return Response.json({
          success: true,
          replayed: true,
          workerVersion: WORKER_VERSION,
          scanId: identity.scan_id,
          fixListId: scan.fix_list_id,
          fixListVerified: true,
          allowanceConsumed: false,
          scanRun: scan,
        });
      }
      throw new RequestProblem(409, "authority_immutable", "This scan is already terminal.");
    }

    // A proof staged by this attempt is resumable. A staged proof owned by a
    // different attempt is superseded and cannot be replaced.
    if (
      scan.authority_proof
      && scan.authority_proof !== authorityProof
      && normalizeAttempt(scan.authority_attempt_count ?? rowAttempt) !== claimedAttempt
    ) {
      throw new RequestProblem(409, "superseded_attempt", "A different attempt staged this authority.");
    }
    const replayed = scan.authority_proof === authorityProof;

    const rowsWithoutListId = authorityRowsFromSnapshot(snapshot, {
      ownerUserId: identity.owner_user_id,
      proof: authorityProof,
    });
    const fixList = await upsertSingleFixList(entities, rowsWithoutListId.fixList, identity, scan);
    if (!fixList?.id) throw new RequestProblem(500, "authority_persistence_failed", "The authoritative FixList could not be saved.");

    const rows = authorityRowsFromSnapshot(snapshot, {
      fixListId: fixList.id,
      ownerUserId: identity.owner_user_id,
      proof: authorityProof,
    });
    await reconcileFixItems(entities, fixList.id, rows.fixItems);
    await assertAttemptStillActive(entities, identity.scan_id, claimedAttempt);

    // Stage the exact authority proof while the run remains non-terminal. This
    // makes retries safe and lets us verify every authoritative row before any
    // allowance is consumed.
    // attempt_count belongs to the browser/dispatcher lifecycle, never to an
    // authority row. Writing it back here would let a slow task resurrect an
    // old attempt number onto a row that has already moved on.
    const { attempt_count: _stagedAttempt, ...scanRunFields } = rows.scanRun;
    const stagedScanFields = {
      ...scanRunFields,
      status: "reviewing",
      status_detail: "Authority verified; finalizing this scan.",
      release_gate_eligible: false,
      completed_at: "",
    };
    await entities.ScanRun.update(identity.scan_id, stagedScanFields);

    const stagedScan = await entities.ScanRun.get(identity.scan_id);
    const persistedFixList = await entities.FixList.get(fixList.id);
    const persistedItems = rows.fixItems.length > 0
      ? await entities.FixItem.filter({ fix_list_id: fixList.id }, "created_date", MAX_FIX_ITEMS)
      : [];
    const authorityStaged = Boolean(
      stagedScan?.status === "reviewing"
      && normalizeAttempt(stagedScan?.attempt_count) === claimedAttempt
      && stagedScan?.authority_proof === authorityProof
      && stagedScan?.authority_seal_version === snapshot.version
      && stagedScan?.authority_sealed_at === snapshot.sealed_at
      && stagedScan?.fix_list_id === fixList.id
      && stagedScan?.release_gate_eligible === false
      && persistedFixList?.authority_proof === authorityProof
      && persistedFixList?.is_authoritative === true
      && String(persistedFixList?.scan_run_id || "") === identity.scan_id
      && String(persistedFixList?.project_id || "") === identity.project_id
      && String(persistedFixList?.owner_user_id || "") === identity.owner_user_id
      && persistedItems.length === rows.fixItems.length
      && persistedItems.every((item) => item?.authority_proof === authorityProof)
    );
    if (!authorityStaged) {
      throw new RequestProblem(500, "authority_persistence_incomplete", "The durable authority rows were not completely staged.");
    }

    // Paid admission happens before enqueue. Completion never creates, updates
    // or consumes Access rows, so a persistence retry cannot affect billing.
    await assertAttemptStillActive(entities, identity.scan_id, claimedAttempt);
    await entities.ScanRun.update(identity.scan_id, scanRunFields);
    const persistedScan = await entities.ScanRun.get(identity.scan_id);
    const authorityPersisted = Boolean(
      persistedScan?.status === "complete"
      && persistedScan?.authority_proof === authorityProof
      && persistedScan?.authority_seal_version === snapshot.version
      && persistedScan?.authority_sealed_at === snapshot.sealed_at
      && persistedScan?.fix_list_id === fixList.id
      && persistedScan?.release_gate_eligible === true
    );
    if (!authorityPersisted) {
      throw new RequestProblem(500, "authority_terminal_update_failed", "The authoritative scan could not be finalized.");
    }
    await releaseIfServerAdmitted(persistedScan);

    return Response.json({
      success: true,
      replayed,
      workerVersion: WORKER_VERSION,
      scanId: identity.scan_id,
      fixListId: fixList.id,
      fixListVerified: true,
      allowanceConsumed: false,
      scanRun: persistedScan,
    });
  } catch (error) {
    if (error instanceof RequestProblem) return problemResponse(error);
    console.error("persistDurableScanAuthority failed", error instanceof Error ? error.name : "unknown_error");
    return problemResponse(new RequestProblem(500, "durable_authority_failed", "The durable scan authority could not be saved."));
  }
});

async function releaseIfServerAdmitted(scan) {
  if (!cleanId(scan?.admission_access_id)) return true;
  const released = await releaseAdmission({
    ownerUserId: cleanId(scan?.owner_user_id || scan?.created_by_id),
    scanId: cleanId(scan?.id),
    terminalStatus: "complete",
  }).catch(() => ({ ok: false, failureCode: "admission_unreachable", outcomeUnknown: true }));
  if (released?.ok && ["released", "already_released"].includes(String(released.outcome || ""))) return true;
  console.error("persistDurableScanAuthority admission release failed", {
    scan_id: cleanId(scan?.id),
    failure_code: cleanText(released?.failureCode, 120) || "admission_release_failed",
    outcome_unknown: released?.outcomeUnknown === true,
  });
  return false;
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
    idempotency_key: cleanId(source.idempotency_key),
    normalized_domain: normalizeDomain(source.normalized_domain),
    // Signed by the worker. Without it the attempt guard would compare
    // undefined and silently pass, so a superseded task could still write.
    attempt_count: normalizeAttempt(source.attempt_count),
  };
}

function validateCurrentIdentity({ scan, project, identity, scanResult }) {
  if (
    cleanId(scan.id) !== identity.scan_id
    || cleanId(scan.project_id) !== identity.project_id
    || !recordOwnedById(scan, identity.owner_user_id)
    || !recordOwnedById(project, identity.owner_user_id)
    || normalizeDomain(scan.website_url || scan.submitted_url) !== identity.normalized_domain
    || normalizeDomain(project.website_url) !== identity.normalized_domain
    || cleanId(scanResult.scan_id || scanResult.scan_run_id) !== identity.scan_id
    || cleanId(scanResult.request_id) !== identity.request_id
    || cleanId(scanResult.idempotency_key || scanResult.request_id) !== identity.idempotency_key
    || normalizeDomain(scanResult.final_url || scanResult.website_url || scanResult.submitted_url) !== identity.normalized_domain
  ) {
    throw new RequestProblem(409, "authority_identity_mismatch", "The durable completion no longer matches this owner-bound scan.");
  }
}

async function upsertSingleFixList(entities, desired, identity, scan) {
  const existing = await entities.FixList.filter({
    scan_run_id: identity.scan_id,
    owner_user_id: identity.owner_user_id,
  }, "-created_date", MAX_FIX_ITEMS);
  const rows = Array.isArray(existing) ? existing.filter((row) => row?.id) : [];
  const preferredId = String(scan?.fix_list_id || "");
  const current = rows.find((row) => String(row.id) === preferredId)
    || [...rows].sort((a, b) => String(a.id).localeCompare(String(b.id)))[0]
    || null;

  if (!current?.id) return entities.FixList.create(desired);

  for (const duplicate of rows) {
    if (duplicate.id === current.id) continue;
    const duplicateItems = await entities.FixItem.filter(
      { fix_list_id: duplicate.id },
      "created_date",
      MAX_FIX_ITEMS,
    );
    for (const item of duplicateItems || []) {
      if (item?.id) await entities.FixItem.delete(item.id);
    }
    await entities.FixList.delete(duplicate.id);
  }

  const updated = await entities.FixList.update(current.id, desired);
  return { ...current, ...(updated || {}), id: current.id };
}

async function reconcileFixItems(entities, fixListId, desiredRows) {
  const existing = await entities.FixItem.filter(
    { fix_list_id: fixListId },
    "created_date",
    MAX_FIX_ITEMS,
  );
  const groups = new Map();
  for (const item of existing || []) {
    const key = String(item?.fix_id || "");
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(item);
  }
  const desiredIds = new Set(desiredRows.map((row) => String(row.fix_id || "")));

  for (const [fixId, items] of groups) {
    if (!desiredIds.has(fixId)) {
      for (const item of items) if (item?.id) await entities.FixItem.delete(item.id);
      continue;
    }
    for (const duplicate of items.slice(1)) {
      if (duplicate?.id) await entities.FixItem.delete(duplicate.id);
    }
  }

  for (const row of desiredRows) {
    const current = groups.get(String(row.fix_id || ""))?.[0];
    if (current?.id) await entities.FixItem.update(current.id, row);
    else await entities.FixItem.create(row);
  }
}

async function assertAttemptStillActive(entities, scanId, claimedAttempt) {
  const current = await entities.ScanRun.get(scanId).catch(() => null);
  if (!current || normalizeAttempt(current.attempt_count) !== claimedAttempt) {
    throw new RequestProblem(409, "superseded_attempt", "A newer attempt owns this scan.");
  }
  if (["complete", "limited", "failed", "cancelled"].includes(String(current.status || "").toLowerCase())) {
    throw new RequestProblem(409, "terminal_authority_rejected", "This scan attempt is already terminal.");
  }
}

function stableTimestamp(scan) {
  for (const value of [scan?.started_at, scan?.queued_at, scan?.created_date]) {
    if (Number.isFinite(Date.parse(String(value || "")))) return new Date(value).toISOString();
  }
  throw new RequestProblem(409, "scan_timestamp_missing", "The durable scan timestamp is unavailable.");
}

function recordOwnedById(record, ownerId) {
  const owner = cleanId(ownerId);
  return Boolean(owner && (
    cleanId(record?.owner_user_id) === owner
    || cleanId(record?.created_by_id) === owner
  ));
}

function objectValue(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
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

function cleanProof(value) {
  const proof = cleanText(value, 64).toLowerCase();
  return /^[a-f0-9]{64}$/.test(proof) ? proof : "";
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
