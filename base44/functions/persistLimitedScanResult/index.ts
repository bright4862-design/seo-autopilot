import { createClientFromRequest } from "npm:@base44/sdk@0.8.40";
import { verifyAuthoritySeal } from "./workerEnvelope.js";
import {
  buildLimitedResultSnapshot,
  createLimitedResultProof,
  limitedRowsFromSnapshot,
  MAX_LIMITED_FIXES,
} from "./limitedResultIntegrity.js";

/**
 * Persist a scan that saw real evidence but not enough to be authoritative.
 *
 * Deliberately a separate package from persistDurableScanAuthority. Branching
 * that function to accept provisional data would put the authority seal one
 * boolean away from covering a scan that is not authoritative; here there is no
 * authority path to weaken, because none exists in this file.
 */

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
    return problemResponse(new RequestProblem(405, "method_not_allowed", "Use POST to persist a limited scan result."));
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
    const sealedAt = cleanText(scan.result_integrity_sealed_at, 80) || stableTimestamp(scan);
    const snapshot = buildLimitedResultSnapshot({
      identity,
      scan: { ...scanResult, worker_source_sha: cleanText(body?.worker_source_sha, 80) },
      review,
      now: sealedAt,
    });
    if (!snapshot.eligible_for_limited_result) {
      throw new RequestProblem(409, "limited_result_has_no_evidence", "There is no useful evidence to persist.");
    }
    const integrityProof = await createLimitedResultProof(snapshot, secret);

    if (scanStatus === "limited" && cleanProof(scan.result_integrity_proof) === integrityProof && scan.fix_list_id) {
      return Response.json({
        success: true,
        replayed: true,
        workerVersion: WORKER_VERSION,
        scanId: identity.scan_id,
        fixListId: scan.fix_list_id,
        resultIntegrityVerified: true,
        scanRun: scan,
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

    return Response.json({
      success: true,
      replayed: false,
      workerVersion: WORKER_VERSION,
      scanId: identity.scan_id,
      fixListId: fixList.id,
      resultIntegrityVerified: true,
      scanRun: persistedScan,
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
