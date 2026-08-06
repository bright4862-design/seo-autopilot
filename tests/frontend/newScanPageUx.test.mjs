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

test("field order is heading, subhead, trust badge, URL, name, spec line, CTA", () => {
  const order = [
    /<h1[^>]*>Create your FixList<\/h1>/,
    /Enter a website URL and we’ll turn the scan/,
    /Read-only scan — FixList never logs in or changes your website\./,
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

test("debug tooling is hidden unless explicitly requested", () => {
  assert.match(scanForm, /const debugVisible = useMemo\(\(\) => isDebugRequested\(\), \[\]\)/);
  assert.match(scanForm, /\{debugVisible \? \(/);
  assert.match(scanForm, /\{debugVisible && debugOpen \? \(/);
  const gate = scanForm.match(/function isDebugRequested\(\)[\s\S]*?\n\}/);
  assert.ok(gate, "isDebugRequested is missing");
  assert.match(gate[0], /get\("debug"\) === "1"/);
  assert.match(gate[0], /VITE_INTERNAL_DEBUG/);
});

test("customer navigation cannot reach Grok", () => {
  assert.match(layout, /Ask Grok · Coming soon/);
  assert.doesNotMatch(layout, /name: "Ask Grok", href: "\/assistant"/);
  assert.match(layout, /aria-disabled="true"/);
});

test("the page is a centred column of about 640px", () => {
  assert.match(onboarding, /max-w-\[640px\]/);
  assert.match(onboarding, /mx-auto/);
  assert.match(scanForm, /mx-auto w-full max-w-\[640px\]/);
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
