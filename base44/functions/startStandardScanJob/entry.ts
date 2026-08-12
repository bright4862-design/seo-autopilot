import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";
import {
  DRAIN_DELAY_SECONDS,
  enqueueScanDrain,
  enqueueScanJob,
  normalizeAttemptCount,
} from "./cloudTasks.js";
import { evaluatePaidAccess, uniqueAccessRows } from "./entitlement.js";

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

const VERSION = "startStandardScanJob_v2_paid_durable";
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
    if (!identity.fields.request_id || !identity.fields.scan_id) {
      return jsonResponse({
        success: false,
        version: VERSION,
        error: "A durable request_id and scan_id are required.",
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

    const context = await loadOwnedScanContext({ base44, user, identity, websiteUrl });
    if (!context.ok) {
      return jsonResponse({
        success: false,
        version: VERSION,
        error: context.error,
        ...identity.fields,
      }, context.status);
    }

    const attemptCount = normalizeAttemptCount(context.scan?.attempt_count);
    const entitlement = await loadPaidEntitlement(base44, user);
    if (!entitlement.ok) {
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

    const queuePath = String(Deno.env.get("SCAN_TASKS_QUEUE_PATH") || "");
    const workerUrl = String(Deno.env.get("SCAN_WORKER_URL") || "");
    const invokerServiceAccount = String(Deno.env.get("TASKS_INVOKER_SERVICE_ACCOUNT") || "");
    if (!queuePath || !workerUrl || !invokerServiceAccount) {
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
      queuePath,
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
    const scan = await base44.entities.ScanRun.get(identity.fields.scan_id);
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
    const project = await base44.entities.BusinessProject.get(projectId);
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
  const current = await base44.entities.ScanRun.get(context.scan.id).catch(() => null);
  if (
    !current ||
    normalizeAttemptCount(current.attempt_count) !== normalizeAttemptCount(attemptCount) ||
    TERMINAL_SCAN_STATUSES.has(String(current.status || "").toLowerCase())
  ) return;

  try {
    await base44.entities.ScanRun.update(context.scan.id, {
      status: "failed",
      status_detail: customerStatusDetail(failureCode),
      error_code: failureCode,
      error_message: customerStatusDetail(failureCode),
      completed_at: new Date().toISOString(),
      release_gate_eligible: false,
    });
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
      submitted_url: submittedUrl,
      normalized_domain: normalizedDomain,
    },
  };
}

function recordOwnedBy(record, user) {
  const userId = String(user?.id || "").trim();
  const userEmail = String(user?.email || "").trim().toLowerCase();
  return Boolean(userId && (
    String(record?.owner_user_id || "").trim() === userId ||
    String(record?.created_by_id || "").trim() === userId ||
    (userEmail && String(record?.created_by || "").trim().toLowerCase() === userEmail)
  ));
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
