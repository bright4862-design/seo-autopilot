import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";
import { createAuthoritySeal } from "./authoritySeal.js";

const VERSION = "runStandard150Scan_v1_python_required";
const PUBLIC_SCAN_MODE = "standard_150";
const PYTHON_COMPATIBILITY_MODE = "advanced";
const PYTHON_SCANNER_VERSION = "python_scanner_v3_bounded_request";
const MAX_PAGES = 150;
// Deadline model, outermost to innermost:
//
//   PYTHON_CRAWL_BUDGET_MS + UPSTREAM_RESPONSE_RESERVE_MS
//     < upstreamTimeoutMs
//     < upstreamTimeoutMs + RESPONSE_RESERVE_MS
//     < FUNCTION_RESPONSE_BUDGET_MS
//     < BROWSER_DEADLINE_MS
//
// These budgets are bounded by the Base44 function platform, not by our own
// timers. Production evidence: with a 95s function budget (~90s upstream timer)
// scan 6a74441e23b1bf178afd41a2 still died at 51.6s with
// AbortError "The operation was aborted" -- the platform aborts the outbound
// fetch at roughly 50 seconds regardless of what we configure. A 75s Python
// budget therefore authorises a crawl the platform will kill before it can
// respond, which is a guaranteed 503 for any site that uses the full budget.
//
// The crawl budget must also leave room for what happens AFTER crawling.
// Python honours its deadline (sitemap discovery and crawl both sit inside
// scan_started_at + budget["timeout"]), but serialising and transferring a
// 150-page evidence payload then costs another ~10s. At a 40s crawl budget the
// total landed at 49.8-52.7s against a 50s upstream timer, so large-site root
// scans were a coin flip: funbooker.com/ and jackssurfboards.com/ failed at
// 50.9s, 51.6s, 51.9s while small sites (11-16s) and narrow path-prefixed
// scans always passed.
//
// 28s leaves roughly 22s for the response instead of 10s. On a slow site the
// crawl now stops earlier and Python returns what it collected with
// scan_deadline_reached true -- a smaller sealed result rather than a 503.
// This trades page coverage for completion; restoring full coverage on large
// sites needs asynchronous orchestration, not a larger timer.
//
// The 150-page maximum, robots enforcement and Python-only operation are
// unaffected: this changes time, never scope.
const PYTHON_CRAWL_BUDGET_MS = 28_000;
const BROWSER_DEADLINE_MS = 105_000;
const FUNCTION_RESPONSE_BUDGET_MS = 55_000;
const RESPONSE_RESERVE_MS = 5_000;
const UPSTREAM_RESPONSE_RESERVE_MS = 4_000;
const REVIEW_PAGE_SAMPLE_LIMIT = 60;
const REVIEW_FINDING_LIMIT = 100;
const SCAN_ATTESTATION_VERSION = "standard_scan_review_payload_hmac_v2";
const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

Deno.serve(async (req) => {
  const startedAt = Date.now();
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS_HEADERS });
  if (req.method !== "POST") return jsonResponse({ success: false, version: VERSION, error: "Method not allowed." }, 405);

  let body = {};
  let context = null;
  // Hoisted so the catch-all can still write the terminal ScanRun state.
  let base44 = null;
  try {
    base44 = createClientFromRequest(req);
    const user = await base44.auth.me().catch(() => null);
    if (!user?.id) return jsonResponse({ success: false, version: VERSION, error: "Unauthorized." }, 401);

    body = unwrapRequestBody(await safeReadJson(req));
    const identity = resolveRequestIdentity(body);
    if (identity.conflict) {
      return jsonResponse({ success: false, version: VERSION, error: "request_id and idempotency_key must match.", ...identity.fields }, 409);
    }
    if (!identity.fields.request_id || !identity.fields.scan_id) {
      return jsonResponse({ success: false, version: VERSION, error: "A durable request_id and scan_id are required." }, 400);
    }

    const requestedMode = normalizePublicMode(body.scan_mode || body.canonical_mode || body.audit_profile);
    if (!requestedMode) {
      return jsonResponse({ success: false, version: VERSION, error: "Only the Standard 150 scan is available." }, 400);
    }

    const websiteUrl = normalizeWebsiteUrl(
      body.website_url || body.url || body.normalized_url || body.requested_start_url || body.start_url || body.target_url || "",
    );
    if (!websiteUrl) return jsonResponse({ success: false, version: VERSION, error: "Missing or invalid website_url.", ...identity.fields }, 400);
    const safety = validatePublicHttpUrl(websiteUrl);
    if (!safety.ok) return jsonResponse({ success: false, version: VERSION, error: safety.reason, ...identity.fields }, 400);

    context = await loadOwnedScanContext({ base44, user, identity, websiteUrl });
    if (!context.ok) return jsonResponse({ success: false, version: VERSION, error: context.error, ...identity.fields }, context.status);

    const scannerUrl = scannerApiUrl();
    const scannerKey = scannerApiKey();
    if (!scannerUrl || !scannerKey) {
      return await unavailable({ base44, context, identity, startedAt, failureCode: !scannerUrl ? "url_not_configured" : "key_not_configured" });
    }

    const remainingMs = FUNCTION_RESPONSE_BUDGET_MS - (Date.now() - startedAt);
    const upstreamTimeoutMs = remainingMs - RESPONSE_RESERVE_MS;
    // We must outlast the request-scoped Python budget plus serialization,
    // while still returning before Base44 can kill the function.
    if (upstreamTimeoutMs <= PYTHON_CRAWL_BUDGET_MS + UPSTREAM_RESPONSE_RESERVE_MS) {
      return await unavailable({ base44, context, identity, startedAt, failureCode: "insufficient_gateway_budget" });
    }

    const upstreamPayload = {
      website_url: websiteUrl,
      path_prefix: body.path_prefix || body.requested_path_prefix || body.crawl_path_prefix || null,
      scan_mode: PYTHON_COMPATIBILITY_MODE,
      business_name: body.business_name || body.project_name || "",
      cms_platform: body.cms_platform || body.platform || "",
      request_id: identity.fields.request_id,
      idempotency_key: identity.fields.idempotency_key,
      scan_id: identity.fields.scan_id,
      scan_run_id: identity.fields.scan_run_id,
      submitted_url: identity.fields.submitted_url || websiteUrl,
      normalized_domain: identity.fields.normalized_domain,
      respect_robots_txt: true,
      // Authenticated request-scoped cap. Python clamps this to 20s..75s and
      // preserves the Standard 150 page maximum.
      advisory_crawl_timeout_ms: PYTHON_CRAWL_BUDGET_MS,
    };

    const response = await fetchWithTimeout(`${scannerUrl}/scan`, {
      method: "POST",
      headers: { "content-type": "application/json", "x-scanner-key": scannerKey },
      body: JSON.stringify(upstreamPayload),
    }, upstreamTimeoutMs);

    const text = await response.text();
    const upstream = parseJson(text);
    if (!response.ok || !upstream || upstream.success === false) {
      const failureCode = !response.ok
        ? `http_${response.status}`
        : (upstream ? "scanner_success_false" : "parse_failure");
      return await unavailable({ base44, context, identity, startedAt, failureCode });
    }
    if (upstream.scanner_version !== PYTHON_SCANNER_VERSION) {
      return await unavailable({ base44, context, identity, startedAt, failureCode: "version_mismatch" });
    }
    if (!matchesUpstreamIdentity(upstream, identity.fields)) {
      return await unavailable({ base44, context, identity, startedAt, failureCode: "identity_mismatch" });
    }

    const pages = firstPageArray(upstream).slice(0, MAX_PAGES);
    const reportedPages = nonNegativeInteger(upstream.pages_crawled);
    if (reportedPages > MAX_PAGES || firstPageArray(upstream).length > MAX_PAGES) {
      return await unavailable({ base44, context, identity, startedAt, failureCode: "page_cap_violation" });
    }

    const result = canonicalizeResult({ upstream, pages, identity: identity.fields, elapsedMs: Date.now() - startedAt });
    return jsonResponse(await attachScanAttestation({ base44, user, result, context }));
  } catch (error) {
    const identity = resolveRequestIdentity(body);
    console.error("runStandard150Scan failed", {
      name: String(error?.name || "Error"),
      message: String(error?.message || "unknown error").slice(0, 180),
      request_id: identity.fields.request_id,
      scan_id: identity.fields.scan_id,
    });
    return await unavailable({
      base44,
      context,
      identity,
      startedAt,
      failureCode: isTimeoutError(error) ? "timeout" : "gateway_error",
    });
  }
});

function canonicalizeResult({ upstream, pages, identity, elapsedMs }) {
  const technical = upstream.technical_audit_summary && typeof upstream.technical_audit_summary === "object"
    ? upstream.technical_audit_summary
    : {};
  const pageCount = Math.min(MAX_PAGES, pages.length || nonNegativeInteger(upstream.pages_crawled));
  return {
    ...upstream,
    success: true,
    version: VERSION,
    wrapper_version: VERSION,
    scanner_wrapper_version: VERSION,
    scanner_version: PYTHON_SCANNER_VERSION,
    scan_mode: PUBLIC_SCAN_MODE,
    canonical_mode: PUBLIC_SCAN_MODE,
    audit_profile: PUBLIC_SCAN_MODE,
    max_pages: MAX_PAGES,
    request_id: identity.request_id,
    idempotency_key: identity.idempotency_key,
    scan_id: identity.scan_id,
    scan_run_id: identity.scan_run_id,
    submitted_url: identity.submitted_url,
    normalized_domain: identity.normalized_domain,
    respect_robots_txt: true,
    advanced_scan_backend: "python_scanner_api",
    scanner_backend: "python_scanner_api",
    deno_fallback_used: false,
    screaming_frog_lite_enabled: false,
    pages,
    crawled_pages: pages,
    pages_crawled: pageCount,
    release_gate_eligible: upstream.release_gate_eligible === true,
    gateway_elapsed_ms: elapsedMs,
    technical_audit_summary: {
      ...technical,
      scanner_version: PYTHON_SCANNER_VERSION,
      scanner_wrapper_version: VERSION,
      advanced_scan_backend: "python_scanner_api",
      deno_fallback_used: false,
      pages_crawled: pageCount,
      canonical_mode: PUBLIC_SCAN_MODE,
      respect_robots_txt: true,
    },
  };
}

async function loadOwnedScanContext({ base44, user, identity, websiteUrl }) {
  try {
    const scan = await base44.entities.ScanRun.get(identity.fields.scan_id);
    if (!scan || !recordOwnedBy(scan, user)) return { ok: false, status: 403, error: "The scan does not belong to this account." };
    if (scan.request_id && scan.request_id !== identity.fields.request_id) return { ok: false, status: 409, error: "The scan request identity does not match." };
    if (scan.idempotency_key && scan.idempotency_key !== identity.fields.idempotency_key) return { ok: false, status: 409, error: "The scan request identity does not match." };
    const projectId = String(scan.project_id || "").trim();
    if (!projectId) return { ok: false, status: 409, error: "The scan is missing its website project identity." };
    const project = await base44.entities.BusinessProject.get(projectId);
    if (!project || !recordOwnedBy(project, user)) return { ok: false, status: 403, error: "The website project does not belong to this account." };
    const expectedDomain = authorityDomain(websiteUrl);
    if (!expectedDomain || authorityDomain(scan.website_url || scan.submitted_url) !== expectedDomain || authorityDomain(project.website_url) !== expectedDomain) {
      return { ok: false, status: 409, error: "The scan website does not match its saved project." };
    }
    return { ok: true, scan, project, expectedDomain };
  } catch {
    return { ok: false, status: 503, error: "The saved scan context is unavailable. Please retry." };
  }
}

async function attachScanAttestation({ base44, user, result, context }) {
  const secret = String(Deno.env.get("SCAN_EVIDENCE_SIGNING_KEY") || "");
  if (!secret) return unsignedResult(result, "signing_key_not_configured");
  try {
    const unsigned = withoutAuthorityAttestation(result);
    const reviewPayload = buildAuthorityReviewPayload(unsigned);
    const document = {
      version: SCAN_ATTESTATION_VERSION,
      owner_user_id: String(user.id),
      scan_id: String(context.scan.id),
      project_id: String(context.scan.project_id),
      normalized_domain: context.expectedDomain,
      result: reviewPayload,
    };
    const proof = await createAuthoritySeal(document, secret);
    return {
      ...unsigned,
      authority_review_payload: reviewPayload,
      authority_attestation_status: "server_attested",
      authority_scan_attestation: {
        version: SCAN_ATTESTATION_VERSION,
        owner_user_id: String(user.id),
        scan_id: String(context.scan.id),
        project_id: String(context.scan.project_id),
        normalized_domain: context.expectedDomain,
        proof,
      },
    };
  } catch {
    return unsignedResult(result, "attestation_failed");
  }
}

function buildAuthorityReviewPayload(result = {}) {
  const pages = firstPageArray(result).slice(0, REVIEW_PAGE_SAMPLE_LIMIT);
  const findings = firstFindingArray(result).slice(0, REVIEW_FINDING_LIMIT);
  const technical = result.technical_audit_summary && typeof result.technical_audit_summary === "object"
    ? result.technical_audit_summary
    : {};
  const scanSummary = result.scan_summary && typeof result.scan_summary === "object"
    ? result.scan_summary
    : {};
  return {
    success: true,
    review_payload_version: SCAN_ATTESTATION_VERSION,
    scanner_version: result.scanner_version,
    scanner_build_revision: result.scanner_build_revision || technical.scanner_build_revision,
    scanner_wrapper_version: result.scanner_wrapper_version,
    beta_revision_fingerprint: result.beta_revision_fingerprint,
    advanced_scan_backend: result.advanced_scan_backend,
    deno_fallback_used: false,
    scan_mode: PUBLIC_SCAN_MODE,
    canonical_mode: PUBLIC_SCAN_MODE,
    request_id: result.request_id,
    idempotency_key: result.idempotency_key,
    scan_id: result.scan_id,
    scan_run_id: result.scan_run_id,
    submitted_url: result.submitted_url,
    website_url: result.website_url,
    final_url: result.final_url,
    normalized_domain: result.normalized_domain,
    respect_robots_txt: true,
    pages_crawled: nonNegativeInteger(result.pages_crawled),
    pages_found: nonNegativeInteger(result.pages_found),
    queued_remaining: nonNegativeInteger(result.queued_remaining),
    sampled_pages_sent_to_review: pages.length,
    sampled_findings_sent_to_review: findings.length,
    page_sample_truncated: nonNegativeInteger(result.pages_crawled) > pages.length,
    scanner_elapsed_ms: nonNegativeInteger(result.scanner_elapsed_ms),
    scanner_total_budget_seconds: Number(result.scanner_total_budget_seconds || 0),
    scan_deadline_reached: result.scan_deadline_reached === true,
    requested_crawl_timeout_ms: nonNegativeInteger(result.requested_crawl_timeout_ms),
    metadata_evidence_version: result.metadata_evidence_version || technical.metadata_evidence_version || "",
    title_evidence_version: result.title_evidence_version || technical.title_evidence_version || "",
    sampling_evidence: result.sampling_evidence || {},
    crawl_timing: result.crawl_timing || technical.crawl_timing || {},
    crawl_scope: result.crawl_scope || technical.crawl_scope || {},
    crawl_policy: result.crawl_policy || technical.crawl_policy || {},
    crawl_policy_source: result.crawl_policy_source || technical.crawl_policy_source || "",
    url_evidence_summary: result.url_evidence_summary || technical.url_evidence_summary || {},
    verified_failed_pages: boundedArray(result.verified_failed_pages, 25),
    suspicious_url_artifacts: boundedArray(result.suspicious_url_artifacts, 25),
    health_score: Number(result.health_score || 0),
    scan_summary: scanSummary,
    technical_audit_summary: technical,
    crawl_warnings: Array.isArray(result.crawl_warnings) ? result.crawl_warnings.slice(0, 12) : [],
    crawled_pages: pages,
    grouped_findings: findings,
  };
}

function boundedArray(value, limit) {
  return Array.isArray(value) ? value.slice(0, limit) : [];
}

function firstFindingArray(result = {}) {
  for (const key of ["grouped_findings", "recommendations", "findings", "raw_findings", "fixes"]) {
    if (Array.isArray(result[key])) return result[key];
  }
  return [];
}

function unsignedResult(result, status) {
  return {
    ...withoutAuthorityAttestation(result),
    release_gate_eligible: false,
    authority_review_payload: null,
    authority_scan_attestation: null,
    authority_attestation_status: status,
  };
}

function withoutAuthorityAttestation(result = {}) {
  const {
    authority_review_payload: _reviewPayload,
    authority_scan_attestation: _attestation,
    authority_attestation_status: _status,
    ...unsigned
  } = result;
  return unsigned;
}

function matchesUpstreamIdentity(upstream, identity) {
  return String(upstream.request_id || "") === identity.request_id
    && String(upstream.idempotency_key || upstream.request_id || "") === identity.idempotency_key
    && String(upstream.scan_id || upstream.scan_run_id || "") === identity.scan_id
    && authorityDomain(upstream.final_url || upstream.website_url || upstream.submitted_url || "") === identity.normalized_domain.replace(/^www\./, "");
}

function resolveRequestIdentity(body = {}) {
  const requestId = String(body.request_id || body.idempotency_key || "").trim();
  const idempotencyKey = String(body.idempotency_key || requestId).trim();
  const scanId = String(body.scan_id || body.scan_run_id || "").trim();
  const submittedUrl = String(body.submitted_url || body.requested_start_url || body.website_url || "").trim();
  const normalizedDomain = authorityDomain(body.normalized_domain || body.website_url || submittedUrl);
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

function normalizePublicMode(value) {
  const mode = String(value || PUBLIC_SCAN_MODE).trim().toLowerCase();
  return [PUBLIC_SCAN_MODE, "advanced"].includes(mode) ? PUBLIC_SCAN_MODE : "";
}

function firstPageArray(result = {}) {
  for (const key of ["crawled_pages", "pages", "scanned_pages", "crawl_pages"]) {
    if (Array.isArray(result[key])) return result[key];
  }
  return [];
}

// Terminal states the gateway must never overwrite. A run that already reached
// complete/limited carries persisted evidence; a late gateway failure must not
// destroy it.
const PROTECTED_SCAN_STATUSES = new Set(["complete", "limited"]);

// Customer-safe explanations. Never surface internal failure codes, upstream
// bodies, secrets, or attestation material to the customer.
const CUSTOMER_STATUS_DETAIL = {
  url_not_configured: "The scanner is not configured yet. No pages were scanned and nothing was charged.",
  key_not_configured: "The scanner is not configured yet. No pages were scanned and nothing was charged.",
  insufficient_gateway_budget: "The scan could not be started in the time available. Please try again.",
  timeout: "The scan took longer than the time allowed and was stopped. Please try again.",
  scanner_success_false: "The scanner could not complete this website. Please try again.",
  version_mismatch: "The scanner is being updated. Please try again shortly.",
  identity_mismatch: "This scan could not be matched to your request. Please start a new scan.",
  page_cap_violation: "The scan returned more pages than Standard 150 allows and was rejected.",
  parse_failure: "The scanner returned a response FixList could not read. Please try again.",
  gateway_error: "The scan stopped unexpectedly. No partial result was saved. Please try again.",
};

function customerStatusDetail(failureCode) {
  return CUSTOMER_STATUS_DETAIL[failureCode]
    || "The scan did not complete. No partial result was saved. Please try again.";
}

// The browser is not the only actor that can fail a ScanRun. Once ownership is
// proven, every gateway-observed failure writes a terminal state so a lost or
// closed browser cannot orphan the row.
async function failOwnedScanRun({ base44, context, identity, failureCode }) {
  if (!context?.ok || !context.scan?.id) return { attempted: false, ok: false };
  // context.scan was read before the upstream call and can be ~90s stale by now.
  // persistScanAuthority writes status "complete" from a separate invocation
  // using asServiceRole, so the snapshot is not a safe basis for this decision.
  // Re-read immediately before writing; if the re-read fails, refuse to write
  // rather than risk clobbering a completed run.
  let current = null;
  try {
    current = await base44.entities.ScanRun.get(context.scan.id);
  } catch (error) {
    console.error("runStandard150Scan terminal recheck failed", {
      request_id: identity?.fields?.request_id,
      scan_id: identity?.fields?.scan_id,
      failure_code: failureCode,
      update_error: String(error?.message || error || "unknown error").slice(0, 180),
    });
    return { attempted: false, ok: false, skipped: "recheck_failed" };
  }
  const currentStatus = String(current?.status ?? context.scan.status ?? "").toLowerCase();
  if (!current || PROTECTED_SCAN_STATUSES.has(currentStatus)) {
    return { attempted: false, ok: false, skipped: "protected_status" };
  }
  try {
    await base44.entities.ScanRun.update(context.scan.id, {
      status: "failed",
      status_detail: customerStatusDetail(failureCode),
      error_code: failureCode,
      error_message: customerStatusDetail(failureCode),
      completed_at: new Date().toISOString(),
      release_gate_eligible: false,
    });
    return { attempted: true, ok: true };
  } catch (error) {
    // Log identity and the update failure only. Never secrets or authority proofs.
    console.error("runStandard150Scan terminal write failed", {
      request_id: identity?.fields?.request_id,
      scan_id: identity?.fields?.scan_id,
      failure_code: failureCode,
      update_error: String(error?.message || error || "unknown error").slice(0, 180),
    });
    return { attempted: true, ok: false };
  }
}

async function unavailable({ base44, context, identity, startedAt, failureCode }) {
  const terminal = base44
    ? await failOwnedScanRun({ base44, context, identity, failureCode })
    : { attempted: false, ok: false };
  return jsonResponse({
    scan_run_failed: terminal.ok === true,
    success: false,
    version: VERSION,
    error: "The Standard 150 scanner is temporarily unavailable. Please try again.",
    retryable: true,
    failure_code: failureCode,
    advanced_scan_backend: "python_scanner_api_unavailable",
    deno_fallback_used: false,
    release_gate_eligible: false,
    ...identity.fields,
    elapsed_ms: Date.now() - startedAt,
  }, 503);
}

function scannerApiUrl() {
  return String(
    Deno.env.get("SCANNER_API_URL")
      || Deno.env.get("PYTHON_SCANNER_API_URL")
      || Deno.env.get("PYTHON_SCANNER_URL")
      || Deno.env.get("SCANNER_URL")
      || Deno.env.get("cloud_api")
      || Deno.env.get("CLOUD_API")
      || "",
  ).replace(/\/+$/, "");
}

function scannerApiKey() {
  return String(Deno.env.get("SCANNER_API_KEY") || Deno.env.get("PYTHON_SCANNER_API_KEY") || "");
}

function recordOwnedBy(record, user) {
  const userId = String(user?.id || "").trim();
  const userEmail = String(user?.email || "").trim().toLowerCase();
  return Boolean(userId && (
    String(record?.owner_user_id || "").trim() === userId
    || String(record?.created_by_id || "").trim() === userId
    || (userEmail && String(record?.created_by || "").trim().toLowerCase() === userEmail)
  ));
}

function authorityDomain(value) {
  const normalized = normalizeWebsiteUrl(value);
  if (!normalized) return "";
  try { return new URL(normalized).hostname.toLowerCase().replace(/^www\./, "").replace(/\.$/, ""); }
  catch { return ""; }
}

function normalizeWebsiteUrl(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  try {
    const url = new URL(/^https?:\/\//i.test(raw) ? raw : `https://${raw}`);
    if (!/^https?:$/.test(url.protocol) || !url.hostname || url.username || url.password) return "";
    url.hash = "";
    return url.href;
  } catch { return ""; }
}

function validatePublicHttpUrl(value) {
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase();
    if (!/^https?:$/.test(url.protocol)) return { ok: false, reason: "URL must use http or https." };
    if (!host || host === "localhost" || host.endsWith(".localhost")) return { ok: false, reason: "Localhost URLs are not allowed." };
    if (/^(127\.|10\.|0\.|169\.254\.|192\.168\.|172\.(1[6-9]|2\d|3[0-1])\.)/.test(host)) return { ok: false, reason: "Private network URLs are not allowed." };
    if (host === "::1" || host.startsWith("[::1")) return { ok: false, reason: "Private network URLs are not allowed." };
    return { ok: true, reason: "" };
  } catch { return { ok: false, reason: "Missing or invalid website_url." }; }
}

async function fetchWithTimeout(url, options, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try { return await fetch(url, { ...options, signal: controller.signal }); }
  finally { clearTimeout(timer); }
}

async function safeReadJson(req) {
  try { return await req.json(); } catch { return {}; }
}

function unwrapRequestBody(raw) {
  if (!raw || typeof raw !== "object") return {};
  for (const key of ["data", "body", "payload", "input", "args", "request"]) {
    if (raw[key] && typeof raw[key] === "object") return raw[key];
  }
  return raw;
}

function parseJson(value) {
  try { return JSON.parse(value || "{}"); } catch { return null; }
}

function nonNegativeInteger(value) {
  const number = Number(value || 0);
  return Number.isFinite(number) ? Math.max(0, Math.trunc(number)) : 0;
}

function isTimeoutError(error) {
  const text = `${error?.name || ""} ${error?.message || ""}`;
  return /abort|timeout/i.test(text);
}

function jsonResponse(payload, status = 200) {
  return Response.json(payload, { status, headers: CORS_HEADERS });
}
