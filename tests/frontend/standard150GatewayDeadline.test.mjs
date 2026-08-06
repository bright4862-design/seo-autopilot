// Deadline + terminal-failure contract for the Standard 150 gateway.
//
// The gateway and scanRuns.js cannot be imported under `node --test` (Deno
// globals, "@/" aliases, browser boundaries), so the numeric constants are
// extracted and the deadline inequalities are *computed*, not string-matched.
// The request-scoped timeout is now an authenticated, bounded scanner input;
// the normal Standard 150 page cap and standalone 75s scanner ceiling remain unchanged.
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

test("1. Standard stays capped at 150 pages with a 28-second gateway crawl budget", () => {
  const advanced = pythonScanner.match(/"advanced":\s*\{[^}]*"max_pages":\s*(\d+)[^}]*"timeout":\s*(\d+)/);
  assert.equal(Number(advanced?.[1]), 150, "Standard/advanced page maximum must remain 150");
  assert.equal(Number(advanced?.[2]), 75, "the normal standalone advanced timeout remains 75s");
  assert.equal(PYTHON_CRAWL_BUDGET_MS, 28_000, "gateway must preserve serialization headroom for large root-domain scans");

  const scanRequest = pythonMain.match(/class ScanRequest\(BaseModel\):([\s\S]*?)\n\n/)?.[1] || "";
  assert.ok(scanRequest.length > 0, "ScanRequest model not found");
  assert.match(scanRequest, /advisory_crawl_timeout_ms/);
  assert.match(gateway, /advisory_crawl_timeout_ms: PYTHON_CRAWL_BUDGET_MS/);
  assert.match(pythonMain, /timeout_seconds=request_timeout_seconds/);
  assert.match(pythonScanner, /def resolve_scan_budget/);
  assert.match(pythonScanner, /max\(20\.0, min\(float\(base\["timeout"\]\), requested\)\)/);
});

test("2. gateway timeout leaves headroom before the browser's 105s deadline", () => {
  assert.equal(BROWSER_DEADLINE_MS, 105_000);
  // Browser deadline is derived in the form as crawl_timeout_ms + 15000.
  const formCrawlTimeout = Number(form.match(/crawl_timeout_ms: (\d+)/)?.[1]);
  const formPad = Number(form.match(/crawl_timeout_ms \|\| 30000\) \+ (\d+)/)?.[1]);
  assert.equal(formCrawlTimeout + formPad, BROWSER_DEADLINE_MS);

  assert.equal(FUNCTION_RESPONSE_BUDGET_MS, 55_000);
  for (const elapsed of [0, 1_000, 4_000]) {
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



test("2c. authority review uses a bounded signed envelope instead of the full scan", () => {
  const aiReview = fs.readFileSync("base44/functions/aiReviewScan/entry.ts", "utf8");
  assert.match(gateway, /const REVIEW_PAGE_SAMPLE_LIMIT = 60/);
  assert.match(gateway, /const REVIEW_FINDING_LIMIT = 100/);
  assert.match(gateway, /standard_scan_review_payload_hmac_v2/);
  assert.match(gateway, /result: reviewPayload/);
  assert.match(gateway, /authority_review_payload: reviewPayload/);
  const compactBuilder = gateway.match(/function buildAuthorityReviewPayload[\s\S]*?\n\}/)?.[0] || "";
  assert.ok(compactBuilder, "compact review payload builder not found");
  assert.match(compactBuilder, /crawled_pages: pages/);
  assert.match(compactBuilder, /grouped_findings: findings/);
  assert.doesNotMatch(compactBuilder, /^\s*pages,/m);
  assert.doesNotMatch(compactBuilder, /^\s*(raw_findings|findings|recommendations):?\s*findings/m);
  assert.match(gateway, /boundedArray\(result\.verified_failed_pages, 25\)/);
  assert.match(gateway, /boundedArray\(result\.suspicious_url_artifacts, 25\)/);
  assert.match(form, /authority_review_payload: scanData\.authority_review_payload/);
  assert.doesNotMatch(form, /authoritative_scan: scanData,/);
  assert.match(aiReview, /authoritativeScan\.authority_review_payload/);
  assert.match(aiReview, /standard_scan_review_payload_hmac_v2/);
  assert.match(aiReview, /Math\.min\(45_000/);
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
  assert.match(scanRuns, /PROTECTED_SCAN_STATUSES = new Set\(\["complete", "limited"\]\)/);
  assert.match(scanRuns, /!PROTECTED_SCAN_STATUSES\.has\(String\(run\.status/);
});

test("4b. the terminal write re-reads status instead of trusting the stale snapshot", () => {
  const fn = gateway.match(/async function failOwnedScanRun\([\s\S]*?\n\}/)?.[0] || "";
  assert.ok(fn, "failOwnedScanRun not found");

  // persistScanAuthority sets status "complete" from a separate invocation via
  // asServiceRole, so context.scan.status (read up to ~90s earlier) is a TOCTOU.
  const rereadIndex = fn.indexOf("ScanRun.get(context.scan.id)");
  const guardIndex = fn.search(/PROTECTED_SCAN_STATUSES\.has\(currentStatus\)/);
  const writeIndex = fn.indexOf("ScanRun.update(context.scan.id");
  assert.ok(rereadIndex > -1, "must re-read ScanRun before the terminal write");
  assert.ok(guardIndex > rereadIndex, "protected-status guard must use the re-read value");
  assert.ok(writeIndex > guardIndex, "the write must happen after the guard");

  // The guard must not be decided from the stale snapshot.
  assert.doesNotMatch(fn, /PROTECTED_SCAN_STATUSES\.has\(String\(context\.scan\.status/);
  // A failed re-read must refuse to write rather than clobber.
  assert.match(fn, /skipped: "recheck_failed"/);
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
