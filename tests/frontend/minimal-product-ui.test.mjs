import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const app = readFileSync("src/App.jsx", "utf8");
const onboarding = readFileSync("src/pages/Onboarding.jsx", "utf8");
const layout = readFileSync("src/components/layout/DashboardLayout.jsx", "utf8");
const billing = readFileSync("src/pages/Billing.jsx", "utf8");
const scanForm = readFileSync("src/components/scan/ScanWebsiteForm.jsx", "utf8");

// scanner-minimal.css was deleted. It restyled the form through positional
// selectors (`form > div:first-child > div:first-child > div:first-child`),
// which stripped the input borders and left the selection-card thumb behind
// once the card itself was removed. Layout now lives with the form markup.
test("the New Scan form owns its centred layout, with no override stylesheet", () => {
  // Comments may explain why the stylesheet is gone; code may not import it.
  const onboardingCode = onboarding
    .split("\n")
    .filter((line) => !/^\s*(\/\/|\*|\/\*)/.test(line))
    .join("\n");
  assert.doesNotMatch(onboardingCode, /scanner-minimal/);
  assert.match(onboarding, /return <ScanWebsiteForm \/>/);
  assert.match(scanForm, /mx-auto w-full max-w-\[680px\]/);
});

test("inputs are bordered and expose a visible focus ring", () => {
  assert.match(scanForm, /border-hairline/);
  assert.match(scanForm, /focus-visible:ring-2/);
  assert.match(scanForm, /focus-visible:ring-ink\/10/);
});

test("dashboard shell stays lightweight, sticky, and keyboard-aware", () => {
  assert.match(layout, /sticky top-0/);
  assert.match(layout, /backdrop-blur-xl/);
  assert.match(layout, /max-w-\[680px\]/);
  assert.match(layout, /aria-current=/);
  assert.match(layout, /Dashboard/);
  assert.match(layout, /New scan/);
  assert.match(layout, /Billing/);
});

test("billing uses responsive rows and a visible current-plan summary", () => {
  assert.match(billing, /Current plan/);
  assert.match(billing, /Run a new scan/);
  assert.match(billing, /flex-col gap-5 sm:flex-row/);
  assert.match(billing, /border-hairline-soft/);
  assert.doesNotMatch(billing, /Payments are not connected yet|free test scan|Run free scan/i);
  assert.match(billing, /Standard 150 beta/);
  assert.match(billing, /securely handled by Stripe/);
});

test("legacy scanner URL redirects to the Standard 150 onboarding route", () => {
  assert.match(app, /path="\/ScanWebsite" element=\{<Navigate to="\/onboarding" replace \/>\}/);
  assert.match(app, /path="\/onboarding" element=\{<Onboarding \/>\}/);
});
