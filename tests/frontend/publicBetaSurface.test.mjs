import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const landingSource = readFileSync("src/pages/Landing.jsx", "utf8");
const appSource = readFileSync("src/App.jsx", "utf8");
const dashboardLayoutSource = readFileSync(
  "src/components/layout/DashboardLayout.jsx",
  "utf8",
);
const mobileNavigationSource = readFileSync(
  "src/components/layout/MobileBottomNav.jsx",
  "utf8",
);

test("the public landing page states the paid Standard 150 contract without beta invitation language", () => {
  assert.match(landingSource, /Standard 150/);
  assert.doesNotMatch(landingSource, /Standard 150 beta|Get beta access|invite-only/i);
  // The page renders the shared price constant rather than a literal, so certify
  // what the customer is shown through it. Grepping the source for "$100" went
  // stale the moment the price moved into src/lib/access.js, and this assertion
  // has been failing ever since while the rendered price stayed correct.
  // paidBetaContract.test.mjs pins that constant to $100 across checkout, the
  // webhook and every customer surface.
  assert.match(landingSource, /\{UNLOCK_PRICE_LABEL\}/);
  // And the page must not reintroduce a hard-coded price, which is what let the
  // certification and the rendered value drift apart in the first place.
  assert.doesNotMatch(landingSource, /\$\d/);
  assert.match(landingSource, /one-time/i);
  assert.match(landingSource, /2–4 minutes/);

  assert.doesNotMatch(landingSource, /free scan|no credit card/i);
  assert.doesNotMatch(landingSource, /1–2 minutes|1-2 minutes/i);
  assert.doesNotMatch(landingSource, /Grok|Premium/i);
});

test("the unreleased Assistant route redirects to the customer dashboard", () => {
  assert.doesNotMatch(appSource, /import Assistant from/);
  assert.doesNotMatch(appSource, /element=\{<Assistant \/>\}/);
  assert.match(
    appSource,
    /path="\/assistant"\s+element=\{<Navigate to="\/dashboard" replace \/>\}/,
  );
});

test("customer navigation does not advertise or link to unreleased AI features", () => {
  for (const source of [dashboardLayoutSource, mobileNavigationSource]) {
    assert.doesNotMatch(source, /Grok|Assistant|\/assistant|Coming soon/i);
  }
});
