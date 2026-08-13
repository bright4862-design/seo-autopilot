import fs from "node:fs";
// Contract for the New Scan page after the UI/UX rebuild. The page presents one
// scanner, states its scope as plain text, and never offers a scan-size choice.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const scanForm = readFileSync("src/components/scan/ScanWebsiteForm.jsx", "utf8");
const onboarding = readFileSync("src/pages/Onboarding.jsx", "utf8");
const layout = readFileSync("src/components/layout/DashboardLayout.jsx", "utf8");

test("required copy is present verbatim", () => {
  assert.match(scanForm, /Scan depth: up to 150 pages · respects robots\.txt · read-only/);
  assert.match(scanForm, /Business or website name \(optional\)/);
  assert.match(scanForm, /Scans up to 150 pages\. Larger sites coming soon\./);
  assert.match(scanForm, /Takes about 2–4 minutes\. You can leave this page — we’ll save your list\./);
});

test("retired copy is gone", () => {
  assert.doesNotMatch(scanForm, /Premium large-site scans will be enabled after production benchmarking/);
  assert.doesNotMatch(scanForm, /A complete, prioritized scan of up to 150 pages/);
  assert.doesNotMatch(scanForm, /Standard · 150/);
});

test("field order is trust note, heading, subhead, URL, name, spec line, CTA", () => {
  const order = [
    /Read-only scan · no site changes/,
    /<h1[^>]*>Create your FixList<\/h1>/,
    /Enter a website URL and we’ll turn the scan/,
    /id="fixlist-website-url"/,
    /id="fixlist-business-name"/,
    /\{SCAN_SPEC_LINE\}/,
    /type="submit"/,
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
    scanForm.indexOf('type="submit"') < scanForm.indexOf("Optional: personalize your FixList"),
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
  assert.match(layout, /Ask Grok · Coming soon/);
  assert.doesNotMatch(layout, /name: "Ask Grok", href: "\/assistant"/);
  assert.match(layout, /aria-disabled="true"/);
});

test("the page is a centred 680px column owned by the form", () => {
  assert.match(onboarding, /return <ScanWebsiteForm \/>/);
  assert.match(scanForm, /mx-auto w-full max-w-\[680px\]/);
});


test("the loading state shows visible progress and reassures the customer", () => {
  assert.match(scanForm, /SCAN_PROGRESS_STEPS/);
  assert.match(scanForm, /aria-label="Scan progress"/);
  assert.match(scanForm, /role="status"/);
  assert.match(scanForm, /aria-live="assertive"/);
  assert.match(scanForm, /aria-busy=\{isLoading\}/);
  assert.match(scanForm, /fixed left-1\/2 top-4 z-\[100\]/);
  assert.match(scanForm, />Scan running<\/p>/);
  assert.match(scanForm, /formatElapsed\(elapsedSeconds\)/);
  assert.match(scanForm, /Your result will open automatically when it is saved/);
  assert.match(scanForm, /Still working — larger or slower sites can take a little longer/);
});

test("the running scan shows the customer's own domain, not just a spinner", () => {
  // Momentum comes from something real and personal appearing immediately.
  // Falling back to the typed URL means the label is present on the first
  // frame, before the durable run has been read even once.
  assert.match(scanForm, /const scanTargetLabel = durableScan\.domain \|\| safeHostname\(websiteUrl\) \|\| ""/);
  assert.match(scanForm, /\{scanTargetLabel \? \(/, "the progress surface must render the scan target");
});

test("live discovery counts render only once there is something to report", () => {
  // A counter reading "0 pages discovered" is worse than no counter: it reads
  // as a stalled scan. The count appears only when it is non-zero, and the
  // crawled figure only once crawling has actually started.
  assert.match(scanForm, /durableScan\.pagesFound > 0 \? \(/);
  assert.match(scanForm, /pages discovered/);
  assert.match(scanForm, /durableScan\.pagesCrawled > 0 \?/);
  assert.match(scanForm, /STANDARD_SCAN_BUDGET\.max_pages\} checked/,
    "the cap shown must come from the scan budget, not a hardcoded number");
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
