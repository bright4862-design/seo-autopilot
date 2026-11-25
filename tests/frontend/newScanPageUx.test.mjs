import fs from "node:fs";
// Contract for the New Scan page after the UI/UX rebuild. The page presents one
// scanner, states its scope as plain text, and never offers a scan-size choice.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const scanForm = readFileSync("src/components/scan/ScanWebsiteForm.jsx", "utf8");
const onboarding = readFileSync("src/pages/Onboarding.jsx", "utf8");
const layout = readFileSync("src/components/layout/DashboardLayout.jsx", "utf8");
const app = readFileSync("src/App.jsx", "utf8");

test("required copy is present verbatim", () => {
  // The scope line is derived from the attested policy now, because an
  // owner-managed scan must not be shown a robots.txt promise it will not keep.
  // Both spec strings are pinned in siteOwnershipRobotsPolicy.test.mjs.
  assert.match(scanForm, /const scanSpecLine = scanSpecForOwnership\(siteOwnership\);/);
  assert.match(scanForm, /Business or website name \(optional\)/);
  assert.match(scanForm, /FixList confirms your account’s page limit when the scan starts\./);
  assert.match(scanForm, /New accounts can preview one free scan of up to 150 pages\./);
});

test("retired copy is gone", () => {
  assert.doesNotMatch(scanForm, /Premium large-site scans will be enabled after production benchmarking/);
  assert.doesNotMatch(scanForm, /A complete, prioritized scan of up to 150 pages/);
  assert.doesNotMatch(scanForm, /Standard · 150/);
  assert.doesNotMatch(scanForm, /Takes about 2–4 minutes\. You can leave this page — we’ll save your list\./);
});

test("the new scan form leads with the site and puts optional inputs after the start action", () => {
  const order = [
    /"Scan a section" : "Scan a website"/,
    /id="fixlist-website-url"/,
    /id=\{`fixlist-site-ownership-\$\{answer\}`\}/,
    /\{scanSpecLine\}/,
    /type="submit"/,
    /id="fixlist-business-name"/,
  ];
  let cursor = -1;
  for (const pattern of order) {
    const index = scanForm.search(pattern);
    assert.ok(index > cursor, `out of order: ${pattern}`);
    cursor = index;
  }
});

test("the CTA is not pushed below the fold by optional settings", () => {
  // The personalization section renders after the CTA, so the submit button
  // stays within one iPad-landscape viewport of the URL field.
  assert.ok(
    scanForm.indexOf('type="submit"') < scanForm.indexOf("Optional scan settings"),
    "the optional accordion must render after the CTA",
  );
});

test("a bare domain is accepted and normalised to https on blur", () => {
  const blur = scanForm.match(/function handleWebsiteUrlBlur\(\)[\s\S]*?\n {2}\}/);
  assert.ok(blur, "handleWebsiteUrlBlur is missing");
  assert.match(blur[0], /normalizeWebsiteUrl\(raw\)/);
  assert.match(blur[0], /setWebsiteUrl\(normalized\)/);
  assert.match(scanForm, /onBlur=\{handleWebsiteUrlBlur\}/);
  assert.match(scanForm, /placeholder="example\.com"/);

  // Executed, not just asserted: the normaliser must accept a bare domain.
  const normalize = scanForm.match(/function normalizeWebsiteUrl\(value\) \{.*?\n/);
  assert.ok(normalize, "normalizeWebsiteUrl is missing");
  const run = new Function(`${normalize[0]}\nreturn normalizeWebsiteUrl;`)();
  assert.equal(run("example.com"), "https://example.com/");
  assert.equal(run("  example.com  "), "https://example.com/");
  assert.equal(run("http://example.com"), "http://example.com/");
  assert.equal(run("not a url"), "");
});

test("validation is inline and fires before any network work", () => {
  const submit = scanForm.match(/async function handleSubmit[\s\S]*?access = await loadAccess\(\);/);
  assert.ok(submit, "could not read the pre-flight section of handleSubmit");
  assert.match(submit[0], /if \(!normalizedUrl\) \{ setUrlError\(INVALID_URL_MESSAGE\); return; \}/);
  // The access gate and every request must sit after the URL check.
  assert.ok(
    submit[0].indexOf("setUrlError(INVALID_URL_MESSAGE)") < submit[0].indexOf("loadAccess"),
    "URL validation must run before the access check",
  );
  assert.ok(
    submit[0].indexOf('setSubmitting(true)') < submit[0].indexOf("loadAccess"),
    "the visible loader must start before the access check",
  );
  assert.match(scanForm, /aria-invalid=\{Boolean\(urlError\)\}/);
  assert.match(scanForm, /id="fixlist-website-url-error"/);
});

test("the business name is genuinely optional", () => {
  assert.doesNotMatch(scanForm, /Enter the business or website name/);
  assert.match(scanForm, /businessName\.trim\(\) \|\| safeHostname\(normalizedUrl\)/);
});

test("customer-visible debug controls are absent", () => {
  assert.doesNotMatch(scanForm, /Show debug|Hide debug|Scan debug|debugVisible|isDebugRequested/);
  assert.doesNotMatch(scanForm, /VITE_INTERNAL_DEBUG|get\("debug"\) === "1"/);
});

test("customer navigation cannot reach Grok", () => {
  assert.doesNotMatch(layout, /Ask Grok|\/assistant/);
  assert.match(app, /path="\/assistant"[\s\S]*<Navigate to="\/dashboard" replace \/>/);
  assert.doesNotMatch(app, /import Assistant|<Assistant \/>/);
});

test("the page is a centred 680px column owned by the form", () => {
  assert.match(onboarding, /return <ScanWebsiteForm \/>/);
  assert.match(scanForm, /mx-auto w-full max-w-\[680px\]/);
});


test("the loading state delegates to the truthful durable progress surface", () => {
  assert.match(scanForm, /import DurableScanProgressSurface from "@\/components\/scan\/DurableScanProgressSurface"/);
  assert.match(scanForm, /aria-busy=\{isLoading\}/);
  assert.doesNotMatch(scanForm, /fixed left-1\/2 top-4 z-\[100\]/);
  assert.match(scanForm, /<DurableScanProgressSurface/);
  assert.match(scanForm, /durableScan=\{durableScan\}/);
  assert.match(scanForm, /targetLabel=\{scanTargetLabel\}/);
  assert.match(scanForm, /elapsedLabel=\{formatElapsed\(elapsedSeconds\)\}/);
  assert.match(scanForm, /backgroundExecutionProven=\{Boolean\(watchedScanId\)\}/);
  assert.match(scanForm, /onOpenSavedScan=\{watchedScanId/);
  assert.doesNotMatch(scanForm, /SCAN_PROGRESS_STEPS|scanProgressIndex\(/);
});

test("the running scan passes the customer's own domain to truthful progress", () => {
  // Momentum comes from something real and personal appearing immediately.
  // Falling back to the typed URL means the label exists on the first frame,
  // before the durable run has been read even once.
  assert.match(scanForm, /const scanTargetLabel = durableScan\.domain \|\| safeHostname\(websiteUrl\) \|\| ""/);
  assert.match(scanForm, /targetLabel=\{scanTargetLabel\}/,
    "the progress surface must receive the customer's scan target");
});

test("discovery inventory and the 150-page cap are never presented as progress", () => {
  assert.doesNotMatch(scanForm, /pages discovered/);
  assert.doesNotMatch(scanForm, /of \$\{STANDARD_SCAN_BUDGET\.max_pages\} checked/);
  assert.doesNotMatch(scanForm, /durableScan\.pagesFound > 0 \? \(/);
});

test("scan refusal messaging preserves curated copy and safe server detail", () => {
  assert.match(scanForm, /const MAX_SERVER_DETAIL = 240/);
  assert.match(scanForm, /function serverProvidedDetail\(value\)/);
  assert.match(scanForm, /function customerScanAdmissionMessage\(code, serverDetail = "", retryAfterSeconds = null\)/);
  assert.match(scanForm, /const curated = messages\[String\(code \|\| ""\)\]/);
  assert.match(scanForm, /if \(curated\) return curated/);
  assert.match(scanForm, /const detail = serverProvidedDetail\(serverDetail\)/);
  assert.match(scanForm, /if \(detail\) return detail/);
  assert.match(scanForm, /The scan job could not be accepted\. No fallback scan was started\./);
  assert.match(scanForm, /customerScanAdmissionMessage\(failureCode, jobData\?\.error, jobData\?\.retry_after_seconds\)/);
  assert.match(scanForm, /boundary: "async_job_refused"|logScanBoundary\("async_job_refused"/);
  assert.match(scanForm, /failure_code: failureCode/);
  assert.match(scanForm, /dispatcher_version: String\(jobData\?\.version \|\| ""\)/);
  assert.match(scanForm, /error\?\.backend_error/,
    "wrapped Base44 refusals must preserve the parsed server payload");
  assert.match(scanForm, /typeof error\?\.message === "string"/,
    "a safe wrapper message must survive when no structured carrier is present");
});

test("a site cooldown stops the launch retry loop and shows only the bounded wait", async () => {
  const actual = [
    /^function normalizeFunctionResponse\([\s\S]*?^\}/m,
    /^async function submitStandardScanJob\([\s\S]*?^\}/m,
    /^function serverProvidedDetail\([\s\S]*?^\}/m,
    /^function customerScanAdmissionMessage\([\s\S]*?^\}/m,
  ].map((pattern) => {
    const code = scanForm.match(pattern)?.[0];
    assert.ok(code, `missing scan form function for ${pattern}`);
    return code;
  }).join("\n");
  const buildHarness = new Function("callBase44Function", "clearCustomerAuthBoundary", "window", `
    const ASYNC_SCAN_JOB_FUNCTION = "startStandardScanJobV8";
    const UNLOCK_PRICE_LABEL = "$49";
    const MAX_SERVER_DETAIL = 240;
    ${actual}
    return { submitStandardScanJob, customerScanAdmissionMessage };
  `);
  const refusal = {
    accepted: false,
    retryable: true,
    failure_code: "target_cooldown_active",
    retry_after: 3600,
    retry_after_seconds: 3600,
    error: "Private backend detail",
  };

  for (const throwsTransportError of [false, true]) {
    let launches = 0;
    const { submitStandardScanJob, customerScanAdmissionMessage } = buildHarness(
      async () => {
        launches += 1;
        if (throwsTransportError) throw Object.assign(new Error("HTTP 429"), { response: { data: refusal } });
        return { data: refusal };
      },
      () => false,
      { setTimeout: () => assert.fail("a site cooldown must not retry automatically") },
    );
    const result = await submitStandardScanJob({});
    assert.equal(launches, 1);
    assert.equal(result.failure_code, "target_cooldown_active");
    const message = (seconds) => customerScanAdmissionMessage(result.failure_code, result.error, seconds);
    assert.equal(message(result.retry_after_seconds), "This site has asked automated scanners to wait. Try again in about 1 hour.");
    assert.equal(message(60), "This site has asked automated scanners to wait. Try again in about 1 minute.");
    assert.equal(message(47), "This site has asked automated scanners to wait. Try again in about 47 seconds.");
    assert.equal(message(3661), "This site has asked automated scanners to wait. Try again in about 1 hour and 2 minutes.");
    assert.equal(message(86_401), "This site has asked automated scanners to wait. Try again in about 24 hours and 1 minute.");
    for (const unverified of [undefined, 0, "5", -1, 1.5, Infinity]) {
      assert.equal(message(unverified), "This site has asked automated scanners to wait. Try again later.");
    }
  }
});

test("unsafe server refusal detail is rejected before rendering", () => {
  assert.match(scanForm, /typeof value !== "string"/);
  assert.match(scanForm, /text\.length > MAX_SERVER_DETAIL/);
  assert.match(scanForm, /\[\{\}\\\[\\\]<>\]\|\\n/);
});

test("progress counters never move backwards during one scan", () => {
  const hook = fs.readFileSync("src/hooks/useDurableScanCompletion.js", "utf8");
  // A transient null read (RLS hiccup, backgrounded tab) must not blank a
  // counter the customer has already seen.
  assert.match(hook, /Math\.max\(previous\.pagesFound, next\.pagesFound\)/);
  assert.match(hook, /Math\.max\(previous\.pagesCrawled, next\.pagesCrawled\)/);
  assert.match(hook, /next\.domain \|\| previous\.domain/);
  // Derived from the run already fetched for completion — no extra polling.
  assert.equal((hook.match(/getScanRunWithFixList\(/g) || []).length, 1,
    "live progress must reuse the existing read, not add a second request");
});
