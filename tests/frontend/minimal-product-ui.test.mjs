import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const app = readFileSync("src/App.jsx", "utf8");
const onboarding = readFileSync("src/pages/Onboarding.jsx", "utf8");
const scannerCss = readFileSync("src/styles/scanner-minimal.css", "utf8");
const layout = readFileSync("src/components/layout/DashboardLayout.jsx", "utf8");
const billing = readFileSync("src/pages/Billing.jsx", "utf8");

test("scanner uses the shared narrow paper-and-ink surface", () => {
  assert.match(onboarding, /scanner-minimal\.css/);
  assert.match(onboarding, /className="scanner-minimal"/);
  assert.match(scannerCss, /max-width:\s*680px/);
  assert.match(scannerCss, /background:\s*transparent\s*!important/);
  assert.match(scannerCss, /button\[type="submit"\]/);
  assert.match(scannerCss, /border-bottom:\s*1px solid rgba\(28, 25, 23/);
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
  assert.match(billing, /Payments are not connected yet/);
});

test("legacy scanner URL redirects to the Standard 150 onboarding route", () => {
  assert.match(app, /path="\/ScanWebsite" element=\{<Navigate to="\/onboarding" replace \/>\}/);
  assert.match(app, /path="\/onboarding" element=\{<Onboarding \/>\}/);
});
