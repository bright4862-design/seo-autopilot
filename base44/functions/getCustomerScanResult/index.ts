import { createClientFromRequest } from "npm:@base44/sdk@0.8.41";
import {
  authoritySnapshotFromRows,
  buildCustomerProjection,
  buildScanHistoryProjection,
  evaluatePaidAccess,
  recordOwnedByUser,
  verifyAuthoritySeal,
} from "./projection.js";

const AUTHORITY_VERSION = "standard_review_snapshot_hmac_v1";
const RELEASE_FINGERPRINT = "03dbfa67f4b708cf";
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
    return problemResponse(new RequestProblem(405, "method_not_allowed", "Use POST to load a saved scan."));
  }

  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me().catch(() => null);
    if (!user?.id || !user?.email) {
      throw new RequestProblem(401, "unauthorized", "Sign in to open this scan.");
    }

    const body = unwrapBody(await req.json().catch(() => ({})));
    const action = cleanText(body?.action || "get", 20).toLowerCase();
    const serviceEntities = base44.asServiceRole.entities;
    if (action === "list") {
      return await listCustomerScans({ serviceEntities, user, body });
    }
    if (action !== "get") {
      throw new RequestProblem(400, "result_action_invalid", "Choose one supported saved-scan action.");
    }

    const scanId = cleanId(body?.scan_id || body?.scan_run_id);
    if (!scanId) throw new RequestProblem(400, "scan_id_required", "Choose a saved scan to continue.");

    // ScanRun is always service-read and then explicitly owner-bound. This is
    // required before its entity RLS becomes admin-only and avoids treating a
    // caller-scoped read as the confidentiality boundary for paid fields.
    const run = await serviceEntities.ScanRun.get(scanId).catch(() => null);
    const exactOwner = cleanId(run?.owner_user_id) === cleanId(user.id);
    const legacyOwner = !cleanId(run?.owner_user_id)
      && recordOwnedByUser(run, user.id);
    if (!run || cleanId(run.id) !== scanId || (!exactOwner && !legacyOwner)) {
      throw new RequestProblem(404, "scan_not_found", "This scan is not available to this account.");
    }

    const project = await loadOwnedProject(serviceEntities.BusinessProject, run.project_id, user);
    if (normalizeDomain(project.website_url) !== normalizeDomain(run.normalized_domain || run.website_url)) {
      throw new RequestProblem(409, "result_authority_invalid", "This saved scan no longer matches its website project.");
    }

    // Legacy rows without the explicit owner field may expose progress only.
    // Paid sealed content always requires exact current ownership on both
    // ScanRun and BusinessProject.
    if (!exactOwner || cleanId(project.owner_user_id) !== cleanId(user.id)) {
      return Response.json(buildCustomerProjection({
        run,
        fixList: null,
        fixItems: [],
        fullAccess: false,
        authorityVerified: false,
      }));
    }

    const accessRows = await loadAccessRows(serviceEntities.Access, user);
    const access = evaluatePaidAccess({ rows: accessRows, user });
    if (!access.ok && access.failureCode === "paid_access_conflict") {
      throw new RequestProblem(409, "paid_access_conflict", "Your access record needs support before this result can open.");
    }
    if (!access.ok) {
      return Response.json(buildCustomerProjection({
        run,
        fixList: null,
        fixItems: [],
        fullAccess: false,
        authorityVerified: false,
      }));
    }

    // Full access does not make staged or failed content authoritative. These
    // states intentionally return progress metadata and no FixItems.
    if (run.status !== "complete") {
      return Response.json(buildCustomerProjection({
        run,
        fixList: null,
        fixItems: [],
        fullAccess: true,
        authorityVerified: false,
      }));
    }

    const proof = cleanProof(run.authority_proof);
    if (
      !proof
      || run.authority_seal_version !== AUTHORITY_VERSION
      || !cleanText(run.authority_sealed_at, 80)
      || run.release_gate_eligible !== true
      || run.score_is_provisional === true
      || run.evidence_quality_blocking === true
      || run.beta_revision_fingerprint !== RELEASE_FINGERPRINT
    ) {
      throw new RequestProblem(409, "result_not_authoritative", "This scan did not produce a verified customer result.");
    }

    const fixList = await loadFixList(serviceEntities.FixList, run, user, proof);
    const fixItems = await loadFixItems(serviceEntities.FixItem, fixList, run, user, proof);
    const snapshot = authoritySnapshotFromRows({ run, fixList, fixItems, userId: user.id });
    assertSnapshotIdentity(snapshot, { run, fixList, user });

    // Authority proof must be verified with the exact same secret bytes used
    // by persistDurableScanAuthority. Do not trim or normalize this value:
    // whitespace is part of an HMAC key and changing it invalidates every seal.
    const secret = String(Deno.env.get("SCAN_EVIDENCE_SIGNING_KEY") || "");
    if (!secret) {
      throw new RequestProblem(503, "result_authority_unavailable", "Verified results are temporarily unavailable.");
    }
    if (!await verifyAuthoritySeal(snapshot, secret, proof)) {
      throw new RequestProblem(409, "result_authority_invalid", "This saved result no longer matches its server authority seal.");
    }

    return Response.json(buildCustomerProjection({
      run,
      fixList,
      fixItems,
      fullAccess: true,
      authorityVerified: true,
    }));
  } catch (error) {
    if (error instanceof RequestProblem) return problemResponse(error);
    console.error("getCustomerScanResult failed", error instanceof Error ? error.name : "unknown_error");
    return problemResponse(new RequestProblem(500, "result_load_failed", "This saved result could not be loaded."));
  }
});

async function listCustomerScans({ serviceEntities, user, body }) {
  const projectId = cleanId(body?.project_id);
  if (!projectId) throw new RequestProblem(400, "project_id_required", "Choose a website project to view saved scans.");
  await loadOwnedProject(serviceEntities.BusinessProject, projectId, user);

  const limit = Math.min(Math.max(nonNegativeInteger(body?.limit) || 8, 1), 20);
  let rows;
  try {
    const [owned, legacy] = await Promise.all([
      serviceEntities.ScanRun.filter(
        { project_id: projectId, owner_user_id: cleanId(user.id) },
        "-queued_at",
        limit,
      ),
      serviceEntities.ScanRun.filter(
        { project_id: projectId, created_by_id: cleanId(user.id) },
        "-queued_at",
        limit,
      ),
    ]);
    rows = uniqueRows([...(owned || []), ...(legacy || [])])
      .filter((run) => recordOwnedByUser(run, user.id))
      .sort((left, right) => scanTimestamp(right) - scanTimestamp(left))
      .slice(0, limit);
  } catch {
    throw new RequestProblem(503, "result_load_failed", "Saved scans could not be loaded. Please retry.");
  }

  return Response.json({
    success: true,
    action: "list",
    project_id: projectId,
    runs: buildScanHistoryProjection(rows),
  });
}

async function loadOwnedProject(projectEntity, projectIdValue, user) {
  const projectId = cleanId(projectIdValue);
  if (!projectId) throw new RequestProblem(409, "result_authority_invalid", "This scan is missing its website project.");
  const project = await projectEntity.get(projectId).catch(() => null);
  if (!project || cleanId(project.id) !== projectId || !recordOwnedByUser(project, user.id)) {
    throw new RequestProblem(404, "scan_not_found", "This scan is not available to this account.");
  }
  return project;
}

async function loadAccessRows(accessEntity, user) {
  const userId = cleanId(user?.id);
  const email = cleanText(user?.email, 320).toLowerCase();
  try {
    const [byUser, byEmail] = await Promise.all([
      accessEntity.filter({ owner_user_id: userId }),
      accessEntity.filter({ user_email: email }),
    ]);
    return [...(byUser || []), ...(byEmail || [])];
  } catch {
    throw new RequestProblem(503, "paid_access_unavailable", "Access could not be confirmed. Please retry.");
  }
}

async function loadFixList(fixListEntity, run, user, proof) {
  let fixList = null;
  try {
    if (cleanId(run.fix_list_id)) {
      fixList = await fixListEntity.get(cleanId(run.fix_list_id));
    } else {
      const matches = await fixListEntity.filter({
        scan_run_id: cleanId(run.id),
        project_id: cleanId(run.project_id),
        owner_user_id: cleanId(user.id),
        authority_proof: proof,
      }, "-generated_at", 2);
      fixList = matches?.[0] || null;
    }
  } catch {
    throw new RequestProblem(409, "fix_list_unavailable", "The verified FixList for this scan is unavailable.");
  }
  if (
    !fixList
    || cleanId(fixList.id) !== cleanId(run.fix_list_id)
    || cleanId(fixList.owner_user_id) !== cleanId(user.id)
    || cleanId(fixList.scan_run_id) !== cleanId(run.id)
    || cleanId(fixList.project_id) !== cleanId(run.project_id)
    || cleanProof(fixList.authority_proof) !== proof
    || fixList.is_authoritative !== true
    || normalizeDomain(fixList.website_url) !== normalizeDomain(run.website_url)
  ) {
    throw new RequestProblem(409, "fix_list_mismatch", "The saved FixList does not match this verified scan.");
  }
  return fixList;
}

async function loadFixItems(fixItemEntity, fixList, run, user, proof) {
  let items;
  try {
    items = await fixItemEntity.filter({
      fix_list_id: cleanId(fixList.id),
      scan_run_id: cleanId(run.id),
      project_id: cleanId(run.project_id),
      owner_user_id: cleanId(user.id),
      authority_proof: proof,
    }, "created_date", MAX_FIX_ITEMS);
  } catch {
    throw new RequestProblem(409, "fix_items_unavailable", "The verified recommendations for this scan are unavailable.");
  }

  const expectedCount = nonNegativeInteger(fixList.total_fixes);
  if (!Array.isArray(items) || items.length !== expectedCount || items.length > MAX_FIX_ITEMS) {
    throw new RequestProblem(409, "fix_items_incomplete", "The saved recommendations are incomplete.");
  }
  for (const item of items) {
    if (
      cleanId(item.owner_user_id) !== cleanId(user.id)
      || cleanId(item.fix_list_id) !== cleanId(fixList.id)
      || cleanId(item.scan_run_id) !== cleanId(run.id)
      || cleanId(item.project_id) !== cleanId(run.project_id)
      || cleanProof(item.authority_proof) !== proof
    ) {
      throw new RequestProblem(409, "fix_items_mismatch", "The saved recommendations do not match this verified scan.");
    }
  }
  return items;
}

function assertSnapshotIdentity(snapshot, { run, fixList, user }) {
  if (
    snapshot.version !== AUTHORITY_VERSION
    || snapshot.owner_user_id !== cleanId(user.id)
    || snapshot.scan_id !== cleanId(run.id)
    || snapshot.project_id !== cleanId(run.project_id)
    || snapshot.release_fingerprint !== RELEASE_FINGERPRINT
    || snapshot.normalized_domain !== normalizeDomain(run.normalized_domain || run.website_url)
    || snapshot.scan?.status !== "complete"
    || snapshot.scan?.release_gate_eligible !== true
    || snapshot.scan?.score_is_provisional === true
    || snapshot.scan?.evidence_quality_blocking === true
    || snapshot.fix_list?.is_authoritative !== true
    || snapshot.fix_list?.total_fixes !== nonNegativeInteger(fixList.total_fixes)
    || snapshot.recommendations.length !== nonNegativeInteger(fixList.total_fixes)
  ) {
    throw new RequestProblem(409, "result_authority_invalid", "This saved result no longer matches its server authority seal.");
  }
}

function unwrapBody(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  if (value.data && typeof value.data === "object" && !Array.isArray(value.data)) return value.data;
  return value;
}

function cleanId(value) {
  return cleanText(value, 160);
}

function cleanText(value, limit) {
  return typeof value === "string" ? value.trim().slice(0, limit) : "";
}

function cleanProof(value) {
  const proof = cleanText(value, 64).toLowerCase();
  return /^[a-f0-9]{64}$/.test(proof) ? proof : "";
}

function nonNegativeInteger(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(0, Math.trunc(parsed)) : 0;
}

function uniqueRows(rows) {
  return Array.from(new Map(
    (Array.isArray(rows) ? rows : [])
      .filter((row) => cleanId(row?.id))
      .map((row) => [cleanId(row.id), row]),
  ).values());
}

function scanTimestamp(run) {
  // "Newest scan" means when the scan was created/queued, not when an older
  // orphan was later cancelled or reconciled. Completion time must not make
  // stale history jump ahead of genuinely newer runs.
  for (const value of [run?.queued_at, run?.created_date, run?.started_at, run?.reviewing_at, run?.completed_at]) {
    const parsed = Date.parse(cleanText(value, 80));
    if (Number.isFinite(parsed)) return parsed;
  }
  return 0;
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

function problemResponse(error) {
  return Response.json({
    success: false,
    error_code: error.code,
    error: error.message,
  }, { status: error.status });
}
