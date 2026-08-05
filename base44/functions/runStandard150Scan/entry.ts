import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";

const VERSION = "runStandard150Scan_v1_python_required";
const PYTHON_SCANNER_VERSION = "python_scanner_v3_bounded_request";
const CANONICAL_MODE = "standard_150";
const PYTHON_COMPATIBILITY_MODE = "advanced";
const MAX_PAGES = 150;
const FETCH_TIMEOUT_MS = 85_000;
const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

Deno.serve(async (req) => {
  const startedAt = Date.now();
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS_HEADERS });
  if (req.method !== "POST") return jsonResponse({ success: false, version: VERSION, error: "Method not allowed." }, 405);

  let body: Record<string, unknown> = {};
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me().catch(() => null);
    if (!user) return jsonResponse({ success: false, version: VERSION, error: "Unauthorized." }, 401);

    body = unwrapRequestBody(await safeReadJson(req));
    const identity = resolveIdentity(body);
    if (identity.conflict) {
      return jsonResponse({
        success: false,
        version: VERSION,
        error: "request_id and idempotency_key must match.",
        ...identity.fields,
      }, 409);
    }

    const requestedMode = String(body.scan_mode || body.audit_profile || CANONICAL_MODE).trim().toLowerCase();
    if (![CANONICAL_MODE, PYTHON_COMPATIBILITY_MODE].includes(requestedMode)) {
      return jsonResponse({
        success: false,
        version: VERSION,
        error: "FixList supports only the Standard 150 scan.",
        canonical_mode: CANONICAL_MODE,
        ...identity.fields,
      }, 400);
    }

    const websiteUrl = normalizeWebsiteUrl(
      body.website_url || body.url || body.normalized_url || body.requested_start_url || body.start_url || body.target_url || "",
    );
    if (!websiteUrl) {
      return jsonResponse({ success: false, version: VERSION, error: "Missing or invalid website_url.", ...identity.fields }, 400);
    }
    const safety = validatePublicHttpUrl(websiteUrl);
    if (!safety.ok) {
      return jsonResponse({ success: false, version: VERSION, error: safety.reason, ...identity.fields }, 400);
    }

    const scannerUrl = String(
      Deno.env.get("SCANNER_API_URL")
      || Deno.env.get("PYTHON_SCANNER_API_URL")
      || Deno.env.get("PYTHON_SCANNER_URL")
      || Deno.env.get("SCANNER_URL")
      || Deno.env.get("cloud_api")
      || Deno.env.get("CLOUD_API")
      || "",
    ).replace(/\/+$/, "");
    const scannerKey = String(Deno.env.get("SCANNER_API_KEY") || Deno.env.get("PYTHON_SCANNER_API_KEY") || "");

    if (!scannerUrl || !scannerKey) {
      return jsonResponse({
        success: false,
        version: VERSION,
        error: "The Standard 150 scanner is temporarily unavailable.",
        detail: !scannerUrl ? "scanner_url_not_configured" : "scanner_key_not_configured",
        retryable: true,
        canonical_mode: CANONICAL_MODE,
        advanced_scan_backend: "python_scanner_api_unavailable",
        deno_fallback_used: false,
        release_gate_eligible: false,
        ...identity.fields,
      }, 503);
    }

    const pathPrefix = String(body.path_prefix || body.requested_path_prefix || body.crawl_path_prefix || "").trim();
    const response = await fetchWithTimeout(`${scannerUrl}/scan`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-scanner-key": scannerKey,
      },
      body: JSON.stringify({
        website_url: websiteUrl,
        path_prefix: pathPrefix || null,
        scan_mode: PYTHON_COMPATIBILITY_MODE,
        canonical_mode: CANONICAL_MODE,
        max_pages: MAX_PAGES,
        business_name: String(body.business_name || body.project_name || ""),
        cms_platform: String(body.cms_platform || body.platform || ""),
        request_id: identity.fields.request_id,
        idempotency_key: identity.fields.idempotency_key,
        scan_id: identity.fields.scan_id,
        scan_run_id: identity.fields.scan_run_id,
        submitted_url: identity.fields.submitted_url || websiteUrl,
        normalized_domain: identity.fields.normalized_domain || normalizedDomain(websiteUrl),
        respect_robots_txt: true,
      }),
    }, FETCH_TIMEOUT_MS);

    const responseText = await response.text();
    const result = parseJson(responseText) || { success: false, error: "Invalid scanner response." };
    if (!response.ok || result.success === false) {
      console.error("Standard 150 Python scanner request failed", {
        status: response.status,
        failure: String(result.detail || result.error || "request_failed").slice(0, 180),
        request_id: identity.fields.request_id,
        scan_id: identity.fields.scan_id,
      });
      return jsonResponse({
        success: false,
        version: VERSION,
        error: "The Standard 150 scanner is temporarily unavailable.",
        detail: `python_scanner_http_${response.status}`,
        retryable: response.status >= 500 || response.status === 408 || response.status === 429,
        canonical_mode: CANONICAL_MODE,
        advanced_scan_backend: "python_scanner_api_unavailable",
        deno_fallback_used: false,
        release_gate_eligible: false,
        ...identity.fields,
        elapsed_ms: Date.now() - startedAt,
      }, 503);
    }

    if (result.scanner_version !== PYTHON_SCANNER_VERSION) {
      return jsonResponse({
        success: false,
        version: VERSION,
        error: "The Standard 150 scanner returned an unrecognized release.",
        detail: "python_scanner_version_mismatch",
        retryable: false,
        canonical_mode: CANONICAL_MODE,
        advanced_scan_backend: "python_scanner_api_unavailable",
        deno_fallback_used: false,
        release_gate_eligible: false,
        ...identity.fields,
      }, 503);
    }

    const pagesCrawled = Number(result.pages_crawled || result.pages_scanned || result.technical_audit_summary?.pages_crawled || 0);
    if (pagesCrawled > MAX_PAGES) {
      return jsonResponse({
        success: false,
        version: VERSION,
        error: "The scanner response exceeded the Standard 150 page contract.",
        detail: "standard_150_page_cap_violation",
        retryable: false,
        canonical_mode: CANONICAL_MODE,
        advanced_scan_backend: "python_scanner_api_unavailable",
        deno_fallback_used: false,
        release_gate_eligible: false,
        ...identity.fields,
      }, 503);
    }

    const technical = result.technical_audit_summary && typeof result.technical_audit_summary === "object"
      ? result.technical_audit_summary
      : {};

    return jsonResponse({
      ...result,
      success: true,
      version: VERSION,
      scanner_wrapper_version: VERSION,
      scanner_version: result.scanner_version,
      scan_mode: CANONICAL_MODE,
      canonical_mode: CANONICAL_MODE,
      audit_profile: CANONICAL_MODE,
      backend_scan_mode: PYTHON_COMPATIBILITY_MODE,
      max_pages: MAX_PAGES,
      respect_robots_txt: true,
      advanced_scan_backend: "python_scanner_api",
      deno_fallback_used: false,
      scanner_api_url_configured: true,
      release_gate_eligible: result.release_gate_eligible !== false,
      ...identity.fields,
      final_url: result.final_url || result.resolved_start_url || result.pages?.[0]?.final_url || result.normalized_url || result.website_url || websiteUrl,
      normalized_domain: result.normalized_domain || identity.fields.normalized_domain || normalizedDomain(websiteUrl),
      technical_audit_summary: {
        ...technical,
        scanner_version: result.scanner_version,
        scanner_wrapper_version: VERSION,
        canonical_mode: CANONICAL_MODE,
        backend_scan_mode: PYTHON_COMPATIBILITY_MODE,
        max_pages: MAX_PAGES,
        respect_robots_txt: true,
        advanced_scan_backend: "python_scanner_api",
        deno_fallback_used: false,
        python_scanner_fallback_reason: "",
      },
      elapsed_ms: Date.now() - startedAt,
    });
  } catch (error) {
    const message = String(error?.message || error || "unknown error");
    console.error("runStandard150Scan failed", {
      error: message.slice(0, 180),
      request_id: String(body.request_id || body.idempotency_key || ""),
      scan_id: String(body.scan_id || body.scan_run_id || ""),
    });
    return jsonResponse({
      success: false,
      version: VERSION,
      error: "The Standard 150 scanner is temporarily unavailable.",
      detail: /abort|timeout/i.test(message) ? "python_scanner_timeout" : "standard_150_gateway_failure",
      retryable: true,
      canonical_mode: CANONICAL_MODE,
      advanced_scan_backend: "python_scanner_api_unavailable",
      deno_fallback_used: false,
      release_gate_eligible: false,
      ...resolveIdentity(body).fields,
      elapsed_ms: Date.now() - startedAt,
    }, 503);
  }
});

function resolveIdentity(body: Record<string, unknown> = {}) {
  const requestId = String(body.request_id || body.idempotency_key || "").trim();
  const idempotencyKey = String(body.idempotency_key || requestId).trim();
  const scanId = String(body.scan_id || body.scan_run_id || "").trim();
  const submittedUrl = String(body.submitted_url || body.requested_start_url || body.website_url || "").trim();
  return {
    conflict: Boolean(requestId && idempotencyKey && requestId !== idempotencyKey),
    fields: {
      request_id: requestId,
      idempotency_key: idempotencyKey,
      scan_id: scanId,
      scan_run_id: scanId,
      submitted_url: submittedUrl,
      normalized_domain: String(body.normalized_domain || normalizedDomain(String(body.website_url || submittedUrl))),
    },
  };
}

function unwrapRequestBody(raw: unknown): Record<string, unknown> {
  if (!raw || typeof raw !== "object") return {};
  const source = raw as Record<string, unknown>;
  if (source.website_url || source.url || source.normalized_url || source.requested_start_url) return source;
  for (const key of ["data", "body", "payload", "input", "args", "request"]) {
    const nested = source[key];
    if (nested && typeof nested === "object") return nested as Record<string, unknown>;
  }
  return source;
}

async function safeReadJson(req: Request) {
  try { return await req.json(); } catch { return {}; }
}

function parseJson(text: string) {
  try { return JSON.parse(text || "{}"); } catch { return null; }
}

async function fetchWithTimeout(url: string, options: RequestInit, timeoutMs: number) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try { return await fetch(url, { ...options, signal: controller.signal }); }
  finally { clearTimeout(timer); }
}

function normalizeWebsiteUrl(value: unknown) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  try {
    const url = new URL(/^https?:\/\//i.test(raw) ? raw : `https://${raw}`);
    if (!/^https?:$/i.test(url.protocol) || !url.hostname || url.username || url.password) return "";
    url.hash = "";
    return url.href;
  } catch { return ""; }
}

function normalizedDomain(value: string) {
  try { return new URL(normalizeWebsiteUrl(value)).hostname.toLowerCase().replace(/\.$/, ""); }
  catch { return ""; }
}

function validatePublicHttpUrl(value: string) {
  try {
    const url = new URL(value);
    if (!/^https?:$/i.test(url.protocol)) return { ok: false, reason: "URL must use http or https." };
    const host = url.hostname.toLowerCase();
    if (!host || host === "localhost" || host.endsWith(".localhost")) return { ok: false, reason: "Localhost URLs are not allowed." };
    if (/^(127\.|10\.|0\.|169\.254\.|192\.168\.|172\.(1[6-9]|2\d|3[0-1])\.)/.test(host)) return { ok: false, reason: "Private network URLs are not allowed." };
    if (host === "::1" || host.startsWith("[::1")) return { ok: false, reason: "Private network URLs are not allowed." };
    return { ok: true, reason: "" };
  } catch { return { ok: false, reason: "Missing or invalid website_url." }; }
}

function jsonResponse(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...CORS_HEADERS, "content-type": "application/json" },
  });
}
