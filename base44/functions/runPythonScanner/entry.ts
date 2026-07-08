import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";

const VERSION = "runPythonScanner_wrapper_v1";
const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
const FETCH_TIMEOUT_MS = 120_000;

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS_HEADERS });
  if (req.method !== "POST") return jsonResponse({ success: false, version: VERSION, error: "Method not allowed" }, 405);

  let rawBody = {}, body = {};
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me().catch(() => null);
    if (!user) return jsonResponse({ success: false, version: VERSION, error: "Unauthorized" }, 401);

    rawBody = await safeReadJson(req);
    body = unwrapRequestBody(rawBody);

    const scannerUrl = String(Deno.env.get("SCANNER_API_URL") || Deno.env.get("PYTHON_SCANNER_API_URL") || "").replace(/\/+$/, "");
    const scannerKey = String(Deno.env.get("SCANNER_API_KEY") || Deno.env.get("PYTHON_SCANNER_API_KEY") || "");
    if (!scannerUrl) {
      return jsonResponse({ success: false, version: VERSION, error: "Python scanner is not configured. Set SCANNER_API_URL before using runPythonScanner." }, 503);
    }

    const websiteUrl = body.website_url || body.url || body.normalized_url || body.requested_start_url || body.start_url || body.target_url || "";
    if (!websiteUrl) return jsonResponse({ success: false, version: VERSION, error: "Missing website_url.", received_keys: Object.keys(rawBody || {}), resolved_keys: Object.keys(body || {}) }, 400);

    const payload = {
      website_url: websiteUrl,
      path_prefix: body.path_prefix || body.requested_path_prefix || body.crawl_path_prefix || null,
      scan_mode: body.scan_mode || body.audit_profile || "advanced",
      business_name: body.business_name || body.project_name || "",
      cms_platform: body.cms_platform || body.platform || "",
    };

    const response = await withTimeout(
      fetch(`${scannerUrl}/scan`, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          ...(scannerKey ? { "x-scanner-key": scannerKey } : {}),
        },
        body: JSON.stringify(payload),
      }),
      FETCH_TIMEOUT_MS,
    );

    const resultText = await response.text();
    const result = parseJson(resultText) || { success: false, error: resultText.slice(0, 500) };
    if (!response.ok) {
      return jsonResponse({ success: false, version: VERSION, scanner_status: response.status, error: result.detail || result.error || "Python scanner request failed.", scanner_response: result }, response.status);
    }

    return jsonResponse({
      ...result,
      success: result.success !== false,
      wrapper_version: VERSION,
      scanner_backend: "python_scanner_api",
      scanner_api_url_configured: true,
      scan_mode: result.scan_mode || payload.scan_mode,
      audit_profile: result.audit_profile || result.scan_mode || payload.scan_mode,
    });
  } catch (error) {
    console.error("runPythonScanner failed", error);
    return jsonResponse({ success: false, version: VERSION, error: "Python scanner wrapper failed.", detail: String(error?.message || error || "unknown error").slice(0, 240), received_keys: Object.keys(rawBody || {}), resolved_keys: Object.keys(body || {}) }, 500);
  }
});

async function safeReadJson(req) {
  try { return await req.json(); } catch { return {}; }
}

function unwrapRequestBody(raw) {
  let body = raw && typeof raw === "object" ? raw : {};
  for (const key of ["data", "body", "payload", "request"]) {
    if (body?.[key] && typeof body[key] === "object") body = body[key];
  }
  return body;
}

function parseJson(text) {
  try { return JSON.parse(text || "{}"); } catch { return null; }
}

async function withTimeout(promise, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await Promise.race([
      promise,
      new Promise((_, reject) => setTimeout(() => reject(new Error(`Timed out after ${timeoutMs}ms`)), timeoutMs)),
    ]);
  } finally {
    clearTimeout(timer);
  }
}

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data, null, 2), {
    status,
    headers: { ...CORS_HEADERS, "content-type": "application/json" },
  });
}
