import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";
import {
  DRAIN_DELAY_SECONDS,
  enqueueScanDrain,
  enqueueScanJob,
  normalizeAttemptCount,
} from "./cloudTasks.js";
import { evaluatePaidAccess, uniqueAccessRows } from "./entitlement.js";
import {
  betaScanAdmissionPolicy,
  normalizeAdmissionIdentity,
  scanIsTerminal,
} from "./admission.js";
import {
  bindAdmission,
  claimAdmission,
  releaseAdmission,
} from "./admissionClient.js";

const CORS_HEADERS = Object.freeze({
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
});

function corsHeaders() {
  return { ...CORS_HEADERS };
}

function jsonResponse(payload, status = 200) {
  return Response.json(payload, { status, headers: corsHeaders() });
}

const VERSION = "startStandardScanJob_v3_server_admission";
const PUBLIC_SCAN_MODE = "standard_150";
const MAX_PAGES = 150;
const ASYNC_WORKER_BUDGET_MS = 210_000;
const TERMINAL_SCAN_STATUSES = new Set(["complete", "limited", "failed", "cancelled"]);

const CUSTOMER_STATUS_DETAIL: Record<string, string> = {
  paid_access_required: "A paid Standard 150 beta pass is required before this scan can start.",
  paid_access_conflict: "Your access record needs support before this scan can start.",
  durable_worker_not_configured: "The scan worker is not configured yet. No scan was started.",
  invalid_worker_url: "The scan worker is not configured correctly. No scan was started.",
  tasks_credentials_not_configured: "The scan queue is not configured yet. No scan was started.",
  tasks_token_mint_failed: "The scan queue could not authenticate. No scan was started.",
  tasks_unreachable: "The scan queue could not be reached. Please retry.",
  scan_admission_paused: "New beta scans are temporarily paused.",
  scan_admission_configuration_invalid: "The scan admission coordinator is not configured correctly.",
};

export default async function (req: Request): Promise<Response> {
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: corsHeaders() });
  if (req.method !== "POST") {
    return jsonResponse({ success: false, version: VERSION, error: "Method not allowed." }, 405);
  }

  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me().catch(() => null);
    if (!user?.id || !user?.email) {
      return jsonResponse({ success: false, version: VERSION, error: "Unauthorized." }, 401);
    }

    const body = unwrapRequestBody(await safeReadJson(req));
    const identity = resolveRequestIdentity(body);
    if (identity.conflict) {
      return jsonResponse({
        success: false,
        version: VERSION,
        error: "request_id and idempotency_key must match.",
        ...identity.fields,
      }, 409);
    }
    if (!identity.fields.request_id) {
      return jsonResponse({
        success: false,
        version: VERSION,
        error: "A durable request_id is required.",
      }, 400);
    }

    const requestedMode = String(
      body.scan_mode || body.canonical_mode || body.audit_profile || PUBLIC_SCAN_MODE,
    ).trim().toLowerCase();
    if (requestedMode !== PUBLIC_SCAN_MODE) {
      return jsonResponse({
        success: false,
        version: VERSION,
        error: "Only the Standard 150 scan is available.",
        ...identity.fields,
      }, 400);
    }

    const websiteUrl = normalizeWebsiteUrl(
      body.website_url || body.url || body.normalized_url || body.requested_start_url || body.start_url || "",
    );
    if (!websiteUrl) {
      return jsonResponse({
        success: false,
        version: VERSION,
        error: "Missing or invalid website_url.",
        ...identity.fields,
      }, 400);
    }
    const safety = validatePublicHttpUrl(websiteUrl);
    if (!safety.ok) {
      return jsonResponse({
        success: false,
        version: VERSION,
        error: safety.reason,
        ...identity.fields,
      }, 400);
    }

    let context;
    let entitlement;
    let admissionMeta = { replayed: false, replay_reason: "" };
    if (identity.fields.scan_id) {
      // Temporary cache-compatible path for a browser-created row. It remains
      // only until the server-admission frontend has crossed its cache window.
      context = await loadOwnedScanContext({ base44, user, identity, websiteUrl });
      if (!context.ok) {
        return jsonResponse({
          success: false,
          version: VERSION,
          error: context.error,
          ...identity.fields,
        }, context.status);
      }
      entitlement = await loadPaidEntitlement(base44, user);
      if (!entitlement.ok) {
        const attemptCount = normalizeAttemptCount(context.scan?.attempt_count);
        await failOwnedScanRun({
          base44,
          context,
          identity: identity.fields,
          attemptCount,
          failureCode: entitlement.failureCode,
        });
        return jsonResponse({
          success: false,
          accepted: false,
          version: VERSION,
          retryable: false,
          failure_code: entitlement.failureCode,
          error: customerStatusDetail(entitlement.failureCode),
          ...identity.fields,
        }, entitlement.failureCode === "paid_access_conflict" ? 409 : 402);
      }
    } else {
      const policy = betaScanAdmissionPolicy();
      if (!policy.ok) {
        return jsonResponse({
          success: false,
          accepted: false,
          version: VERSION,
          retryable: false,
          failure_code: policy.code,
          error: customerStatusDetail(policy.code),
          ...identity.fields,
        }, 503);
      }
      if (!policy.allowedUserIds.includes(String(user.id))) {
        return jsonResponse({
          success: false,
          accepted: false,
          version: VERSION,
          retryable: false,
          failure_code: "scan_not_invited",
          error: "This Standard 150 beta cohort is invite-only.",
          ...identity.fields,
        }, 403);
      }

      const project = await loadExactOwnedProject({
        base44,
        user,
        projectId: body.project_id,
        websiteUrl,
      });
      if (!project.ok) {
        return jsonResponse({
          success: false,
          accepted: false,
          version: VERSION,
          failure_code: project.code,
          error: project.error,
          ...identity.fields,
        }, project.status);
      }

      entitlement = await loadPaidEntitlement(base44, user);
      if (!entitlement.ok) {
        return jsonResponse({
          success: false,
          accepted: false,
          version: VERSION,
          retryable: false,
          failure_code: entitlement.failureCode,
          error: customerStatusDetail(entitlement.failureCode),
          ...identity.fields,
        }, entitlement.failureCode === "paid_access_conflict" ? 409 : 402);
      }

      const admitted = await admitServerOwnedScan({
        base44,
        user,
        access: entitlement.record,
        project: project.project,
        body,
        identity,
        websiteUrl,
      });
      if (!admitted.ok) {
        return jsonResponse({
          success: false,
          accepted: false,
          version: VERSION,
          retryable: admitted.retryable === true,
          retry_after: admitted.retryAfter || undefined,
          failure_code: admitted.code,
          error: admitted.error,
          ...identity.fields,
        }, admitted.status);
      }
      context = admitted.context;
      identity.fields.scan_id = String(context.scan.id);
      identity.fields.scan_run_id = String(context.scan.id);
      admissionMeta = {
        replayed: admitted.replayed === true,
        replay_reason: admitted.replayReason || "",
      };
    }

    const attemptCount = normalizeAttemptCount(context.scan?.attempt_count);
    if (scanIsTerminal(context.scan)) {
      return jsonResponse({
        success: true,
        accepted: true,
        version: VERSION,
        scan_mode: PUBLIC_SCAN_MODE,
        status: String(context.scan.status),
        max_pages: MAX_PAGES,
        respect_robots_txt: true,
        deno_fallback_used: false,
        ...admissionMeta,
        ...identity.fields,
      });
    }

    const queuePath = String(Deno.env.get("SCAN_TASKS_QUEUE_PATH") || "");
    const drainQueuePath = String(Deno.env.get("SCAN_DRAIN_QUEUE_PATH") || "");
    const workerUrl = String(Deno.env.get("SCAN_WORKER_URL") || "");
    const invokerServiceAccount = String(Deno.env.get("TASKS_INVOKER_SERVICE_ACCOUNT") || "");
    if (!queuePath || !drainQueuePath || queuePath === drainQueuePath || !workerUrl || !invokerServiceAccount) {
      await failOwnedScanRun({
        base44,
        context,
        identity: identity.fields,
        attemptCount,
        failureCode: "durable_worker_not_configured",
      });
      return jsonResponse({
        success: false,
        accepted: false,
        version: VERSION,
        retryable: true,
        failure_code: "durable_worker_not_configured",
        error: customerStatusDetail("durable_worker_not_configured"),
        ...identity.fields,
      }, 503);
    }

    const pathPrefix = String(
      body.path_prefix || body.requested_path_prefix || body.crawl_path_prefix || "",
    ) || null;
    const drainAfter = new Date(Date.now() + DRAIN_DELAY_SECONDS * 1000).toISOString();
    const commonPayload = {
      scan_id: identity.fields.scan_id,
      attempt_count: attemptCount,
      request_id: identity.fields.request_id,
      idempotency_key: identity.fields.idempotency_key,
      project_id: String(context.scan?.project_id || ""),
      owner_user_id: String(user.id),
      website_url: websiteUrl,
      normalized_domain: identity.fields.normalized_domain,
    };

    // The delayed, attempt-bound watchdog is created first. If the scan task or
    // all of its retries disappear, this task is the final server-side owner of
    // terminal state. If the scan completes, it no-ops.
    const drain = await enqueueScanDrain({
      queuePath: drainQueuePath,
      workerUrl,
      invokerServiceAccount,
      scanId: identity.fields.scan_id,
      attemptCount,
      payload: { ...commonPayload, drain_after: drainAfter },
    });
    if (!drain.ok) {
      await failOwnedScanRun({
        base44,
        context,
        identity: identity.fields,
        attemptCount,
        failureCode: drain.failureCode,
      });
      return jsonResponse({
        success: false,
        accepted: false,
        version: VERSION,
        retryable: true,
        failure_code: drain.failureCode,
        error: "The scan safety watchdog could not be queued. No scan was started.",
        ...identity.fields,
      }, 503);
    }

    const enqueued = await enqueueScanJob({
      queuePath,
      workerUrl,
      invokerServiceAccount,
      scanId: identity.fields.scan_id,
      attemptCount,
      payload: {
        ...commonPayload,
        path_prefix: pathPrefix,
        business_name: String(body.business_name || body.project_name || ""),
        cms_platform: String(body.cms_platform || body.platform || ""),
        scan_mode: PUBLIC_SCAN_MODE,
        respect_robots_txt: true,
      },
    });

    if (!enqueued.ok && enqueued.outcomeUnknown !== true) {
      await failOwnedScanRun({
        base44,
        context,
        identity: identity.fields,
        attemptCount,
        failureCode: enqueued.failureCode,
      });
      return jsonResponse({
        success: false,
        accepted: false,
        version: VERSION,
        retryable: true,
        failure_code: enqueued.failureCode,
        error: "The scan job could not be queued.",
        ...identity.fields,
      }, 503);
    }

    const dispatchUncertain = enqueued.ok !== true;
    logBoundary("async_job_accepted", identity.fields, {
      attempt_count: attemptCount,
      task_name: enqueued.taskName || "",
      watchdog_task_name: drain.taskName || "",
      deduplicated: enqueued.deduplicated === true,
      dispatch_uncertain: dispatchUncertain,
    });
    return jsonResponse({
      success: true,
      accepted: true,
      version: VERSION,
      scan_mode: PUBLIC_SCAN_MODE,
      status: "crawling",
      worker_budget_ms: ASYNC_WORKER_BUDGET_MS,
      max_pages: MAX_PAGES,
      respect_robots_txt: true,
      deno_fallback_used: false,
      dispatch_uncertain: dispatchUncertain,
      ...admissionMeta,
      ...identity.fields,
    });
  } catch (error) {
    console.error("startStandardScanJob failed", {
      message: String(error?.message || error).slice(0, 180),
    });
    return jsonResponse({
      success: false,
      accepted: false,
      version: VERSION,
      error: "The scan job could not be submitted.",
      retryable: true,
    }, 500);
  }
}

async function loadExactOwnedProject({ base44, user, projectId, websiteUrl }) {
  const id = String(projectId || "").trim();
  if (!id) {
    return { ok: false, status: 400, code: "project_id_required", error: "Choose a website project first." };
  }
  const project = await base44.asServiceRole.entities.BusinessProject.get(id).catch(() => null);
  if (!project || String(project.id || "") !== id || String(project.owner_user_id || "") !== String(user.id)) {
    return { ok: false, status: 404, code: "project_not_found", error: "This website project is not available." };
  }
  if (authorityDomain(project.website_url) !== authorityDomain(websiteUrl)) {
    return { ok: false, status: 409, code: "project_domain_mismatch", error: "The scan website does not match this project." };
  }
  return { ok: true, project };
}

async function admitServerOwnedScan({ base44, user, access, project, body, identity, websiteUrl }) {
  const request = normalizeAdmissionIdentity({
    request_id: identity.fields.request_id,
    idempotency_key: identity.fields.idempotency_key,
    request_fingerprint: await buildAdmissionFingerprint(websiteUrl),
  });
  if (!request.ok) {
    return { ok: false, status: 409, code: request.code, error: "The scan request identity is invalid." };
  }
  identity.fields.request_fingerprint = request.request_fingerprint;

  let claim;
  try {
    claim = await claimAdmission({
      ownerUserId: String(user.id),
      requestId: request.request_id,
      requestFingerprint: request.request_fingerprint,
    });
  } catch {
    claim = { ok: false, outcomeUnknown: true, failureCode: "admission_unreachable" };
  }
  if (!claim?.ok) return coordinatorAdmissionFailure(claim);

  const claimToken = String(claim.claim_token || "").trim();
  const claimedScanId = String(claim.scan_id || "").trim();
  if (claim.outcome === "replayed" && claimedScanId) {
    let scan = await base44.asServiceRole.entities.ScanRun.get(claimedScanId).catch(() => null);
    const validation = validateServerScanContext({ scan, user, project, request, websiteUrl });
    if (!validation.ok) return validation;
    scan = await normalizeRecoveredServerScan({ scans: base44.asServiceRole.entities.ScanRun, scan });
    return {
      ok: true,
      replayed: true,
      replayReason: "request_replay",
      context: { ok: true, scan, project, expectedDomain: authorityDomain(websiteUrl) },
    };
  }
  if (!["claimed", "replayed"].includes(String(claim.outcome || "")) || !claimToken) {
    return { ok: false, status: 503, code: "scan_admission_state_invalid", error: "Scan admission is temporarily unavailable.", retryable: true, retryAfter: 2 };
  }

  // Only the caller that received a fresh `claimed` outcome may create a new
  // ScanRun. An exact replay with no coordinator scan_id first looks for a row
  // that the original caller may already have created before losing its bind
  // response. If none exists yet, it waits instead of racing a second create.
  if (claim.outcome === "replayed" && !claimedScanId) {
    const recovered = await recoverExistingServerScan({
      base44,
      user,
      project,
      request,
      websiteUrl,
    }).catch(() => null);
    if (!recovered) {
      return {
        ok: false,
        status: 202,
        code: "scan_admission_pending",
        error: "This exact scan request is still being admitted.",
        retryable: true,
        retryAfter: 2,
      };
    }
    const rebound = await bindAdmission({
      ownerUserId: String(user.id),
      requestId: request.request_id,
      claimToken,
      scanId: String(recovered.id),
    }).catch(() => ({ ok: false, outcomeUnknown: true, failureCode: "admission_unreachable" }));
    if (!rebound?.ok || !["bound", "already_bound"].includes(String(rebound.outcome || ""))) {
      const failure = coordinatorAdmissionFailure(rebound, "scan_admission_binding_lost");
      return { ...failure, error: "The recovered scan could not be bound to this request." };
    }
    return {
      ok: true,
      replayed: true,
      replayReason: "request_replay_recovered",
      context: { ok: true, scan: recovered, project, expectedDomain: authorityDomain(websiteUrl) },
    };
  }

  let scan;
  try {
    scan = await recoverOrCreateServerScan({
      base44,
      user,
      access,
      project,
      body,
      request,
      websiteUrl,
    });
  } catch (error) {
    return {
      ok: false,
      status: Number(error?.status || 503),
      code: String(error?.code || "scan_admission_create_unknown"),
      error: "The durable scan record could not be admitted yet.",
      retryable: true,
      retryAfter: 2,
    };
  }

  let bound;
  try {
    bound = await bindAdmission({
      ownerUserId: String(user.id),
      requestId: request.request_id,
      claimToken,
      scanId: String(scan.id),
    });
  } catch {
    bound = { ok: false, outcomeUnknown: true, failureCode: "admission_unreachable" };
  }
  if (!bound?.ok || !["bound", "already_bound"].includes(String(bound.outcome || ""))) {
    const failure = coordinatorAdmissionFailure(bound, "scan_admission_binding_lost");
    return { ...failure, error: "The durable scan record could not be bound to this request." };
  }

  return {
    ok: true,
    replayed: claim.outcome === "replayed",
    replayReason: claim.outcome === "replayed" ? "request_replay_recovered" : "server_admitted",
    context: { ok: true, scan, project, expectedDomain: authorityDomain(websiteUrl) },
  };
}

function coordinatorAdmissionFailure(result = {}, fallbackCode = "scan_admission_state_unavailable") {
  const upstream = String(result?.failureCode || fallbackCode);
  if (upstream === "admission_busy") {
    return {
      ok: false,
      status: 429,
      code: "scan_admission_busy",
      error: "Another scan is already active for this account.",
      retryable: true,
      retryAfter: Math.max(1, Number(result?.retryAfterSeconds || 2)),
    };
  }
  if (["request_conflict", "scan_identity_conflict", "invalid_claim_token", "claim_expired"].includes(upstream)) {
    return { ok: false, status: 409, code: upstream === "request_conflict" ? "scan_request_identity_conflict" : upstream, error: "The scan request identity conflicts with an existing request." };
  }
  return {
    ok: false,
    status: 503,
    code: upstream || fallbackCode,
    error: "Scan admission is temporarily unavailable.",
    retryable: true,
    retryAfter: Math.max(1, Number(result?.retryAfterSeconds || 2)),
  };
}

async function buildAdmissionFingerprint(websiteUrl) {
  const canonical = `${PUBLIC_SCAN_MODE}|${normalizeWebsiteUrl(websiteUrl)}`;
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(canonical)));
  return `standard150:${Array.from(digest, (byte) => byte.toString(16).padStart(2, "0")).join("")}`;
}

async function recoverExistingServerScan({ base44, user, project, request, websiteUrl }) {
  const scans = base44.asServiceRole.entities.ScanRun;
  const matches = await scans.filter(
    { owner_user_id: String(user.id), request_id: request.request_id },
    "-created_date",
    3,
  ).catch(() => []);
  if (matches.length > 1) {
    throw Object.assign(new Error("scan_request_duplicate_rows"), { status: 409, code: "scan_request_duplicate_rows" });
  }
  if (matches.length === 0) return null;
  const validation = validateServerScanContext({ scan: matches[0], user, project, request, websiteUrl });
  if (!validation.ok) throw Object.assign(new Error(validation.code), validation);
  return normalizeRecoveredServerScan({ scans, scan: matches[0] });
}

async function recoverOrCreateServerScan({
  base44,
  user,
  access,
  project,
  body,
  request,
  websiteUrl,
}) {
  const scans = base44.asServiceRole.entities.ScanRun;
  let matches = await scans.filter(
    { owner_user_id: String(user.id), request_id: request.request_id },
    "-queued_at",
    3,
  );
  if ((matches || []).length > 1) {
    throw Object.assign(new Error("duplicate_scan_request"), { status: 409, code: "duplicate_scan_request" });
  }

  let scan = matches?.[0] || null;
  if (scan) {
    const validation = validateServerScanContext({ scan, user, project, request, websiteUrl });
    if (!validation.ok) throw Object.assign(new Error(validation.code), validation);
    return normalizeRecoveredServerScan({ scans, scan });
  }

  let previousScanId = "";
  const previous = await scans.filter(
    { owner_user_id: String(user.id), project_id: String(project.id) },
    "-completed_at",
    20,
  ).catch(() => []);
  previousScanId = (previous || []).find((row) => ["complete", "limited"].includes(String(row.status || "")))?.id || "";

  const now = new Date().toISOString();
  try {
    const created = await scans.create({
      request_id: request.request_id,
      idempotency_key: request.idempotency_key,
      request_fingerprint: request.request_fingerprint,
      project_id: String(project.id),
      website_url: websiteUrl,
      submitted_url: String(body.submitted_url || body.requested_start_url || websiteUrl),
      final_url: "",
      normalized_domain: authorityDomain(websiteUrl),
      path_prefix: String(body.path_prefix || body.requested_path_prefix || body.crawl_path_prefix || ""),
      scan_mode: PUBLIC_SCAN_MODE,
      scan_source: String(body.source || "scan_website_page"),
      status: "queued",
      previous_scan_id: String(previousScanId),
      attempt_count: 1,
      respect_robots_txt: true,
      queued_at: now,
      owner_user_id: String(user.id),
      admission_access_id: String(access.id),
    });
    return normalizeRecoveredServerScan({ scans, scan: created, now });
  } catch (error) {
    // A create/update response can be lost after Base44 committed it. Recover by
    // the owner/request identity before reporting an ambiguous admission.
    matches = await scans.filter(
      { owner_user_id: String(user.id), request_id: request.request_id },
      "-queued_at",
      3,
    ).catch(() => []);
    if (matches.length === 1) {
      scan = matches[0];
      const validation = validateServerScanContext({ scan, user, project, request, websiteUrl });
      if (validation.ok) return normalizeRecoveredServerScan({ scans, scan });
    }
    throw error;
  }
}

async function normalizeRecoveredServerScan({ scans, scan, now = new Date().toISOString() }) {
  const id = String(scan?.id || "").trim();
  if (!id) throw Object.assign(new Error("admission_scan_id_missing"), { status: 503, code: "admission_scan_id_missing" });
  const terminal = TERMINAL_SCAN_STATUSES.has(String(scan?.status || "").toLowerCase());
  const fields = {};
  if (String(scan?.scan_id || "") !== id) fields.scan_id = id;
  if (!terminal && String(scan?.status || "").toLowerCase() === "queued") {
    fields.status = "crawling";
    if (!scan?.started_at) fields.started_at = now;
  }
  if (Object.keys(fields).length === 0) return { ...scan, id, scan_id: id };
  const updated = await scans.update(id, fields);
  return { ...scan, ...(updated || {}), ...fields, id, scan_id: id };
}

function validateServerScanContext({ scan, user, project, request, websiteUrl }) {
  if (!scan || String(scan.owner_user_id || "") !== String(user.id)) {
    return { ok: false, status: 404, code: "scan_not_found", error: "This scan is not available to this account." };
  }
  const storedFingerprint = String(scan.request_fingerprint || "")
    || `${String(scan.scan_mode || PUBLIC_SCAN_MODE)}|${normalizeWebsiteUrl(scan.website_url || scan.submitted_url)}`;
  if (
    String(scan.request_id || "") !== request.request_id
    || String(scan.idempotency_key || scan.request_id || "") !== request.idempotency_key
    || storedFingerprint !== request.request_fingerprint
    || String(scan.project_id || "") !== String(project.id)
    || authorityDomain(scan.website_url || scan.submitted_url) !== authorityDomain(websiteUrl)
  ) {
    return { ok: false, status: 409, code: "scan_request_identity_conflict", error: "The scan request identity does not match." };
  }
  return { ok: true };
}

async function loadPaidEntitlement(base44, user) {
  const userId = String(user?.id || "").trim();
  const email = String(user?.email || "").trim().toLowerCase();
  try {
    const [byUser, byEmail] = await Promise.all([
      base44.asServiceRole.entities.Access.filter({ owner_user_id: userId }),
      base44.asServiceRole.entities.Access.filter({ user_email: email }),
    ]);
    return evaluatePaidAccess({
      rows: uniqueAccessRows([...(byUser || []), ...(byEmail || [])]),
      user,
    });
  } catch {
    return { ok: false, failureCode: "paid_access_required" };
  }
}

async function loadOwnedScanContext({ base44, user, identity, websiteUrl }) {
  try {
    const scan = await base44.asServiceRole.entities.ScanRun.get(identity.fields.scan_id);
    if (!scan || !recordOwnedBy(scan, user)) {
      return { ok: false, status: 403, error: "The scan does not belong to this account." };
    }
    if (TERMINAL_SCAN_STATUSES.has(String(scan.status || "").toLowerCase())) {
      return { ok: false, status: 409, error: "This scan attempt is already terminal." };
    }
    if (scan.request_id && scan.request_id !== identity.fields.request_id) {
      return { ok: false, status: 409, error: "The scan request identity does not match." };
    }
    if (scan.idempotency_key && scan.idempotency_key !== identity.fields.idempotency_key) {
      return { ok: false, status: 409, error: "The scan request identity does not match." };
    }

    const projectId = String(scan.project_id || "").trim();
    if (!projectId) {
      return { ok: false, status: 409, error: "The scan is missing its website project identity." };
    }
    const project = await base44.asServiceRole.entities.BusinessProject.get(projectId);
    if (!project || !recordOwnedBy(project, user)) {
      return { ok: false, status: 403, error: "The website project does not belong to this account." };
    }

    const expectedDomain = authorityDomain(websiteUrl);
    if (
      !expectedDomain ||
      authorityDomain(scan.website_url || scan.submitted_url) !== expectedDomain ||
      authorityDomain(project.website_url) !== expectedDomain
    ) {
      return { ok: false, status: 409, error: "The scan website does not match its saved project." };
    }
    return { ok: true, scan, project, expectedDomain };
  } catch {
    return {
      ok: false,
      status: 503,
      error: "The saved scan context is unavailable. Please retry.",
    };
  }
}

async function failOwnedScanRun({ base44, context, identity, attemptCount, failureCode }) {
  if (!context?.ok || !context.scan?.id) return;
  const current = await base44.asServiceRole.entities.ScanRun.get(context.scan.id).catch(() => null);
  if (
    !current ||
    normalizeAttemptCount(current.attempt_count) !== normalizeAttemptCount(attemptCount) ||
    TERMINAL_SCAN_STATUSES.has(String(current.status || "").toLowerCase())
  ) return;

  try {
    await base44.asServiceRole.entities.ScanRun.update(context.scan.id, {
      status: "failed",
      status_detail: customerStatusDetail(failureCode),
      error_code: failureCode,
      error_message: customerStatusDetail(failureCode),
      completed_at: new Date().toISOString(),
      release_gate_eligible: false,
    });
    if (context.scan?.admission_access_id) {
      await releaseCoordinatorAdmission({
        ownerUserId: String(context.scan.owner_user_id || ""),
        scanId: String(context.scan.id),
        terminalStatus: "failed",
      });
    }
    logBoundary("dispatcher_terminal_failed", identity, {
      attempt_count: normalizeAttemptCount(attemptCount),
      failure_code: failureCode,
    });
  } catch (error) {
    console.error("startStandardScanJob terminal write failed", {
      request_id: identity?.request_id,
      scan_id: identity?.scan_id,
      failure_code: failureCode,
      update_error: String(error?.message || error).slice(0, 160),
    });
  }
}

async function releaseCoordinatorAdmission({ ownerUserId, scanId, terminalStatus }) {
  const released = await releaseAdmission({ ownerUserId, scanId, terminalStatus }).catch(() => ({
    ok: false,
    failureCode: "admission_unreachable",
    outcomeUnknown: true,
  }));
  if (released?.ok && ["released", "already_released"].includes(String(released.outcome || ""))) return true;
  console.error("startStandardScanJob admission release failed", {
    scan_id: scanId,
    terminal_status: terminalStatus,
    failure_code: String(released?.failureCode || "admission_release_failed"),
    outcome_unknown: released?.outcomeUnknown === true,
  });
  return false;
}

function customerStatusDetail(failureCode) {
  return CUSTOMER_STATUS_DETAIL[failureCode]
    || "The scan did not complete. No partial result was saved. Please try again.";
}

function resolveRequestIdentity(body = {}) {
  const requestId = String(body.request_id || body.idempotency_key || "").trim();
  const idempotencyKey = String(body.idempotency_key || requestId).trim();
  const scanId = String(body.scan_id || body.scan_run_id || "").trim();
  const submittedUrl = String(
    body.submitted_url || body.requested_start_url || body.website_url || "",
  ).trim();
  const normalizedDomain = authorityDomain(
    body.normalized_domain || body.website_url || submittedUrl,
  );
  return {
    conflict: Boolean(requestId && idempotencyKey && requestId !== idempotencyKey),
    fields: {
      request_id: requestId,
      idempotency_key: idempotencyKey,
      scan_id: scanId,
      scan_run_id: scanId,
      request_fingerprint: "",
      submitted_url: submittedUrl,
      normalized_domain: normalizedDomain,
    },
  };
}

function recordOwnedBy(record, user) {
  const userId = String(user?.id || "").trim();
  const userEmail = String(user?.email || "").trim().toLowerCase();
  if (!userId) return false;
  const explicitOwner = String(record?.owner_user_id || "").trim();
  if (explicitOwner) return explicitOwner === userId;
  const creatorId = String(record?.created_by_id || "").trim();
  if (creatorId) return creatorId === userId;
  return Boolean(userEmail && String(record?.created_by || "").trim().toLowerCase() === userEmail);
}

function authorityDomain(value) {
  const normalized = normalizeWebsiteUrl(value);
  if (!normalized) return "";
  try {
    return new URL(normalized).hostname.toLowerCase().replace(/^www\./, "").replace(/\.$/, "");
  } catch {
    return "";
  }
}

function normalizeWebsiteUrl(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  try {
    const url = new URL(/^https?:\/\//i.test(raw) ? raw : `https://${raw}`);
    if (!/^https?:$/.test(url.protocol) || !url.hostname || url.username || url.password) return "";
    url.hash = "";
    return url.href;
  } catch {
    return "";
  }
}

function validatePublicHttpUrl(value) {
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase();
    if (!/^https?:$/.test(url.protocol)) return { ok: false, reason: "URL must use http or https." };
    if (!host || host === "localhost" || host.endsWith(".localhost")) {
      return { ok: false, reason: "Localhost URLs are not allowed." };
    }
    if (/^(127\.|10\.|0\.|169\.254\.|192\.168\.|172\.(1[6-9]|2\d|3[0-1])\.)/.test(host)) {
      return { ok: false, reason: "Private network URLs are not allowed." };
    }
    if (host === "::1" || host.startsWith("[::1")) {
      return { ok: false, reason: "Private network URLs are not allowed." };
    }
    return { ok: true, reason: "" };
  } catch {
    return { ok: false, reason: "Missing or invalid website_url." };
  }
}

async function safeReadJson(req) {
  try {
    return await req.json();
  } catch {
    return {};
  }
}

function unwrapRequestBody(raw) {
  if (!raw || typeof raw !== "object") return {};
  for (const key of ["data", "body", "payload", "input", "args", "request"]) {
    if (raw[key] && typeof raw[key] === "object") return raw[key];
  }
  return raw;
}

function logBoundary(boundary, identity, extra = {}) {
  console.info("[fixlist.scanjob]", {
    boundary,
    request_id: identity?.request_id || "",
    scan_id: identity?.scan_id || "",
    at: new Date().toISOString(),
    ...extra,
  });
}
