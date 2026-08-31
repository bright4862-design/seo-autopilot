import { createClientFromRequest } from "npm:@base44/sdk@0.8.41";
import {
  buildLimitedResultSnapshot,
  verifyLimitedResultProof,
} from "./limitedResultIntegrity.js";
import {
  authoritySnapshotFromRows,
  buildCustomerProjection,
  buildScanHistoryProjection,
  evaluatePaidAccess,
  recordOwnedByUser,
  verifyAuthoritySeal,
} from "./projection.js";

// Every seal version the writer has ever produced, because a reader pinned to
// one of them turns intact results into "This scan has no verified result".
// Reconstruction is version-dispatched per row, so both shapes verify.
const ACCEPTED_AUTHORITY_VERSIONS = new Set([
  "standard_review_snapshot_hmac_v1",
  "standard_review_snapshot_hmac_v2_coverage",
  "standard_review_snapshot_hmac_v3_acceptance_evidence",
]);
const ACCEPTED_LIMITED_INTEGRITY_VERSIONS = new Set([
  "standard_limited_result_integrity_v1",
  "standard_limited_result_integrity_v2_acceptance_evidence",
]);
import { RELEASE_FINGERPRINT } from "./generatedReleaseContract.js";
import { isReadableAuthorityReleaseFingerprint } from "./releaseCompatibility.js";
const BASE44_HANDLER_RELEASE_FINGERPRINT = "ad3c2b0a8185ee41";
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
    if (RELEASE_FINGERPRINT !== BASE44_HANDLER_RELEASE_FINGERPRINT) {
      throw new RequestProblem(503, "customer_result_release_activation_mismatch", "Server customer-result release activation is inconsistent.");
    }
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
    if (action === "list_all") {
      return await listAllCustomerScans({ serviceEntities, user, body });
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

    // A limited result is a real, verified record of a scan that saw useful
    // evidence but not enough to be authoritative. It is verified against its
    // own integrity domain -- never the authority seal -- and is returned with
    // authority_verified false so nothing downstream can promote it.
    if (run.status === "limited") {
      const integrityProof = cleanProof(run.result_integrity_proof);
      if (
        !integrityProof
        || !ACCEPTED_LIMITED_INTEGRITY_VERSIONS.has(cleanText(run.result_integrity_version, 160))
        || run.release_gate_eligible === true
        || cleanProof(run.authority_proof)
      ) {
        throw new RequestProblem(409, "limited_result_invalid", "This saved result could not be verified.");
      }
      const limitedFixList = await loadLimitedFixList(serviceEntities.FixList, run, user, integrityProof);
      const limitedFixItems = await loadLimitedFixItems(serviceEntities.FixItem, limitedFixList, run, integrityProof);
      const limitedIntegrityVersion = cleanText(run.result_integrity_version, 160);
      const limitedUsesAcceptanceEvidence =
        limitedIntegrityVersion === "standard_limited_result_integrity_v2_acceptance_evidence";
      const limitedSnapshot = buildLimitedResultSnapshot({
        identity: {
          scan_id: run.id,
          project_id: run.project_id,
          owner_user_id: user.id,
          request_id: run.request_id,
          attempt_count: run.attempt_count,
          normalized_domain: run.normalized_domain,
        },
        scan: run,
        review: {
          scan_status: run.scan_status,
          health_score: run.health_score,
          health_grade: run.health_grade,
          limitation: run.limitation || run.status_detail,
          // These base fields are part of the historical signed shape. Never
          // derive them from later diagnostic objects when reopening v1 rows.
          coverage_state: run.coverage_state,
          coverage_reasons: run.coverage_reasons,
          coverage_authority_version: run.coverage_authority_version,
          ...(limitedUsesAcceptanceEvidence ? {
            coverage_authority_evidence: run.coverage_authority_evidence,
            classification_integrity: run.classification_integrity,
            classification_verdict: run.classification_verdict,
          } : {}),
          recommendations: limitedFixItems,
        },
        now: cleanText(run.result_integrity_sealed_at, 80),
        version: limitedIntegrityVersion,
      });
      const secret = String(Deno.env.get("SCAN_EVIDENCE_SIGNING_KEY") || "");
      if (!secret) {
        throw new RequestProblem(503, "result_authority_unavailable", "Verified results are temporarily unavailable.");
      }
      if (!await verifyLimitedResultProof(limitedSnapshot, secret, integrityProof)) {
        throw new RequestProblem(409, "limited_result_invalid", "This saved result no longer matches its integrity proof.");
      }
      return Response.json(buildCustomerProjection({
        run,
        fixList: limitedFixList,
        fixItems: limitedFixItems,
        fullAccess: true,
        authorityVerified: false,
        resultIntegrityVerified: true,
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
      || !ACCEPTED_AUTHORITY_VERSIONS.has(cleanText(run.authority_seal_version, 160))
      || !cleanText(run.authority_sealed_at, 80)
      || run.release_gate_eligible !== true
      || run.score_is_provisional === true
      || run.evidence_quality_blocking === true
    ) {
      throw new RequestProblem(409, "result_not_authoritative", "This scan did not produce a verified customer result.");
    }
    const runReleaseFingerprint = cleanText(run.beta_revision_fingerprint, 64);
    // Unknown scanner releases remain hidden until the reader explicitly proves
    // it understands their signed contract. Known-compatible historical results
    // continue through the same full authority verification as current results.
    if (!isReadableAuthorityReleaseFingerprint(runReleaseFingerprint, RELEASE_FINGERPRINT)) {
      throw new RequestProblem(
        503,
        "result_release_mismatch",
        "Saved results are temporarily unavailable while a release update completes.",
      );
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

/**
 * Record an error that is about to be replaced by a customer-safe problem.
 *
 * The top-level handler returns a RequestProblem before it reaches its own
 * console.error, so an error converted here leaves no server-side trace at all.
 * That is how a saved-scan read failure reached a customer as a support
 * reference that could not be explained from either side.
 *
 * Bounded, non-payload fields only, matching the logging posture used elsewhere
 * in these functions: a raw driver message is never recorded.
 */
function logReplacedReadError(scope, error) {
  console.error("getCustomerScanResult read failed", {
    scope: String(scope || "unknown").slice(0, 40),
    name: String(error?.name || "unknown_error").slice(0, 80),
    code: String(error?.code || "").slice(0, 80),
    status: String(error?.status ?? error?.response?.status ?? "").slice(0, 8),
  });
}

async function listCustomerScans({ serviceEntities, user, body }) {
  const projectId = cleanId(body?.project_id);
  if (!projectId) throw new RequestProblem(400, "project_id_required", "Choose a website project to view saved scans.");
  await loadOwnedProject(serviceEntities.BusinessProject, projectId, user);

  const limit = Math.min(Math.max(nonNegativeInteger(body?.limit) || 3, 1), 3);
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
  } catch (error) {
    logReplacedReadError("list", error);
    throw new RequestProblem(503, "result_load_failed", "Saved scans could not be loaded. Please retry.");
  }

  return Response.json({
    success: true,
    action: "list",
    project_id: projectId,
    runs: buildScanHistoryProjection(rows),
  });
}

async function listAllCustomerScans({ serviceEntities, user, body }) {
  const limit = Math.min(Math.max(nonNegativeInteger(body?.limit) || 20, 1), 30);
  let rows;
  try {
    const [owned, legacy] = await Promise.all([
      serviceEntities.ScanRun.filter(
        { owner_user_id: cleanId(user.id) },
        "-queued_at",
        limit,
      ),
      serviceEntities.ScanRun.filter(
        { created_by_id: cleanId(user.id) },
        "-queued_at",
        limit,
      ),
    ]);
    rows = uniqueRows([...(owned || []), ...(legacy || [])])
      .filter((run) => recordOwnedByUser(run, user.id))
      .sort((left, right) => scanTimestamp(right) - scanTimestamp(left))
      .slice(0, limit);
  } catch (error) {
    logReplacedReadError("list_all", error);
    throw new RequestProblem(503, "result_load_failed", "Saved scans could not be loaded. Please retry.");
  }
  return Response.json({
    success: true,
    action: "list_all",
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
  } catch (error) {
    logReplacedReadError("access", error);
    throw new RequestProblem(503, "paid_access_unavailable", "Access could not be confirmed. Please retry.");
  }
}

async function loadLimitedFixList(fixListEntity, run, user, proof) {
  const id = cleanId(run.fix_list_id);
  const fixList = id ? await fixListEntity.get(id).catch(() => null) : null;
  if (
    !fixList
    || fixList.is_authoritative === true
    || cleanProof(fixList.result_integrity_proof) !== proof
    || cleanId(fixList.scan_run_id) !== cleanId(run.id)
    || cleanId(fixList.owner_user_id) !== cleanId(user.id)
  ) {
    throw new RequestProblem(409, "limited_result_invalid", "This saved result could not be verified.");
  }
  return fixList;
}

async function loadLimitedFixItems(fixItemEntity, fixList, run, proof) {
  const items = await fixItemEntity
    .filter({ fix_list_id: cleanId(fixList.id) }, "created_date", MAX_FIX_ITEMS)
    .catch(() => []);
  const owned = (items || []).filter((item) => cleanProof(item?.result_integrity_proof) === proof);
  if (owned.length !== (items || []).length) {
    throw new RequestProblem(409, "limited_result_invalid", "This saved result is incomplete.");
  }
  return owned;
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
  } catch (error) {
    logReplacedReadError("fix_list", error);
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
  } catch (error) {
    logReplacedReadError("fix_items", error);
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
  const runReleaseFingerprint = cleanText(run.beta_revision_fingerprint, 64);
  if (
    !ACCEPTED_AUTHORITY_VERSIONS.has(snapshot.version)
    // Accepting a set must not mean accepting a mismatch: the rebuilt snapshot
    // has to carry the same version as the row it was rebuilt from, or the
    // proof would be verified against a payload shape the row never had.
    || snapshot.version !== cleanText(run.authority_seal_version, 160)
    || snapshot.owner_user_id !== cleanId(user.id)
    || snapshot.scan_id !== cleanId(run.id)
    || snapshot.project_id !== cleanId(run.project_id)
    || !isReadableAuthorityReleaseFingerprint(runReleaseFingerprint, RELEASE_FINGERPRINT)
    || snapshot.release_fingerprint !== runReleaseFingerprint
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
