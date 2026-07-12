from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "base44/functions/runAdvancedScan/entry.ts"
TEST = ROOT / "tests/frontend/scan-response-deadline.test.mjs"


def replace_once(text: str, old: str, new: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Expected exactly one anchor, found {count}: {old[:120]!r}")
    return text.replace(old, new, 1)


text = TARGET.read_text()
text = replace_once(
    text,
    "const PYTHON_TIMEOUT_MS = 120000;",
    """const FUNCTION_RESPONSE_BUDGET_MS = 95000;
const RESPONSE_RESERVE_MS = 4000;
const MIN_FALLBACK_CRAWL_MS = 5000;
const PYTHON_TIMEOUTS_MS = {
  basic: 45000,
  quick: 55000,
  deep: 70000,
  advanced: 85000,
};""",
)
text = replace_once(
    text,
    "Deno.serve(async (req) => {\n",
    "Deno.serve(async (req) => {\n  const functionStartedAt = Date.now();\n",
)
text = replace_once(
    text,
    '''    const pathPrefix = body.path_prefix || body.requested_path_prefix || body.crawl_path_prefix || "";
    const scanMode = body.scan_mode || body.audit_profile || "advanced";
    const pythonAttempt = await tryPythonScanner({ body, websiteUrl, pathPrefix, scanMode });
    if (pythonAttempt.ok) return jsonResponse(toPythonAdvancedScanResponse(pythonAttempt.result, scanMode));

    const invokeLLM = typeof base44.integrations?.Core?.InvokeLLM === "function" ? async (prompt) => await base44.integrations.Core.InvokeLLM({ prompt }) : null;
    const fallbackReason = pythonAttempt.reason || "Python scanner unavailable; used Deno fallback.";
    const crawlResult = await crawlWebsite({ startUrl: websiteUrl, budget, pathPrefix, invokeLLM });
''',
    '''    const pathPrefix = body.path_prefix || body.requested_path_prefix || body.crawl_path_prefix || "";
    const scanMode = body.scan_mode || body.audit_profile || "advanced";
    const pythonTimeoutMs = resolvePythonTimeout(scanMode);
    const pythonAttempt = await tryPythonScanner({ body, websiteUrl, pathPrefix, scanMode, timeoutMs: pythonTimeoutMs });
    if (pythonAttempt.ok) return jsonResponse(toPythonAdvancedScanResponse(pythonAttempt.result, scanMode));

    const fallbackReason = pythonAttempt.reason || "Python scanner unavailable; used Deno fallback.";
    const remainingMs = FUNCTION_RESPONSE_BUDGET_MS - (Date.now() - functionStartedAt);
    if (remainingMs < MIN_FALLBACK_CRAWL_MS + RESPONSE_RESERVE_MS) {
      return jsonResponse({
        success: false,
        version: VERSION,
        error: "The Python scanner did not finish in time and there was not enough request time left for a safe fallback scan. Please retry with Quick check.",
        detail: fallbackReason,
        retryable: true,
        scanner_api_url_configured: pythonAttempt.configured,
        elapsed_ms: Date.now() - functionStartedAt,
      }, 503);
    }

    const fallbackBudget = {
      ...budget,
      crawl_timeout_ms: Math.min(
        budget.crawl_timeout_ms,
        Math.max(MIN_FALLBACK_CRAWL_MS, remainingMs - RESPONSE_RESERVE_MS),
      ),
      derive_policy: Boolean(budget.derive_policy && remainingMs >= 25000),
    };
    const invokeLLM = typeof base44.integrations?.Core?.InvokeLLM === "function" ? async (prompt) => await base44.integrations.Core.InvokeLLM({ prompt }) : null;
    const crawlResult = await crawlWebsite({ startUrl: websiteUrl, budget: fallbackBudget, pathPrefix, invokeLLM });
''',
)
text = replace_once(
    text,
    "async function tryPythonScanner({ body, websiteUrl, pathPrefix, scanMode }) {",
    "async function tryPythonScanner({ body, websiteUrl, pathPrefix, scanMode, timeoutMs }) {",
)
text = replace_once(
    text,
    "    }, PYTHON_TIMEOUT_MS);",
    "    }, Math.max(1000, Number(timeoutMs || PYTHON_TIMEOUTS_MS.advanced)));",
)
text = replace_once(
    text,
    'function resolveBudget(body) { const mode = String(body.scan_mode || body.audit_profile || "advanced").toLowerCase(); return MODE_LIMITS[mode] || MODE_LIMITS.advanced; }',
    '''function normalizeScanMode(value) { const mode = String(value || "advanced").toLowerCase(); if (mode === "standard") return "deep"; if (["full", "full_site", "full-site"].includes(mode)) return "advanced"; return mode; }
function resolvePythonTimeout(scanMode) { const mode = normalizeScanMode(scanMode); return PYTHON_TIMEOUTS_MS[mode] || PYTHON_TIMEOUTS_MS.advanced; }
function resolveBudget(body) { const mode = normalizeScanMode(body.scan_mode || body.audit_profile || "advanced"); return MODE_LIMITS[mode] || MODE_LIMITS.advanced; }''',
)
TARGET.write_text(text)

TEST.write_text('''import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs.readFileSync("base44/functions/runAdvancedScan/entry.ts", "utf8");

test("runAdvancedScan always budgets below the 105-second UI deadline", () => {
  assert.match(source, /FUNCTION_RESPONSE_BUDGET_MS = 95000/);
  assert.match(source, /quick: 55000/);
  assert.match(source, /advanced: 85000/);
  assert.doesNotMatch(source, /PYTHON_TIMEOUT_MS = 120000/);
  assert.match(source, /remainingMs = FUNCTION_RESPONSE_BUDGET_MS - \(Date\.now\(\) - functionStartedAt\)/);
  assert.match(source, /crawl_timeout_ms: Math\.min\(/);
  assert.match(source, /remainingMs - RESPONSE_RESERVE_MS/);
  assert.match(source, /not enough request time left for a safe fallback scan/);
});
''')
