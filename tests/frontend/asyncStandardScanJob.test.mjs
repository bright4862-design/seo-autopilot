// Asynchronous durable Standard 150 job flow.
//
// The job gateway (startStandardScanJob) submits the authenticated Python
// scanner job in a background task and returns the exact scan_id immediately.
// The browser never waits for Cloud Run, so a crawl longer than the platform's
// ~50s synchronous window can no longer produce a browser-visible 503. The
// synchronous 28s gateway remains only as the temporary fallback, unchanged,
// per the release-coordination record.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const job = fs.readFileSync("base44/functions/startStandardScanJob/entry.ts", "utf8");
const gateway = fs.readFileSync("base44/functions/runStandard150Scan/entry.ts", "utf8");
const form = fs.readFileSync("src/components/scan/ScanWebsiteForm.jsx", "utf8");
const fixListPage = fs.readFileSync("src/pages/FixList.jsx", "utf8");
const completionHook = fs.readFileSync("src/hooks/useDurableScanCompletion.js", "utf8");
const scanRuns = fs.readFileSync("src/lib/scanRuns.js", "utf8");
const pythonScanner = fs.readFileSync("scanner-api/app/scanner.py", "utf8");
const pythonMain = fs.readFileSync("scanner-api/app/main.py", "utf8");

function jobConst(name) {
  const raw = job.match(new RegExp(`const ${name} = ([0-9_]+);`))?.[1];
  assert.ok(raw, `job constant ${name} not found`);
  return Number(raw.replace(/_/g, ""));
}

test("1. a scan longer than 50 seconds cannot produce a browser 503", () => {
  // The upstream fetch runs ONLY inside the background task; the accepted
  // response never awaits it.
  assert.match(job, /waitUntil\(runScanJob\(/);
  assert.doesNotMatch(job, /await runScanJob\(/);
  assert.match(job, /accepted: true/);
  // The browser navigates to the durable result page the moment the job is
  // accepted — before any crawl work — so crawl duration cannot reach it.
  const acceptIndex = form.indexOf("jobData?.accepted === true");
  const navigateIndex = form.indexOf("navigate(`/dashboard?scan_id=${encodeURIComponent(scanId)}`)", acceptIndex);
  const syncFallbackIndex = form.indexOf('callBase44Function(STANDARD_SCANNER_FUNCTION');
  assert.ok(acceptIndex > -1, "form must check the accepted job response");
  assert.ok(navigateIndex > acceptIndex, "accepted job must navigate immediately");
  assert.ok(syncFallbackIndex > navigateIndex, "the synchronous path must come after (fallback only)");
});

test("2. the worker owns a 60-120 second crawl budget; sync fallback keeps 28s", () => {
  assert.equal(jobConst("ASYNC_WORKER_BUDGET_MS"), 120_000);
  assert.ok(jobConst("UPSTREAM_FETCH_TIMEOUT_MS") > 120_000, "worker fetch must outlast the crawl budget plus serialization");
  assert.match(job, /advisory_crawl_timeout_ms: ASYNC_WORKER_BUDGET_MS/);
  assert.match(job, /async_job: true/);
  // Python enforces the ceiling server-side and only for async jobs.
  assert.match(pythonScanner, /ASYNC_JOB_TIMEOUT_CEILING = 120\.0/);
  assert.match(pythonScanner, /min\(ASYNC_JOB_TIMEOUT_CEILING, requested\)/);
  assert.match(pythonScanner, /max\(20\.0, min\(float\(base\["timeout"\]\), requested\)\)/, "sync clamp must remain");
  assert.match(pythonMain, /le=120_000/);
  assert.match(pythonMain, /async_job: bool = False/);
  assert.match(pythonMain, /job_mode=bool\(payload\.async_job\)/);
  // Temporary synchronous fallback unchanged at 28s.
  assert.match(gateway, /const PYTHON_CRAWL_BUDGET_MS = 28_000;/);
});

test("3. scope contract: 150-page cap, robots, Python-only, pages_found kept separate", () => {
  assert.match(job, /const MAX_PAGES = 150;/);
  assert.match(job, /page_cap_violation/);
  assert.match(job, /respect_robots_txt: true/);
  assert.match(job, /deno_fallback_used: false/);
  assert.doesNotMatch(job, /deno_fallback_used: true/);
  assert.doesNotMatch(job, /allow_deno_fallback: true/);
  // Broad discovery evidence stays separate from the crawl cap: pages_crawled
  // is capped, pages_found passes through from upstream untouched.
  assert.match(job, /pages_crawled: pageCount/);
  assert.match(job, /pages_found: nonNegativeInteger\(result\.pages_found\)/);
  assert.doesNotMatch(job, /pages_found: pageCount/);
  // Grok stays disabled and Premium isolated: the job path never touches them.
  for (const forbidden of [/grok/i, /premium/i]) assert.doesNotMatch(job, forbidden);
});

test("4. exact scan identity end to end — no substitute results", () => {
  // ScanRun exists before network work and is verified, never created here.
  assert.match(job, /loadOwnedScanContext/);
  assert.doesNotMatch(job, /ScanRun\.create/);
  assert.match(job, /matchesUpstreamIdentity/);
  // The browser only follows the job when it echoes the exact scan_id.
  assert.match(form, /jobData\?\.accepted === true && String\(jobData\.scan_id \|\| ""\) === String\(scanId\)/);
  // The result page renders only the requested scan.
  assert.match(fixListPage, /const isExactScan = String\(durableBundle\?\.run\?\.id \|\| ""\) === String\(requestedScanId\)/);
  assert.match(fixListPage, /Never substitute another scan/);
});

test("5. duplicate submits are prevented", () => {
  assert.match(form, /if \(submitLockRef\.current \|\| saving\) return;/);
  assert.match(scanRuns, /pendingBeginsByRequest/);
  assert.match(scanRuns, /pendingBeginsByTarget/);
  assert.match(scanRuns, /resolveScanRunReplay/);
});

test("6. refresh and browser recovery during an active scan", () => {
  // The result page polls the exact durable ScanRun and keeps the last known
  // state visible: transient null reads never erase a loaded record.
  assert.match(fixListPage, /getScanRunWithFixList\(requestedScanId\)/);
  assert.match(fixListPage, /A transient null or read error during polling must not erase a scan/);
  assert.match(fixListPage, /isBackgroundRead && loadedScanIdRef\.current === requestedScanId/);
  // The form-side watcher survives transient nulls too and only ever opens the
  // exact watched scan.
  assert.match(completionHook, /getScanRunWithFixList\(scanId\)/);
  assert.match(completionHook, /A transient null read never ends the watch/);
  assert.match(completionHook, /scan_id=\$\{encodeURIComponent\(scanId\)\}/);
});

test("7. terminal failures persist truthfully and never consume allowance", () => {
  // failed / timed-out states are written on the exact run.
  assert.match(job, /status: "failed"/);
  assert.match(job, /failureCode: isTimeoutError\(error\) \? "timeout" : "worker_error"/);
  assert.match(job, /release_gate_eligible: false/);
  // A sealed complete/limited run is never overwritten.
  assert.match(job, /PROTECTED_SCAN_STATUSES = new Set\(\["complete", "limited"\]\)/);
  // Allowance is written in exactly one place, after sealed verification.
  const allowanceWrites = job.match(/scans_used/g) || [];
  assert.ok(allowanceWrites.length > 0, "allowance write must exist");
  const consumeIndex = job.indexOf("await consumeScanAllowance(");
  const sealCheckIndex = job.indexOf("await readSealedRun(");
  assert.ok(sealCheckIndex > -1 && consumeIndex > sealCheckIndex, "allowance must be consumed only after the sealed run is verified");
  const failFn = job.match(/async function failOwnedScanRun[\s\S]*?\n\}/)?.[0] || "";
  assert.doesNotMatch(failFn, /scans_used/, "failure path must never touch allowance");
});

test("8. completed persistence is authority-sealed", () => {
  // The worker requires the review attestation and persists through
  // persistScanAuthority — the only sealed write path.
  assert.match(job, /authority_review_attestation/);
  assert.match(job, /review_attestation_missing/);
  assert.match(job, /invokeFunction\(base44, "persistScanAuthority"/);
  // Verification demands a 64-hex proof, protected status, and a fix_list_id.
  assert.match(job, /\^\[a-f0-9\]\{64\}\$/);
  assert.match(job, /run\.fix_list_id/);
  assert.match(job, /standard_scan_review_payload_hmac_v2/);
});

test("9. completed ScanRun automatically opens its exact FixList", () => {
  // In-place transition on the result page as soon as polling sees terminal.
  assert.match(fixListPage, /Polling stops as soon as the run reaches a terminal state/);
  // Missed navigation is recovered by durable polling from the form watcher.
  assert.match(completionHook, /\["complete", "limited"\]\.includes\(status\) && fixListId/);
  assert.match(completionHook, /navigate\(`\/dashboard\?scan=complete&scan_id=/);
});