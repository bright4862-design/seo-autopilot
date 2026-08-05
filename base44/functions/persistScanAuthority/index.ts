import { createClient, createClientFromRequest } from "npm:@base44/sdk";
import { verifyAuthoritySeal } from "./authoritySeal.js";
import { authorityRowsFromSnapshot, missingAuthorityFixRows } from "./authorityRows.js";

const REVIEW_ATTESTATION_VERSION = "standard_review_snapshot_hmac_v1";
const EXPECTED_RELEASE_FINGERPRINT = "51c813a6219b4e70";
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
  if (req.method !== "POST") return problemResponse(new RequestProblem(405, "method_not_allowed", "Use POST to persist scan authority."));
  const base44 = createClientFromRequest(req);
  const user = await base44.auth.me().catch(() => null);
  if (!user?.id) return problemResponse(new RequestProblem(401, "unauthorized", "Sign in before saving a scan."));

  try {
    const serviceBase44 = createServiceOnlyClient(req);
    const serviceEntities = serviceBase44.asServiceRole.entities;
    const body = await req.json().catch(() => ({}));
    const scanId = cleanId(body?.scan_id || body?.scan_run_id);
    const attestation = body?.attestation;
    if (!scanId || !attestation || typeof attestation !== "object") {
      throw new RequestProblem(400, "authority_attestation_required", "A server review attestation is required.");
    }
    if (attestation.version !== REVIEW_ATTESTATION_VERSION || attestation.snapshot?.version !== REVIEW_ATTESTATION_VERSION) {
      throw new RequestProblem(409, "authority_attestation_invalid", "The review attestation version is invalid.");
    }

    const secret = String(Deno.env.get("SCAN_EVIDENCE_SIGNING_KEY") || "");
    if (!secret) throw new RequestProblem(503, "authority_not_configured", "Server scan authority is not configured.");
    if (!await verifyAuthoritySeal(attestation.snapshot, secret, attestation.proof)) {
      throw new RequestProblem(409, "authority_attestation_invalid", "The server review attestation could not be verified.");
    }

    const snapshot = validateSnapshot(attestation.snapshot, { scanId, user });
    const scan = await getOwnedRecord(base44.entities.ScanRun, scanId, user);
    const project = await getOwnedRecord(base44.entities.BusinessProject, snapshot.project_id, user);
    if (
      cleanId(scan.project_id) !== snapshot.project_id
      || normalizeDomain(scan.website_url || scan.submitted_url) !== snapshot.normalized_domain
      || normalizeDomain(project.website_url) !== snapshot.normalized_domain
    ) {
      throw new RequestProblem(409, "authority_identity_mismatch", "The attested review no longer matches this project.");
    }
    if (scan.authority_proof && scan.authority_proof !== attestation.proof) {
      throw new RequestProblem(409, "authority_conflict", "This scan already has a different server authority seal.");
    }
    const replayed = scan.authority_proof === attestation.proof;

    const unsignedRows = authorityRowsFromSnapshot(snapshot, {
      ownerUserId: user.id,
      proof: attestation.proof,
    });
    const existingFixLists = await serviceEntities.FixList.filter({
      scan_run_id: scanId,
      owner_user_id: String(user.id),
      authority_proof: String(attestation.proof).toLowerCase(),
    }, "-created_date", 2);
    const fixList = existingFixLists?.[0]
      || await serviceEntities.FixList.create(unsignedRows.fixList);
    if (!fixList?.id) throw new RequestProblem(500, "authority_persistence_failed", "The authoritative FixList could not be saved.");

    if (snapshot.recommendations.length > 0) {
      const rows = authorityRowsFromSnapshot(snapshot, {
        fixListId: fixList.id,
        ownerUserId: user.id,
        proof: attestation.proof,
      });
      const existingItems = await serviceEntities.FixItem.filter({
        fix_list_id: fixList.id,
        authority_proof: String(attestation.proof).toLowerCase(),
      }, "created_date", MAX_FIX_ITEMS);
      const missingItems = missingAuthorityFixRows(rows.fixItems, existingItems);
      if (missingItems.length > 0) await serviceEntities.FixItem.bulkCreate(missingItems);
    }

    const authorityFields = authorityRowsFromSnapshot(snapshot, {
      fixListId: fixList.id,
      ownerUserId: user.id,
      proof: attestation.proof,
    }).scanRun;
    await serviceEntities.ScanRun.update(scanId, authorityFields);

    const expectedProof = String(attestation.proof).toLowerCase();
    const persistedScan = await serviceEntities.ScanRun.get(scanId);
    const persistedFixList = await serviceEntities.FixList.get(fixList.id);
    const persistedItems = snapshot.recommendations.length > 0
      ? await serviceEntities.FixItem.filter({
        fix_list_id: fixList.id,
        authority_proof: expectedProof,
      }, "created_date", MAX_FIX_ITEMS)
      : [];
    const authorityPersisted = Boolean(
      persistedScan?.authority_proof === expectedProof
      && persistedScan?.authority_seal_version === snapshot.version
      && persistedScan?.authority_sealed_at === snapshot.sealed_at
      && persistedScan?.fix_list_id === fixList.id
      && persistedScan?.release_gate_eligible === true
      && persistedFixList?.authority_proof === expectedProof
      && persistedFixList?.is_authoritative === true
      && persistedItems.length === snapshot.recommendations.length
      && persistedItems.every((item) => item?.authority_proof === expectedProof)
    );
    if (!authorityPersisted) {
      throw new RequestProblem(500, "authority_persistence_incomplete", "The server authority seal was not durably stored.");
    }

    return Response.json({
      success: true,
      replayed,
      requestId: cleanId(scan.request_id),
      scanId,
      fixListId: fixList.id,
      scanRun: persistedScan,
    });
  } catch (error) {
    if (error instanceof RequestProblem) return problemResponse(error);
    console.error("persistScanAuthority failed", error instanceof Error ? error.name : "unknown_error");
    return problemResponse(new RequestProblem(500, "authority_persistence_failed", "The authoritative scan could not be saved."));
  }
});


function createServiceOnlyClient(req: Request) {
  const serviceAuthorization = String(req.headers.get("Base44-Service-Authorization") || "");
  const appId = cleanId(req.headers.get("Base44-App-Id"));
  if (!appId || !serviceAuthorization.startsWith("Bearer ") || serviceAuthorization.split(" ").length !== 2) {
    throw new RequestProblem(500, "authority_service_role_unavailable", "Server authority storage is unavailable.");
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

function validateSnapshot(value, { scanId, user }) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new RequestProblem(409, "authority_snapshot_invalid", "The authoritative review snapshot is invalid.");
  }
  const snapshot = value;
  const sealedAt = Date.parse(snapshot.sealed_at || "");
  if (
    snapshot.version !== REVIEW_ATTESTATION_VERSION
    || cleanId(snapshot.owner_user_id) !== cleanId(user.id)
    || cleanId(snapshot.scan_id) !== scanId
    || !cleanId(snapshot.project_id)
    || !normalizeDomain(snapshot.normalized_domain)
    || snapshot.release_fingerprint !== EXPECTED_RELEASE_FINGERPRINT
    || !Number.isFinite(sealedAt)
  ) {
    throw new RequestProblem(409, "authority_snapshot_invalid", "The authoritative review snapshot identity is invalid.");
  }
  if (
    snapshot.scan?.status !== "complete"
    || snapshot.scan?.release_gate_eligible !== true
    || snapshot.scan?.score_is_provisional === true
    || snapshot.scan?.evidence_quality_blocking === true
    || snapshot.scan?.beta_revision_fingerprint !== EXPECTED_RELEASE_FINGERPRINT
    || snapshot.fix_list?.is_authoritative !== true
    || snapshot.fix_list?.score_is_provisional === true
  ) {
    throw new RequestProblem(409, "authority_snapshot_not_eligible", "The review snapshot is not release-authoritative.");
  }

  const recommendations = Array.isArray(snapshot.recommendations) ? snapshot.recommendations : [];
  if (recommendations.length > MAX_FIX_ITEMS || Number(snapshot.fix_list?.total_fixes) !== recommendations.length) {
    throw new RequestProblem(409, "authority_snapshot_invalid", "The authoritative recommendations are incomplete.");
  }
  const ids = new Set();
  for (const fix of recommendations) {
    const id = cleanId(fix?.fix_id);
    if (!id || ids.has(id) || !cleanText(fix?.issue_title, 500)) {
      throw new RequestProblem(409, "authority_snapshot_invalid", "The authoritative recommendations contain an invalid identity.");
    }
    ids.add(id);
  }
  return snapshot;
}

async function getOwnedRecord(entity, id, user) {
  try {
    const record = await entity.get(id);
    if (record && recordOwnedBy(record, user)) return record;
  } catch {
    // Return the same not-found boundary for inaccessible records.
  }
  throw new RequestProblem(404, "authority_record_not_found", "The attested scan project was not found.");
}

function recordOwnedBy(record, user) {
  const userId = cleanId(user?.id);
  const userEmail = cleanText(user?.email, 320).toLowerCase();
  return Boolean(userId && (
    cleanId(record?.owner_user_id) === userId
    || cleanId(record?.created_by_id) === userId
    || (userEmail && cleanText(record?.created_by, 320).toLowerCase() === userEmail)
  ));
}

function normalizeDomain(value) {
  const raw = cleanText(value, 2_000);
  if (!raw) return "";
  try {
    const parsed = new URL(/^https?:\/\//i.test(raw) ? raw : `https://${raw}`);
    return ["http:", "https:"].includes(parsed.protocol) ? parsed.hostname.toLowerCase().replace(/^www\./, "").replace(/\.$/, "") : "";
  } catch {
    return "";
  }
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
