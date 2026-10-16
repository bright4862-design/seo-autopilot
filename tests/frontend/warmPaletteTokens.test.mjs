import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const css = readFileSync("src/index.css", "utf8");

// The results page paints with the paper/ink palette in tailwind.config.js.
const PAPER = [60, 9, 98];
const INK = [24, 10, 10];

function tokens(selector) {
  const start = css.indexOf(`${selector} {`);
  assert.ok(start >= 0, `${selector} block must exist`);
  const end = css.indexOf("\n  }", start);
  const found = {};
  for (const match of css.slice(start, end).matchAll(/--([a-z0-9-]+):\s*([\d.]+)\s+([\d.]+)%\s+([\d.]+)%;/g)) {
    found[match[1]] = [Number(match[2]), Number(match[3]), Number(match[4])];
  }
  return found;
}

function rgb([h, s, l]) {
  const sat = s / 100;
  const light = l / 100;
  const k = (n) => (n + h / 30) % 12;
  const a = sat * Math.min(light, 1 - light);
  const f = (n) => light - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
  return [f(0), f(8), f(4)];
}

function luminance(color) {
  const [r, g, b] = rgb(color).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const THEMES = { light: tokens(":root"), dark: tokens(".dark") };

test("no shared token falls back to the cool blue/slate template palette", () => {
  for (const [theme, values] of Object.entries(THEMES)) {
    assert.ok(Object.keys(values).length >= 30, `${theme} theme tokens must parse`);
    for (const [name, [hue, saturation]] of Object.entries(values)) {
      const cool = hue >= 180 && hue <= 300 && saturation >= 8;
      assert.equal(cool, false, `${theme} --${name} is a cool hue (${hue} ${saturation}%)`);
    }
  }
});

test("primary actions are ink with paper text, and focus rings are ink", () => {
  const light = THEMES.light;
  assert.deepEqual(light.background, PAPER);
  assert.deepEqual(light.foreground, INK);
  assert.deepEqual(light.primary, INK);
  assert.deepEqual(light["primary-foreground"], PAPER);
  assert.deepEqual(light.ring, INK);
  // Dark mode inverts the same pair rather than introducing another accent.
  assert.deepEqual(THEMES.dark.primary, PAPER);
  assert.deepEqual(THEMES.dark["primary-foreground"], INK);
});

test("text tokens keep readable contrast and focus rings stay visible in both themes", () => {
  const textPairs = [
    ["foreground", "background"],
    ["card-foreground", "card"],
    ["popover-foreground", "popover"],
    ["primary-foreground", "primary"],
    ["secondary-foreground", "secondary"],
    ["accent-foreground", "accent"],
    ["muted-foreground", "background"],
    ["muted-foreground", "muted"],
    ["muted-foreground", "card"],
    ["destructive", "background"],
    ["destructive", "card"],
    ["destructive-foreground", "destructive"],
  ];
  for (const [theme, values] of Object.entries(THEMES)) {
    for (const [fg, bg] of textPairs) {
      const ratio = contrast(values[fg], values[bg]);
      assert.ok(ratio >= 4.5, `${theme} --${fg} on --${bg} is ${ratio.toFixed(2)}:1`);
    }
    for (const bg of ["background", "card"]) {
      const ratio = contrast(values.ring, values[bg]);
      assert.ok(ratio >= 3, `${theme} --ring on --${bg} is ${ratio.toFixed(2)}:1`);
    }
  }
});

test("shared legacy utilities no longer paint template blue or slate", () => {
  const utilities = css.slice(css.indexOf("@layer utilities"));
  assert.doesNotMatch(utilities, /\b(blue|slate|sky|indigo)-\d/);
});

test("the shared button keeps a visible offset focus ring on an ink fill", () => {
  const button = readFileSync("src/components/ui/button.jsx", "utf8");
  assert.match(button, /focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background/);
});

// Active routed surfaces outside the results page itself, which is owned
// separately. Semantic green/amber/red classes remain allowed.
const ACTIVE_SURFACES = [
  "src/components/AuthLayout.jsx",
  "src/components/ProtectedRoute.jsx",
  "src/components/UserNotRegisteredError.jsx",
  "src/components/layout/DashboardLayout.jsx",
  "src/components/scan/ScanWebsiteForm.jsx",
  "src/components/scan/DurableScanProgressSurface.jsx",
  "src/components/scan/TruthfulScanProgress.jsx",
  "src/components/fixlist/ScanComparisonPanel.jsx",
  "src/components/fixlist/RepairRoleView.jsx",
  "src/components/fixlist/GeoReadinessPanel.jsx",
  "src/components/billing/LeadRequestModal.jsx",
  "src/components/billing/UnlockAccessButton.jsx",
  "src/components/ui/button.jsx",
  "src/components/ui/input.jsx",
  "src/pages/Login.jsx",
  "src/pages/Register.jsx",
  "src/pages/ForgotPassword.jsx",
  "src/pages/ResetPassword.jsx",
  "src/pages/Onboarding.jsx",
  "src/pages/Billing.jsx",
  "src/pages/Account.jsx",
];

test("active product surfaces carry no cool-blue or slate accent classes", () => {
  for (const file of ACTIVE_SURFACES) {
    const source = readFileSync(file, "utf8");
    assert.doesNotMatch(
      source,
      /\b(?:[a-z-]+:)*(?:bg|text|border|ring|outline|from|to|via|fill|stroke|divide|decoration|placeholder)-(?:blue|slate|sky|indigo|cyan|gray|zinc)-\d/,
      `${file} uses a cool palette class`,
    );
    assert.doesNotMatch(source, /gradient-primary|gradient-text/, `${file} uses a template accent utility`);
  }
});

test("auth pages use ink links instead of the template primary accent", () => {
  for (const file of ["src/pages/Login.jsx", "src/pages/ForgotPassword.jsx", "src/pages/ResetPassword.jsx"]) {
    const source = readFileSync(file, "utf8");
    assert.doesNotMatch(source, /text-primary|bg-card|text-muted-foreground/, file);
    assert.match(source, /text-ink underline decoration-hairline/, file);
  }
});
