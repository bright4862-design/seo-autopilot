import { createClient } from "npm:@base44/sdk";
import { createAuthoritySeal, verifyAuthoritySeal } from "./authoritySeal.js";
import { authorityRowsFromSnapshot } from "./authorityRows.js";
import { buildAuthoritySnapshot, isAuthorityEligible } from "./authoritySnapshot.js";

const WORKER_VERSION = "scan_job_worker_v1_cloud_tasks";
const COMPLETION_VERSION = "durable_standard150_completion_v1";
const MAX_FIX_ITEMS = 100;
const FREE_SCAN_CONSUMED_VALUE = 1;

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
    const serviceBase44 = createServiceOnlyClient(req);
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

    if (!isAuthorityEligible(scanResult, review)) {
      throw new RequestProblem(409, "authority_snapshot_not_eligible", "The reviewed scan is not release-authoritative.");
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
    if (scan.authority_proof && scan.authority_proof !== authorityProof) {
      throw new RequestProblem(409, "authority_conflict", "This scan already has a different authority seal.");
    }
    const replayed = scan.authority_proof === authorityProof;

    const rowsWithoutListId = authorityRowsFromSnapshot(snapshot, {
      ownerUserId: identity.owner_user_id,
      proof: authorityProof,
    });
    const fixList = await upsertSingleFixList(entities, rowsWithoutListId.fixList, identity);
    if (!fixList?.id) throw new RequestProblem(500, "authority_persistence_failed", "The authoritative FixList could not be saved.");

    const rows = authorityRowsFromSnapshot(snapshot, {
      fixListId: fixList.id,
      ownerUserId: identity.owner_user_id,
      proof: authorityProof,
    });
    await reconcileFixItems(entities, fixList.id, rows.fixItems);

    // Stage the exact authority proof while the run remains non-terminal. This
    // makes retries safe and lets us verify every authoritative row before any
    // allowance is consumed.
    const stagedScanFields = {
      ...rows.scanRun,
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

    // The current product has one free scan. Set the allowance to at least one
    // rather than incrementing it, so a retry cannot charge twice.
    const allowance = await ensureAllowanceConsumed(entities, scan);
    if (!allowance.ok) {
      throw new RequestProblem(500, "allowance_persistence_failed", "The authoritative result was staged but its allowance state could not be verified.");
    }

    // Only after authority and allowance are both verified does the ScanRun
    // become a terminal, release-eligible result.
    await entities.ScanRun.update(identity.scan_id, rows.scanRun);
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

    return Response.json({
      success: true,
      replayed,
      workerVersion: WORKER_VERSION,
      scanId: identity.scan_id,
      fixListId: fixList.id,
      allowanceConsumed: allowance.consumed,
      scanRun: persistedScan,
    });
  } catch (error) {
    if (error instanceof RequestProblem) return problemResponse(error);
    console.error("persistDurableScanAuthority failed", error instanceof Error ? error.name : "unknown_error");
    return problemResponse(new RequestProblem(500, "durable_authority_failed", "The durable scan authority could not be saved."));
  }
});

function createServiceOnlyClient(req: Request) {
  if (String(req.headers.get("X-FixList-Worker") || "") !== WORKER_VERSION) {
    throw new RequestProblem(403, "worker_header_invalid", "The durable worker identity is invalid.");
  }
  const serviceAuthorization = String(req.headers.get("Base44-Service-Authorization") || "");
  const appId = cleanId(req.headers.get("Base44-App-Id"));
  if (!appId || !serviceAuthorization.startsWith("Bearer ") || serviceAuthorization.split(" ").length !== 2) {
    throw new RequestProblem(401, "service_auth_required", "A valid Base44 service token is required.");
  }
  const dataEnv = String(req.headers.get("X-Data-Env") || "");
  const headers: Record<string, string> = {};
  if (dataEnv === "dev" || dataEnv === "prod") headers["X-Data-Env"] = dataEnv;
  return createClient({
    serverUrl: req.headers.get("Base44-Api-Url") || "https://base44.app",
    appId,
    serviceToken: serviceAuthorization.slice("Bearer ".length),
    functionsVersion: req.headers.get("Base44-Functions-Version") || undefined,
    headers,
  });
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

async function upsertSingleFixList(entities, desired, identity) {
  const existing = await entities.FixList.filter({
    scan_run_id: identity.scan_id,
    owner_user_id: identity.owner_user_id,
  }, "-created_date", 2);
  if ((existing || []).length > 1) {
    throw new RequestProblem(409, "duplicate_fix_list_conflict", "More than one FixList exists for this ScanRun.");
  }
  const current = existing?.[0];
  if (!current?.id) return entities.FixList.create(desired);
  const updated = await entities.FixList.update(current.id, desired);
  return { ...current, ...(updated || {}), id: current.id };
}

async function reconcileFixItems(entities, fixListId, desiredRows) {
  const existing = await entities.FixItem.filter({ fix_list_id: fixListId }, "created_date", MAX_FIX_ITEMS);
  const existingById = new Map((existing || []).map((item) => [String(item?.fix_id || ""), item]));
  const desiredIds = new Set(desiredRows.map((row) => String(row.fix_id || "")));

  for (const item of existing || []) {
    if (!desiredIds.has(String(item?.fix_id || ""))) await entities.FixItem.delete(item.id);
  }
  for (const row of desiredRows) {
    const current = existingById.get(String(row.fix_id || ""));
    if (current?.id) await entities.FixItem.update(current.id, row);
    else await entities.FixItem.create(row);
  }
}

async function ensureAllowanceConsumed(entities, scan) {
  const email = cleanText(scan?.created_by || scan?.owner_email, 320).toLowerCase();
  if (!email) return { ok: false, consumed: false };
  const rows = await entities.Access.filter({ user_email: email }, "-created_date", 2);
  if ((rows || []).length > 1) return { ok: false, consumed: false };
  const current = rows?.[0];
  if (current?.has_full_access === true) return { ok: true, consumed: false };
  if (current?.id) {
    const used = Math.max(FREE_SCAN_CONSUMED_VALUE, Number(current.scans_used || 0));
    await entities.Access.update(current.id, { scans_used: used });
  } else {
    await entities.Access.create({ user_email: email, scans_used: FREE_SCAN_CONSUMED_VALUE, has_full_access: false });
  }
  const verified = await entities.Access.filter({ user_email: email }, "-created_date", 2);
  const record = verified?.[0];
  return {
    ok: Boolean(record && (record.has_full_access === true || Number(record.scans_used || 0) >= FREE_SCAN_CONSUMED_VALUE)),
    consumed: record?.has_full_access !== true,
  };
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
