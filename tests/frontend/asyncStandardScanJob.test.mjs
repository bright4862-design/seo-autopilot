import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const job = fs.readFileSync("base44/functions/startStandardScanJob/entry.ts", "utf8");
const form = fs.readFileSync("src/components/scan/ScanWebsiteForm.jsx", "utf8");
const fixListPage = fs.readFileSync("src/pages/FixList.jsx", "utf8");
const completionHook = fs.readFileSync("src/hooks/useDurableScanCompletion.js", "utf8");
const workerMain = fs.readFileSync("scanner-api/app/main.py", "utf8");
const workerJob = fs.readFileSync("scanner-api/app/scan_job.py", "utf8");
const persist = fs.readFileSync("base44/functions/persistDurableScanAuthority/index.ts", "utf8");

test("the browser cannot be held open by a crawl", () => {
  assert.doesNotMatch(job, /waitUntil|runScanJob|fetchScannerResult/);
  assert.match(job, /enqueueScanJob\(\{/);
  assert.match(job, /accepted: true/);
  const acceptIndex = form.indexOf("jobData?.accepted === true");
  const navigateIndex = form.indexOf("navigate(`/dashboard?scan_id=${encodeURIComponent(scanId)}`)", acceptIndex);
  assert.ok(acceptIndex > -1);
  assert.ok(navigateIndex > acceptIndex);
  assert.doesNotMatch(form, /SYNC_FALLBACK_ENABLED/);
  const submitStart = form.indexOf("async function handleSubmit");
  const submitEnd = form.indexOf("\n  return (", submitStart);
  const submitSource = form.slice(submitStart, submitEnd);
  assert.doesNotMatch(submitSource, /runStandard150Scan|aiReviewScan|completeScanRun|failScanRun|cancelScanRun|markScanRunReviewing/);
});

test("the durable route owns the longer Python-only scan", () => {
  assert.match(job, /const ASYNC_WORKER_BUDGET_MS = 210_000;/);
  assert.match(workerMain, /timeout_seconds=CRAWL_BUDGET_SECONDS/);
  assert.match(workerMain, /job_mode=True/);
  assert.match(workerMain, /scan_mode="advanced"/);
  assert.match(workerMain, /enforce_scan_response_page_budget\(result, "advanced"\)/);
  assert.match(workerJob, /CRAWL_BUDGET_SECONDS = 210\.0/);
  assert.doesNotMatch(job, /SCANNER_API_URL|SCANNER_API_KEY/);
});

test("scope is Standard 150, robots-respecting and Python-only", () => {
  assert.match(job, /const MAX_PAGES = 150;/);
  assert.match(job, /respect_robots_txt: true/);
  assert.match(job, /deno_fallback_used: false/);
  assert.match(workerMain, /pages_found/);
  assert.match(workerMain, /pages_crawled/);
  assert.doesNotMatch(job, /allow_deno_fallback: true/);
});

test("the exact owner-bound scan identity travels end to end", () => {
  assert.match(job, /loadOwnedScanContext/);
  assert.doesNotMatch(job, /ScanRun\.create/);
  assert.match(job, /owner_user_id: String\(user\.id\)/);
  assert.match(workerMain, /identity_matches\(scan, job\)/);
  assert.match(workerJob, /"attempt_count": str\(current_attempt\(scan\)\)/);
  assert.match(form, /assertServerAdmissionIdentity\(jobData, \{ request_id: requestId, idempotency_key: idempotencyKey \}\)/);
  assert.match(form, /scanId = String\(jobData\.scan_id \|\| ""\)/);
  assert.match(form, /scanId !== String\(response\?\.scan_run_id \|\| ""\)/);
  assert.match(fixListPage, /const isExactScan = String\(durableBundle\?\.run\?\.id \|\| ""\) === String\(requestedScanId\)/);
});

test("refresh restores only the exact durable result", () => {
  assert.match(fixListPage, /getScanRunWithFixList\(requestedScanId\)/);
  assert.match(completionHook, /getScanRunWithFixList\(scanId\)/);
  assert.match(completionHook, /scan_id=\$\{encodeURIComponent\(scanId\)\}/);
});

test("the delayed watchdog is the final terminal owner", () => {
  assert.match(job, /enqueueScanDrain\(\{/);
  assert.ok(job.indexOf("enqueueScanDrain({") < job.indexOf("enqueueScanJob({"));
  assert.match(workerMain, /@app\.post\("\/scan-job-drain"\)/);
  assert.match(workerMain, /worker_terminal_drain_timeout/);
  assert.match(workerMain, /is_superseded_attempt\(scan, job_attempt\)/);
  assert.match(workerMain, /already_terminal\(scan\)/);
});

test("paid admission is the sole entitlement gate", () => {
  assert.match(job, /loadPaidEntitlement\(base44, user\)/);
  assert.match(job, /paid_access_required/);
  assert.doesNotMatch(job, /scans_used|consumeScanAllowance|FREE_SCAN/);
  assert.doesNotMatch(persist, /entities\.Access|scans_used|ensureAllowanceConsumed/);
  assert.match(persist, /allowanceConsumed: false/);
});

test("completed authority is immutable and attempt-bound", () => {
  assert.match(persist, /terminal_authority_rejected/);
  assert.match(persist, /claimedAttempt !== rowAttempt/);
  assert.ok((persist.match(/await assertAttemptStillActive\(/g) || []).length >= 2);
  assert.match(persist, /persistedScan\?\.status === "complete"/);
  assert.match(persist, /fixListVerified: true/);
});

test("the accepted response is CORS-safe and executable", async () => {
  const corsBlock = job.match(/^const CORS_HEADERS = Object\.freeze\(\{[\s\S]*?\}\);/m)[0];
  const headersFn = job.match(/^function corsHeaders\(\) \{[\s\S]*?\n\}/m)[0];
  const jsonBlock = job.match(/^function jsonResponse\(payload, status = 200\) \{[\s\S]*?\n\}/m)[0];
  const { jsonResponse, CORS_HEADERS } = new Function(
    `${corsBlock}\n${headersFn}\n${jsonBlock}\nreturn { jsonResponse, CORS_HEADERS };`,
  )();
  assert.equal(CORS_HEADERS["Access-Control-Allow-Origin"], "*");
  const response = jsonResponse({ success: true, accepted: true, scan_id: "scan-1" });
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { success: true, accepted: true, scan_id: "scan-1" });
});
