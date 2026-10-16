import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import loadConfig from "tailwindcss/loadConfig.js";

const css = readFileSync("src/index.css", "utf8");
// Load the config exactly as Tailwind does (it is CommonJS in an ESM package).
const tailwind = loadConfig(fileURLToPath(new URL("../../tailwind.config.js", import.meta.url)));
const colors = tailwind.theme.extend.colors;

// The approved Results redesign canvas. Every surface paints on this cream.
const RESULTS_CANVAS = "#F6F4EF";
const INK = "#1C1917";

const hexToRgb = (hex) => {
  const n = Number.parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
};
const rgbToHex = (rgb) => `#${rgb.map((v) => Math.round(v).toString(16).padStart(2, "0")).join("").toUpperCase()}`;

// An HSL token as the browser paints it: 8-bit sRGB.
function hslToRgb([h, s, l]) {
  const sat = s / 100;
  const light = l / 100;
  const k = (n) => (n + h / 30) % 12;
  const a = sat * Math.min(light, 1 - light);
  const f = (n) => light - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
  return [f(0), f(8), f(4)].map((v) => Math.round(v * 255));
}

// Opaque `color` at `alpha` over `base`, as Tailwind's bg-ink/[0.04] renders.
const over = (color, alpha, base) => color.map((v, i) => v * alpha + base[i] * (1 - alpha));

function luminance(rgb) {
  const [r, g, b] = rgb.map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

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

const THEMES = { light: tokens(":root"), dark: tokens(".dark") };
const tokenRgb = (theme, name) => hslToRgb(THEMES[theme][name]);
const tokenHex = (theme, name) => rgbToHex(tokenRgb(theme, name));

const canvas = hexToRgb(RESULTS_CANVAS);
const ink = hexToRgb(INK);
// Surfaces text actually sits on in the app: the canvas, raised white cards,
// and the quiet ink-over-cream fills used for panels, hover and active rows.
const SURFACES = {
  "Results canvas": canvas,
  "white card": [255, 255, 255],
  "bg-ink/[0.025] on canvas": over(ink, 0.025, canvas),
  "bg-ink/[0.04] on canvas": over(ink, 0.04, canvas),
  "--muted fill": tokenRgb("light", "muted"),
};

test("Tailwind paper is exactly the approved Results canvas, with ink and semantic colours kept", () => {
  assert.equal(colors.paper.toUpperCase(), RESULTS_CANVAS);
  assert.equal(colors.ink.DEFAULT.toUpperCase(), INK);
  assert.equal(colors.good.toUpperCase(), "#15803D");
  assert.equal(colors.warnink.toUpperCase(), "#B45309");
  assert.equal(colors.crit.toUpperCase(), "#B91C1C");
});

test("shared HSL tokens resolve to the same colours as the Tailwind palette", () => {
  const paper = colors.paper.toUpperCase();
  const muted = colors.ink.muted.toUpperCase();
  assert.equal(tokenHex("light", "background"), paper);
  assert.equal(tokenHex("light", "sidebar-background"), paper);
  assert.equal(tokenHex("light", "primary-foreground"), paper);
  assert.equal(tokenHex("light", "foreground"), INK);
  assert.equal(tokenHex("light", "primary"), INK);
  assert.equal(tokenHex("light", "ring"), INK);
  assert.equal(tokenHex("light", "muted-foreground"), muted);
  assert.equal(tokenHex("light", "destructive"), colors.crit.toUpperCase());
  assert.equal(tokenHex("light", "success"), colors.good.toUpperCase());
  assert.equal(tokenHex("light", "warning"), colors.warnink.toUpperCase());
  // Dark mode inverts the same pair rather than introducing another accent.
  assert.equal(tokenHex("dark", "primary"), paper);
  assert.equal(tokenHex("dark", "primary-foreground"), INK);
});

test("ink, muted and faint text keep at least 4.5:1 on the canvas and every quiet fill", () => {
  for (const [name, hex] of [["ink", colors.ink.DEFAULT], ["ink-muted", colors.ink.muted], ["ink-faint", colors.ink.faint]]) {
    for (const [surface, rgb] of Object.entries(SURFACES)) {
      const ratio = contrast(hexToRgb(hex), rgb);
      assert.ok(ratio >= 4.5, `text-${name} ${hex} on ${surface} is ${ratio.toFixed(3)}:1`);
    }
  }
});

test("the neutral text hierarchy stays ordered and the two quiet tones stay distinguishable", () => {
  const [strong, muted, faint] = [colors.ink.DEFAULT, colors.ink.muted, colors.ink.faint]
    .map((hex) => contrast(hexToRgb(hex), canvas));
  assert.ok(strong > muted && muted > faint, `expected ink > muted > faint, got ${strong} ${muted} ${faint}`);
  const step = contrast(hexToRgb(colors.ink.muted), hexToRgb(colors.ink.faint));
  assert.ok(step >= 1.15, `muted and faint must differ visibly (${step.toFixed(2)}:1)`);
});

test("semantic success, warning and failure text stays readable on the canvas and white cards", () => {
  for (const hex of [colors.good, colors.warnink, colors.crit]) {
    for (const surface of ["Results canvas", "white card"]) {
      const ratio = contrast(hexToRgb(hex), SURFACES[surface]);
      assert.ok(ratio >= 4.5, `${hex} on ${surface} is ${ratio.toFixed(3)}:1`);
    }
  }
});

test("no shared token falls back to the cool blue/slate template palette", () => {
  for (const [theme, values] of Object.entries(THEMES)) {
    assert.ok(Object.keys(values).length >= 30, `${theme} theme tokens must parse`);
    for (const [name, [hue, saturation]] of Object.entries(values)) {
      const cool = hue >= 180 && hue <= 300 && saturation >= 8;
      assert.equal(cool, false, `${theme} --${name} is a cool hue (${hue} ${saturation}%)`);
    }
  }
});

test("token text pairs keep readable contrast and focus rings stay visible in both themes", () => {
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
  for (const theme of Object.keys(THEMES)) {
    for (const [fg, bg] of textPairs) {
      const ratio = contrast(tokenRgb(theme, fg), tokenRgb(theme, bg));
      assert.ok(ratio >= 4.5, `${theme} --${fg} on --${bg} is ${ratio.toFixed(2)}:1`);
    }
    for (const bg of ["background", "card", "muted"]) {
      const ratio = contrast(tokenRgb(theme, "ring"), tokenRgb(theme, bg));
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
