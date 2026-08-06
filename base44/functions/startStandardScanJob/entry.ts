import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";
import { waitUntil } from "base44:runtime";
import { createAuthoritySeal } from "./authoritySeal.js";
import { enqueueScanJob, normalizeAttemptCount } from "./cloudTasks.js";

// Defined inline rather than imported. The bundler emitted a _bundled.mjs in
// which the ./httpResponse.js bindings were not defined at runtime, so every
// invocation died with "ReferenceError: jsonResponse is not defined" at the
// accepted-response return -- after the job had already been accepted and the
// worker started, which is how ScanRuns were left running with no reply.
// runStandard150Scan, which works in production, declares these inline too.
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

// Asynchronous durable Standard 150 job gateway.
//
// The synchronous gateway (runStandard150Scan) must answer inside the
// platform's ~50s outbound window, which forces a 28s crawl budget. This
// function removes the browser from the wait entirely:
//
//   1. The owner-bound ScanRun already exists (created by the browser BEFORE
//      any network work; this function only verifies it).
//   2. The authenticated Python job is submitted in a background task and the
//      exact scan_id is returned immediately — the browser never waits for
//      Cloud Run and can never see a 503 caused by crawl duration.
//   3. The worker allows Cloud Run a 120-second crawl budget (async_job mode,
//      enforced server-side by scanner.py), keeps the 150-page cap, robots
//      enforcement, and Python-only operation with no Deno crawler fallback.
//   4. The worker then runs the attested review and persistScanAuthority, so
//      the sealed FixList is durably saved server-side. Only after that seal
//      is verified is the customer's scan allowance consumed.
//   5. Every failure — including a timed-out worker — writes a truthful
//      terminal state on the exact ScanRun; the result page polls that row.
const VERSION = "startStandardScanJob_v1_async_durable";
const PUBLIC_SCAN_MODE = "standard_150";
const PYTHON_COMPATIBILITY_MODE = "advanced";
const PYTHON_SCANNER_VERSION = "python_scanner_v3_bounded_request";
const MAX_PAGES = 150;
const ASYNC_WORKER_BUDGET_MS = 120_000;
// Must outlast the 120s crawl plus serialization/transfer of a 150-page result.
const UPSTREAM_FETCH_TIMEOUT_MS = 160_000;
const REVIEW_PAGE_SAMPLE_LIMIT = 60;
const REVIEW_FINDING_LIMIT = 100;
const SCAN_ATTESTATION_VERSION = "standard_scan_review_payload_hmac_v2";
const PROTECTED_SCAN_STATUSES = new Set(["complete", "limited"]);

const CUSTOMER_STATUS_DETAIL: Record<string, string> = {
  scanner_not_configured: "The scanner is not configured yet. No pages were scanned and nothing was charged.",
  timeout: "The scan took longer than the time allowed and was stopped. Please try again.",
  scanner_success_false: "The scanner could not complete this website. Please try again.",
  version_mismatch: "The scanner is being updated. Please try again shortly.",
  identity_mismatch: "This scan could not be matched to your request. Please start a new scan.",
  page_cap_violation: "The scan returned more pages than Standard 150 allows and was rejected.",
  parse_failure: "The scanner returned a response FixList could not read. Please try again.",
  signing_key_not_configured: "The scan finished but could not be saved securely. Please try again.",
  review_failed: "The scan finished but its review could not be completed. Please try again.",
  review_attestation_missing: "The scan finished but its review could not be verified. Please try again.",
  persistence_failed: "The scan finished, but its results could not be saved. Please try again.",
  worker_error: "The scan stopped unexpectedly. No partial result was saved. Please try again.",
};

export default async function (req: Request): Promise<Response> {
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: corsHeaders() });
  if (req.method !== "POST") return jsonResponse({ success: false, version: VERSION, error: "Method not allowed." }, 405);

  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me().catch(() => null);
    if (!user?.id) return jsonResponse({ success: false, version: VERSION, error: "Unauthorized." }, 401);

    const body = unwrapRequestBody(await safeReadJson(req));
    const identity = resolveRequestIdentity(body);
    if (identity.conflict) {
      return jsonResponse({ success: false, version: VERSION, error: "request_id and idempotency_key must match.", ...identity.fields }, 409);
    }
    if (!identity.fields.request_id || !identity.fields.scan_id) {
      return jsonResponse({ success: false, version: VERSION, error: "A durable request_id and scan_id are required." }, 400);
    }

    // Standard 150 is the only customer scan. "advanced" is the Python
    // compatibility alias for the same mode; anything else is refused.
    const requestedMode = String(body.scan_mode || body.canonical_mode || body.audit_profile || PUBLIC_SCAN_MODE)
      .trim().toLowerCase();
    if (![PUBLIC_SCAN_MODE, "advanced"].includes(requestedMode)) {
      return jsonResponse({ success: false, version: VERSION, error: "Only the Standard 150 scan is available.", ...identity.fields }, 400);
    }

    const websiteUrl = normalizeWebsiteUrl(
      body.website_url || body.url || body.normalized_url || body.requested_start_url || body.start_url || "",
    );
    if (!websiteUrl) return jsonResponse({ success: false, version: VERSION, error: "Missing or invalid website_url.", ...identity.fields }, 400);
    const safety = validatePublicHttpUrl(websiteUrl);
    if (!safety.ok) return jsonResponse({ success: false, version: VERSION, error: safety.reason, ...identity.fields }, 400);

    // The owner-bound ScanRun must exist before any network work. This
    // gateway never creates one — it verifies ownership and identity only.
    const context = await loadOwnedScanContext({ base44, user, identity, websiteUrl });
    if (!context.ok) return jsonResponse({ success: false, version: VERSION, error: context.error, ...identity.fields }, context.status);

    const scannerUrl = scannerApiUrl();
    const scannerKey = scannerApiKey();
    const signingKey = String(Deno.env.get("SCAN_EVIDENCE_SIGNING_KEY") || "");
    if (!scannerUrl || !scannerKey || !signingKey) {
      // The async path requires sealed persistence; without configuration the
      // browser falls back to the synchronous path instead.
      return jsonResponse({
        success: false, accepted: false, version: VERSION, retryable: true,
        failure_code: !signingKey ? "signing_key_not_configured" : "scanner_not_configured",
        error: "The asynchronous scan path is not available.", ...identity.fields,
      }, 503);
    }

    const jobInput = {
      websiteUrl,
      identity: identity.fields,
      pathPrefix: String(body.path_prefix || body.requested_path_prefix || body.crawl_path_prefix || "") || null,
      businessName: String(body.business_name || body.project_name || ""),
      cmsPlatform: String(body.cms_platform || body.platform || ""),
      cmsName: String(body.cms_name || ""),
      importantKeywords: Array.isArray(body.important_keywords) ? body.important_keywords.slice(0, 20).map(String) : [],
      scannerUrl,
      scannerKey,
      signingKey,
    };

    // Hand the job to Cloud Tasks and answer immediately.
    //
    // waitUntil() used to run the crawl here. Base44 reaps post-response work,
    // so scan 6a748d5f9e8a27963ae678dc logged worker_scan_start and then
    // produced nothing for 247s until the watchdog closed it as
    // orphaned_no_terminal_state. Nothing long-running may live in this
    // function; the durable worker owns execution from here.
    const queuePath = String(Deno.env.get("SCAN_TASKS_QUEUE_PATH") || "");
    const workerUrl = String(Deno.env.get("SCAN_WORKER_URL") || "");
    const invokerServiceAccount = String(Deno.env.get("TASKS_INVOKER_SERVICE_ACCOUNT") || "");
    if (!queuePath || !workerUrl || !invokerServiceAccount) {
      return jsonResponse({
        success: false, accepted: false, version: VERSION, retryable: true,
        failure_code: "durable_worker_not_configured",
        error: "The asynchronous scan path is not available.", ...identity.fields,
      }, 503);
    }

    // The attempt the browser already recorded on the durable row. Task
    // identity, worker validation and every control envelope are bound to it,
    // so a task minted for an earlier attempt cannot act on a newer one.
    const attemptCount = normalizeAttemptCount(context.scan?.attempt_count);

    const enqueued = await enqueueScanJob({
      queuePath,
      workerUrl,
      invokerServiceAccount,
      scanId: identity.fields.scan_id,
      attemptCount,
      payload: {
        scan_id: identity.fields.scan_id,
        attempt_count: attemptCount,
        request_id: identity.fields.request_id,
        idempotency_key: identity.fields.idempotency_key,
        project_id: String(context.scan?.project_id || ""),
        owner_user_id: String(user.id),
        website_url: websiteUrl,
        path_prefix: jobInput.pathPrefix,
        normalized_domain: identity.fields.normalized_domain,
        business_name: jobInput.businessName,
        cms_platform: jobInput.cmsPlatform,
        scan_mode: PUBLIC_SCAN_MODE,
        respect_robots_txt: true,
      },
    });
    if (!enqueued.ok) {
      // Nothing was started, so nothing is charged and the ScanRun is closed
      // truthfully rather than left active with no owner.
      await failOwnedScanRun({ base44, context, identity: identity.fields, failureCode: enqueued.failureCode });
      return jsonResponse({
        success: false, accepted: false, version: VERSION, retryable: true,
        failure_code: enqueued.failureCode,
        error: "The scan job could not be queued. Nothing was charged.", ...identity.fields,
      }, 503);
    }
    logBoundary("async_job_accepted", { ...identity.fields, attempt_count: attemptCount, task_name: enqueued.taskName, deduplicated: enqueued.deduplicated === true });
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
      ...identity.fields,
    });
  } catch (error) {
    console.error("startStandardScanJob failed", { message: String(error?.message || error).slice(0, 180) });
    return jsonResponse({ success: false, accepted: false, version: VERSION, error: "The scan job could not be submitted.", retryable: true }, 500);
  }
}

// ---------------------------------------------------------------------------
// Background worker
// ---------------------------------------------------------------------------

async function runScanJob({ base44, user, context, jobInput }) {
  const identity = jobInput.identity;
  try {
    logBoundary("worker_scan_start", identity);
    const upstream = await fetchScannerResult(jobInput);
    if (upstream.failureCode) {
      await failOwnedScanRun({ base44, context, identity, failureCode: upstream.failureCode });
      return;
    }
    const result = upstream.result;

    await markReviewing(base44, context);
    logBoundary("worker_review_start", identity);

    const attested = await attachScanAttestation({ user, result, context, signingKey: jobInput.signingKey });
    const reviewData = await invokeFunction(base44, "aiReviewScan", {
      authoritative_scan: {
        authority_review_payload: attested.authority_review_payload,
        authority_scan_attestation: attested.authority_scan_attestation,
        authority_attestation_status: "server_attested",
      },
      client_context: buildClientContext(jobInput),
    });
    if (!reviewData || reviewData.success === false) {
      await failOwnedScanRun({ base44, context, identity, failureCode: "review_failed" });
      return;
    }
    const attestation = reviewData.authority_review_attestation;
    if (!attestation) {
      await failOwnedScanRun({ base44, context, identity, failureCode: "review_attestation_missing" });
      return;
    }

    logBoundary("worker_persist_start", identity);
    const persisted = await invokeFunction(base44, "persistScanAuthority", {
      scan_id: identity.scan_id,
      attestation,
    });
    if (!persisted || persisted.success === false) {
      await failOwnedScanRun({ base44, context, identity, failureCode: "persistence_failed" });
      return;
    }

    // Verify the sealed durable row before anything is consumed.
    const sealedRun = await readSealedRun(base44, identity.scan_id);
    if (!sealedRun) {
      await failOwnedScanRun({ base44, context, identity, failureCode: "persistence_failed" });
      return;
    }

    // Allowance is consumed ONLY here: after the authority-sealed FixList is
    // durably saved. A failed, cancelled, or timed-out scan never reaches this
    // line, so it never consumes the customer's allowance.
    await consumeScanAllowance(base44, user);
    logBoundary("worker_complete", identity, { fix_list_id: sealedRun.fix_list_id || "" });
  } catch (error) {
    logBoundary("worker_error", identity, { message: String(error?.message || error).slice(0, 160) });
    await failOwnedScanRun({
      base44, context, identity,
      failureCode: isTimeoutError(error) ? "timeout" : "worker_error",
    }).catch(() => {});
  }
}

async function fetchScannerResult(jobInput) {
  const { websiteUrl, identity } = jobInput;
  const upstreamPayload = {
    website_url: websiteUrl,
    path_prefix: jobInput.pathPrefix,
    scan_mode: PYTHON_COMPATIBILITY_MODE,
    business_name: jobInput.businessName,
    cms_platform: jobInput.cmsPlatform,
    request_id: identity.request_id,
    idempotency_key: identity.idempotency_key,
    scan_id: identity.scan_id,
    scan_run_id: identity.scan_run_id,
    submitted_url: identity.submitted_url || websiteUrl,
    normalized_domain: identity.normalized_domain,
    respect_robots_txt: true,
    advisory_crawl_timeout_ms: ASYNC_WORKER_BUDGET_MS,
    async_job: true,
  };

  let response;
  try {
    response = await fetchWithTimeout(`${jobInput.scannerUrl}/scan`, {
      method: "POST",
      headers: { "content-type": "application/json", "x-scanner-key": jobInput.scannerKey },
      body: JSON.stringify(upstreamPayload),
    }, UPSTREAM_FETCH_TIMEOUT_MS);
  } catch (error) {
    return { failureCode: isTimeoutError(error) ? "timeout" : "worker_error" };
  }

  const text = await response.text().catch(() => "");
  const upstream = parseJson(text);
  if (!response.ok || !upstream || upstream.success === false) {
    return { failureCode: !response.ok ? `http_${response.status}` : (upstream ? "scanner_success_false" : "parse_failure") };
  }
  if (upstream.scanner_version !== PYTHON_SCANNER_VERSION) return { failureCode: "version_mismatch" };
  if (!matchesUpstreamIdentity(upstream, identity)) return { failureCode: "identity_mismatch" };

  const pages = firstPageArray(upstream);
  // pages_found is broad-discovery evidence and stays separate from
  // pages_crawled; only the crawled evidence arrays are capped at 150.
  if (nonNegativeInteger(upstream.pages_crawled) > MAX_PAGES || pages.length > MAX_PAGES) {
    return { failureCode: "page_cap_violation" };
  }

  const cappedPages = pages.slice(0, MAX_PAGES);
  const pageCount = Math.min(MAX_PAGES, cappedPages.length || nonNegativeInteger(upstream.pages_crawled));
  const technical = upstream.technical_audit_summary && typeof upstream.technical_audit_summary === "object"
    ? upstream.technical_audit_summary
    : {};
  return {
    result: {
      ...upstream,
      success: true,
      wrapper_version: VERSION,
      scanner_wrapper_version: VERSION,
      scanner_version: PYTHON_SCANNER_VERSION,
      scan_mode: PUBLIC_SCAN_MODE,
      canonical_mode: PUBLIC_SCAN_MODE,
      audit_profile: PUBLIC_SCAN_MODE,
      max_pages: MAX_PAGES,
      ...identityEcho(identity),
      respect_robots_txt: true,
      advanced_scan_backend: "python_scanner_api",
      scanner_backend: "python_scanner_api",
      deno_fallback_used: false,
      pages: cappedPages,
      crawled_pages: cappedPages,
      pages_crawled: pageCount,
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
    },
  };
}

async function attachScanAttestation({ user, result, context, signingKey }) {
  const reviewPayload = buildAuthorityReviewPayload(result);
  const document = {
    version: SCAN_ATTESTATION_VERSION,
    owner_user_id: String(user.id),
    scan_id: String(context.scan.id),
    project_id: String(context.scan.project_id),
    normalized_domain: context.expectedDomain,
    result: reviewPayload,
  };
  const proof = await createAuthoritySeal(document, signingKey);
  return {
    authority_review_payload: reviewPayload,
    authority_scan_attestation: {
      version: SCAN_ATTESTATION_VERSION,
      owner_user_id: String(user.id),
      scan_id: String(context.scan.id),
      project_id: String(context.scan.project_id),
      normalized_domain: context.expectedDomain,
      proof,
    },
  };
}

function buildAuthorityReviewPayload(result = {}) {
  const pages = firstPageArray(result).slice(0, REVIEW_PAGE_SAMPLE_LIMIT);
  const findings = firstFindingArray(result).slice(0, REVIEW_FINDING_LIMIT);
  const technical = result.technical_audit_summary && typeof result.technical_audit_summary === "object" ? result.technical_audit_summary : {};
  const scanSummary = result.scan_summary && typeof result.scan_summary === "object" ? result.scan_summary : {};
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

function buildClientContext(jobInput) {
  return {
    business_name: jobInput.businessName,
    cms_platform: jobInput.cmsPlatform,
    cms_name: jobInput.cmsName,
    important_keywords: jobInput.importantKeywords,
    requested_path_prefix: jobInput.pathPrefix || "",
    coverage_instruction: "Use the server-attested scan page counts. Do not describe a sample sent to review as the total scan size.",
    ai_review_goal: "Create a customer-friendly FixList that prioritizes business-important pages first. Preserve URL evidence, group template-level problems, and do not treat suspicious crawler artifacts as confirmed broken links.",
    cms_instruction: `Tailor fixes for ${jobInput.cmsName || jobInput.cmsPlatform || "a custom or unknown CMS"}. Explain which changes a site editor can make and which likely need a developer.`,
    business_priority_instruction: {
      rule: "Prioritize by business importance, not just technical severity.",
      requested_path_prefix: jobInput.pathPrefix || "",
    },
    output_requirements: {
      keep_language_simple: true,
      group_similar_issues: true,
      preserve_url_evidence_fields: true,
      use_scan_coverage_for_page_counts: true,
    },
  };
}

// ---------------------------------------------------------------------------
// Durable state
// ---------------------------------------------------------------------------

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

async function markReviewing(base44, context) {
  try {
    await base44.entities.ScanRun.update(context.scan.id, { status: "reviewing", reviewing_at: new Date().toISOString() });
  } catch {
    // Non-fatal: the terminal write is the state that matters.
  }
}

async function readSealedRun(base44, scanId, attempts = 3) {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const run = await base44.entities.ScanRun.get(scanId).catch(() => null);
    const proof = String(run?.authority_proof || "").trim().toLowerCase();
    if (
      run
      && PROTECTED_SCAN_STATUSES.has(String(run.status || "").toLowerCase())
      && /^[a-f0-9]{64}$/.test(proof)
      && run.fix_list_id
    ) return run;
    if (attempt < attempts - 1) await sleep(2_000);
  }
  return null;
}

// Consumed ONLY after readSealedRun verified the durable, sealed result.
async function consumeScanAllowance(base44, user) {
  try {
    const email = String(user?.email || "").toLowerCase();
    if (!email) return;
    const records = await base44.entities.Access.filter({ user_email: email }).catch(() => []);
    const record = Array.isArray(records) ? records[0] || null : null;
    if (record?.has_full_access === true) return;
    if (record) {
      await base44.entities.Access.update(record.id, { scans_used: Number(record.scans_used || 0) + 1 });
    } else {
      await base44.entities.Access.create({ user_email: email, scans_used: 1, has_full_access: false });
    }
  } catch (error) {
    console.error("startStandardScanJob allowance write failed", { message: String(error?.message || error).slice(0, 160) });
  }
}

async function failOwnedScanRun({ base44, context, identity, failureCode }) {
  if (!context?.ok || !context.scan?.id) return;
  let current = null;
  try {
    current = await base44.entities.ScanRun.get(context.scan.id);
  } catch {
    return; // Refuse to write blind rather than risk clobbering a sealed run.
  }
  const currentStatus = String(current?.status || "").toLowerCase();
  if (!current || PROTECTED_SCAN_STATUSES.has(currentStatus)) return;
  try {
    await base44.entities.ScanRun.update(context.scan.id, {
      status: "failed",
      status_detail: customerStatusDetail(failureCode),
      error_code: failureCode,
      error_message: customerStatusDetail(failureCode),
      completed_at: new Date().toISOString(),
      release_gate_eligible: false,
    });
    logBoundary("worker_terminal_failed", identity, { failure_code: failureCode });
  } catch (error) {
    console.error("startStandardScanJob terminal write failed", {
      request_id: identity?.request_id,
      scan_id: identity?.scan_id,
      failure_code: failureCode,
      update_error: String(error?.message || error).slice(0, 160),
    });
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function invokeFunction(base44, functionName, payload) {
  try {
    const response = await base44.functions.invoke(functionName, payload);
    return response?.data ?? response ?? null;
  } catch (error) {
    console.error("startStandardScanJob invoke failed", { function_name: functionName, message: String(error?.message || error).slice(0, 160) });
    return null;
  }
}

function customerStatusDetail(failureCode) {
  return CUSTOMER_STATUS_DETAIL[failureCode]
    || "The scan did not complete. No partial result was saved. Please try again.";
}

function identityEcho(identity) {
  return {
    request_id: identity.request_id,
    idempotency_key: identity.idempotency_key,
    scan_id: identity.scan_id,
    scan_run_id: identity.scan_run_id,
    submitted_url: identity.submitted_url,
    normalized_domain: identity.normalized_domain,
  };
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

function firstPageArray(result = {}) {
  for (const key of ["crawled_pages", "pages", "scanned_pages", "crawl_pages"]) {
    if (Array.isArray(result[key])) return result[key];
  }
  return [];
}

function firstFindingArray(result = {}) {
  for (const key of ["grouped_findings", "recommendations", "findings", "raw_findings", "fixes"]) {
    if (Array.isArray(result[key])) return result[key];
  }
  return [];
}

function boundedArray(value, limit) {
  return Array.isArray(value) ? value.slice(0, limit) : [];
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
  return /abort|timeout/i.test(`${error?.name || ""} ${error?.message || ""}`);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Identity only — never payloads, evidence, attestations, proofs, or keys.
function logBoundary(boundary, identity, extra = {}) {
  console.info("[fixlist.scanjob]", {
    boundary,
    request_id: identity?.request_id || "",
    scan_id: identity?.scan_id || "",
    at: new Date().toISOString(),
    ...extra,
  });
}