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

test("the public landing page states the paid Standard 150 beta contract", () => {
  assert.match(landingSource, /Standard 150 beta/);
  assert.match(landingSource, /\$50/);
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
