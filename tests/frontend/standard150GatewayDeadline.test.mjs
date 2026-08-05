// Deadline + terminal-failure contract for the Standard 150 gateway.
//
// The gateway and scanRuns.js cannot be imported under `node --test` (Deno
// globals, "@/" aliases, browser boundaries), so the numeric constants are
// extracted and the deadline inequalities are *computed*, not string-matched.
// A previous version of this file asserted `crawl_timeout_ms` was forwarded to
// Python, which was a fictional guarantee: scanner-api's ScanRequest never
// declared that field, so pydantic dropped it.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const gateway = fs.readFileSync("base44/functions/runStandard150Scan/entry.ts", "utf8");
const form = fs.readFileSync("src/components/scan/ScanWebsiteForm.jsx", "utf8");
const scanRuns = fs.readFileSync("src/lib/scanRuns.js", "utf8");
const pythonScanner = fs.readFileSync("scanner-api/app/scanner.py", "utf8");
const pythonMain = fs.readFileSync("scanner-api/app/main.py", "utf8");

function gatewayConst(name) {
  const raw = gateway.match(new RegExp(`const ${name} = ([0-9_]+);`))?.[1];
  assert.ok(raw, `gateway constant ${name} not found`);
  return Number(raw.replace(/_/g, ""));
}

const PYTHON_CRAWL_BUDGET_MS = gatewayConst("PYTHON_CRAWL_BUDGET_MS");
const BROWSER_DEADLINE_MS = gatewayConst("BROWSER_DEADLINE_MS");
const FUNCTION_RESPONSE_BUDGET_MS = gatewayConst("FUNCTION_RESPONSE_BUDGET_MS");
const RESPONSE_RESERVE_MS = gatewayConst("RESPONSE_RESERVE_MS");
const UPSTREAM_RESPONSE_RESERVE_MS = gatewayConst("UPSTREAM_RESPONSE_RESERVE_MS");

// Mirrors the gateway's arithmetic for a given pre-fetch elapsed time.
function upstreamTimeoutFor(elapsedMs) {
  return FUNCTION_RESPONSE_BUDGET_MS - elapsedMs - RESPONSE_RESERVE_MS;
}

test("1. Python's real crawl budget is 75 seconds and is not caller-controlled", () => {
  const advanced = pythonScanner.match(/"advanced":\s*\{[^}]*"timeout":\s*(\d+)/)?.[1];
  assert.equal(Number(advanced), 75, "scanner.py advanced timeout must be 75s");
  assert.equal(PYTHON_CRAWL_BUDGET_MS, 75_000, "gateway must model Python's real budget");

  // The gateway must not claim to cap Python while ScanRequest lacks the field.
  const scanRequest = pythonMain.match(/class ScanRequest\(BaseModel\):([\s\S]*?)\n\n/)?.[1] || "";
  assert.ok(scanRequest.length > 0, "ScanRequest model not found");
  const pythonAcceptsCrawlTimeout = /crawl_timeout_ms/.test(scanRequest);
  assert.equal(
    pythonAcceptsCrawlTimeout,
    false,
    "ScanRequest now declares crawl_timeout_ms - revisit the advisory-only comment and the cap model",
  );
  assert.doesNotMatch(gateway, /^\s*crawl_timeout_ms:/m);
});

test("2. gateway timeout leaves headroom before the browser's 105s deadline", () => {
  assert.equal(BROWSER_DEADLINE_MS, 105_000);
  // Browser deadline is derived in the form as crawl_timeout_ms + 15000.
  const formCrawlTimeout = Number(form.match(/crawl_timeout_ms: (\d+)/)?.[1]);
  const formPad = Number(form.match(/crawl_timeout_ms \|\| 30000\) \+ (\d+)/)?.[1]);
  assert.equal(formCrawlTimeout + formPad, BROWSER_DEADLINE_MS);

  for (const elapsed of [0, 1_000, 5_000, 10_000]) {
    const upstream = upstreamTimeoutFor(elapsed);
    // Inner inequality: we outlast Python's fixed budget plus its serialization.
    assert.ok(
      upstream > PYTHON_CRAWL_BUDGET_MS + UPSTREAM_RESPONSE_RESERVE_MS,
      `upstream ${upstream} must exceed Python budget + reserve at elapsed ${elapsed}`,
    );
    // Outer inequality: we still answer before the browser gives up.
    assert.ok(
      upstream + RESPONSE_RESERVE_MS + elapsed < BROWSER_DEADLINE_MS,
      `upstream ${upstream} + reserve must land before the browser deadline at elapsed ${elapsed}`,
    );
  }
});

test("2b. the budget guard rejects rather than starting a doomed scan", () => {
  assert.match(
    gateway,
    /if \(upstreamTimeoutMs <= PYTHON_CRAWL_BUDGET_MS \+ UPSTREAM_RESPONSE_RESERVE_MS\)/,
  );
  assert.match(gateway, /failureCode: "insufficient_gateway_budget"/);
  // The guard must actually be reachable within the function budget.
  const breakEven = FUNCTION_RESPONSE_BUDGET_MS - RESPONSE_RESERVE_MS
    - (PYTHON_CRAWL_BUDGET_MS + UPSTREAM_RESPONSE_RESERVE_MS);
  assert.ok(breakEven > 0 && breakEven < FUNCTION_RESPONSE_BUDGET_MS);
});

test("3. every gateway-observed failure persists ScanRun as failed", () => {
  assert.match(gateway, /async function failOwnedScanRun/);
  assert.match(gateway, /status: "failed"/);
  assert.match(gateway, /release_gate_eligible: false/);
  assert.match(gateway, /completed_at: new Date\(\)\.toISOString\(\)/);
  assert.match(gateway, /ScanRun\.update\(context\.scan\.id/);
  assert.match(gateway, /async function unavailable/);

  // Every unavailable() call site must await and pass base44 + context, or the
  // terminal write silently never happens.
  const invocations = (gateway.match(/return await unavailable\(\{[\s\S]{0,220}?\}\);/g) || []);
  assert.ok(invocations.length >= 7, `expected >=7 failure paths, found ${invocations.length}`);
  for (const site of invocations) {
    assert.match(site, /base44/, `unavailable() call site missing base44: ${site.slice(0, 80)}`);
    assert.match(site, /context/, `unavailable() call site missing context: ${site.slice(0, 80)}`);
  }
  for (const code of [
    "url_not_configured", "key_not_configured", "insufficient_gateway_budget",
    "timeout", "scanner_success_false", "version_mismatch", "identity_mismatch",
    "page_cap_violation", "parse_failure", "gateway_error",
  ]) {
    assert.match(gateway, new RegExp(code), `missing failure code ${code}`);
  }
});

test("4. a complete or limited ScanRun is never overwritten", () => {
  assert.match(gateway, /PROTECTED_SCAN_STATUSES = new Set\(\["complete", "limited"\]\)/);
  assert.match(gateway, /if \(PROTECTED_SCAN_STATUSES\.has\(String\(context\.scan\.status/);
  assert.match(scanRuns, /PROTECTED_SCAN_STATUSES = new Set\(\["complete", "limited"\]\)/);
  assert.match(scanRuns, /!PROTECTED_SCAN_STATUSES\.has\(String\(run\.status/);
});

test("5. a stale active run becomes failed and frees the key for retry", () => {
  assert.match(scanRuns, /error_code: "orphaned_no_terminal_state"/);
  assert.match(scanRuns, /status_detail: STALE_RUN_STATUS_DETAIL/);
  assert.match(scanRuns, /release_gate_eligible: false/);
  assert.match(scanRuns, /terminalizeStaleScanRuns\(replay\.staleRuns\)/);
  // Retry reuses the same durable row via the existing idempotency contract.
  assert.match(scanRuns, /restartStaleRequestRun/);
  assert.match(scanRuns, /buildStaleScanRetryFields/);
  // No fabricated results, no backfilled scanner identity.
  assert.doesNotMatch(scanRuns, /status: "complete",[\s\S]{0,200}orphaned/);
});

test("6. a fresh active run is not failed by recovery", () => {
  const identity = fs.readFileSync("src/lib/scanRunIdentity.js", "utf8");
  const ttl = identity.match(/STANDARD_ACTIVE_SCAN_TTL_MS = (\d+) \* 60 \* 1000/)?.[1];
  assert.equal(Number(ttl), 10, "stale threshold must be 10 minutes");
  assert.match(identity, /ACTIVE_SCAN_RUN_STATUSES = new Set\(\["queued", "crawling", "reviewing"\]\)/);
  // Staleness is time-gated, so a fresh run is never in staleRuns.
  assert.match(identity, /isStaleActiveScanRun/);
  assert.match(identity, /activeTtlMs = STANDARD_ACTIVE_SCAN_TTL_MS/);
});

test("7. failure-write errors are logged without secrets or proofs", () => {
  const logBlock = gateway.match(/console\.error\("runStandard150Scan terminal write failed",[\s\S]*?\}\);/)?.[0] || "";
  assert.ok(logBlock, "terminal write failure must be logged");
  for (const field of ["request_id", "scan_id", "failure_code", "update_error"]) {
    assert.match(logBlock, new RegExp(field), `terminal write log missing ${field}`);
  }
  // No secret or authority material anywhere in gateway logging.
  for (const forbidden of [/console\.[a-z]+\([^)]*scannerKey/, /console\.[a-z]+\([^)]*proof/, /console\.[a-z]+\([^)]*SIGNING_KEY/]) {
    assert.doesNotMatch(gateway, forbidden);
  }
  // Customer-facing text must not leak internal codes.
  assert.match(gateway, /function customerStatusDetail/);
  assert.doesNotMatch(gateway, /error: `[^`]*\$\{failureCode\}/);
});

test("8. no Grok, Premium, Deno fallback, or scanner-engine change", () => {
  for (const forbidden of [/grok/i, /premium/i, /crawlWebsite/, /InvokeLLM/, /extractLinks/]) {
    assert.doesNotMatch(gateway, forbidden);
  }
  assert.match(gateway, /deno_fallback_used: false/);
  assert.doesNotMatch(gateway, /deno_fallback_used: true/);
  assert.doesNotMatch(gateway, /allow_deno_fallback: true/);
  // Standard 150 contract intact.
  assert.match(gateway, /const MAX_PAGES = 150/);
  assert.match(gateway, /respect_robots_txt: true/);
  assert.match(gateway, /const PUBLIC_SCAN_MODE = "standard_150"/);
});
