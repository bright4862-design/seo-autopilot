import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { build } from "esbuild";

import { buildGeoReadinessPresentation } from "../../src/lib/geoReadinessPresentation.js";

const ASSESSED = {
  geo_readiness_version: "geo_readiness_v1_experimental",
  evidence_adapter_version: "geo_evidence_v1",
  assessment_status: "assessed",
  score: 71,
  coverage: 0.875,
  sample_pages: 8,
  score_bounds: { lower: 62.5, upper: 75 },
  bounds_kind: "unknown_outcome_range_not_statistical_confidence",
};
// Shape produced by scanner-api/app/geo_readiness.py when a dimension is short
// of verified evidence: no score, raw six-decimal bounds.
const INCOMPLETE = {
  ...ASSESSED,
  assessment_status: "insufficient_evidence",
  score: null,
  coverage: 0.512821,
  score_bounds: { lower: 43.589744, upper: 92.307692 },
};
const METHODOLOGY = "Experimental v1 assessment of accepted raw HTML evidence.";
const NON_CITATION = "This readiness assessment does not measure AI citations, inclusion, visibility, or traffic.";

test("insufficient evidence reads as an incomplete assessment, not a failed one", () => {
  const result = buildGeoReadinessPresentation({ geoReadiness: INCOMPLETE, customerAccess: "preview" });
  assert.equal(result.statusLabel, "GEO assessment incomplete");
  assert.equal(result.score, null);
  assert.equal(result.scoreAvailable, false);
  const explanation = result.incompleteExplanation.join(" ");
  assert.match(explanation, /Missing evidence is unknown, not a failed readiness check\./);
  assert.match(explanation, /at least 80% of checks overall/);
  assert.match(explanation, /at least 50% in every assessment area/);
  // No invented score and no promise that another scan will supply the evidence.
  assert.doesNotMatch(explanation, /\d+ out of 100|rescan|scan again|another scan|will (?:fix|resolve|improve)/i);
});

test("score bounds show at most one decimal and always contain the computed range", () => {
  const result = buildGeoReadinessPresentation({ geoReadiness: INCOMPLETE, customerAccess: "preview" });
  assert.equal(result.boundsLabel, "43.5–92.4 possible as unresolved checks are completed");
  assert.doesNotMatch(result.boundsLabel, /43\.589744|92\.307692/);

  for (const [lower, upper, expected] of [
    [80, 100, "80–100"],
    [0, 12.5, "0–12.5"],
    [43.6, 43.6, "43.6–43.6"],
    [12.000001, 87.999999, "12–88"],
    [99.95, 100, "99.9–100"],
  ]) {
    const label = buildGeoReadinessPresentation({
      geoReadiness: { ...INCOMPLETE, score_bounds: { lower, upper } },
      customerAccess: "preview",
    }).boundsLabel;
    assert.equal(label, `${expected} possible as unresolved checks are completed`);
    const [shownLower, shownUpper] = expected.split("–").map(Number);
    assert.ok(shownLower <= lower && shownUpper >= upper, `${expected} must contain ${lower}–${upper}`);
    assert.doesNotMatch(expected, /\.\d{2,}/);
  }
});

test("coverage just below the 80% threshold is never displayed as meeting it", () => {
  const label = (coverage) => buildGeoReadinessPresentation({
    geoReadiness: { ...INCOMPLETE, coverage },
    customerAccess: "preview",
  }).coverageLabel;
  assert.equal(label(0.795), "79% evidence coverage");
  assert.equal(label(0.799999), "79% evidence coverage");
  assert.equal(label(0.57), "57% evidence coverage");
  assert.equal(label(0.512821), "51% evidence coverage");
  assert.equal(buildGeoReadinessPresentation({ geoReadiness: { ...ASSESSED, coverage: 0.8 } }).coverageLabel, "80% evidence coverage");
});

test("other states carry no incomplete-evidence explanation and keep their labels", () => {
  const assessed = buildGeoReadinessPresentation({ geoReadiness: ASSESSED, customerAccess: "preview" });
  assert.equal(assessed.statusLabel, "Experimental readiness score");
  assert.equal(assessed.score, 71);
  assert.deepEqual(assessed.incompleteExplanation, []);

  const limited = buildGeoReadinessPresentation({
    geoReadiness: { ...INCOMPLETE, assessment_status: "access_limited", coverage: 0, score_bounds: null },
  });
  assert.equal(limited.statusLabel, "Could not assess because access was limited");
  assert.deepEqual(limited.incompleteExplanation, []);

  for (const geoReadiness of [undefined, { ...ASSESSED, coverage: "0.8" }]) {
    const neutral = buildGeoReadinessPresentation({ geoReadiness });
    assert.deepEqual(neutral.incompleteExplanation, []);
    assert.equal(neutral.score, null);
  }
});

test("summary validation, the 150-page cap and null-score withholding are unchanged", () => {
  for (const geoReadiness of [
    { ...ASSESSED, coverage: 0.79 },
    { ...ASSESSED, score: null },
    { ...ASSESSED, sample_pages: 151 },
    { ...INCOMPLETE, score: 40 },
    { ...INCOMPLETE, score_bounds: { lower: 60, upper: 40 } },
  ]) {
    const result = buildGeoReadinessPresentation({ geoReadiness, customerAccess: "full" });
    assert.equal(result.state, "unavailable");
    assert.equal(result.score, null);
    assert.equal(result.boundsLabel, "");
  }
  assert.equal(buildGeoReadinessPresentation({ geoReadiness: { ...INCOMPLETE, sample_pages: 150 } }).state, "insufficient_evidence");
});

test("experimental and non-citation disclaimers and full-authority restrictions are unchanged", () => {
  const findings = [{
    check_id: "template_integrity",
    affected_page_count: 1,
    evidence_samples: [{ page_url: "https://example.com/a" }],
    suggested_action: "Replace placeholders.",
  }];
  for (const [customerAccess, authority_verified] of [["preview", true], ["full", false], ["full", undefined]]) {
    const result = buildGeoReadinessPresentation({
      geoReadiness: { ...INCOMPLETE, findings, authority_verified },
      customerAccess,
      siteOrigin: "https://example.com",
    });
    assert.deepEqual(result.actions, []);
    assert.equal(result.methodologyLabel, METHODOLOGY);
    assert.equal(result.nonCitationLabel, NON_CITATION);
  }
  const full = buildGeoReadinessPresentation({
    geoReadiness: { ...INCOMPLETE, findings, authority_verified: true },
    customerAccess: "full",
    siteOrigin: "https://example.com",
  });
  assert.equal(full.actions.length, 1);
});

// Render the real panel; only the "@/" alias is resolved for the test bundle.
const panelPath = new URL("../../src/components/fixlist/GeoReadinessPanel.jsx", import.meta.url);
const srcRoot = new URL("../../src/", import.meta.url);
const bundled = await build({
  entryPoints: [panelPath.pathname],
  bundle: true,
  write: false,
  format: "esm",
  logLevel: "silent",
  plugins: [{
    name: "geo-panel-test",
    setup(builder) {
      builder.onResolve({ filter: /^@\// }, (args) => ({ path: new URL(`${args.path.slice(2)}.js`, srcRoot).pathname }));
      builder.onResolve({ filter: /^(react|react\/jsx-runtime)$/ }, (args) => ({ path: import.meta.resolve(args.path), external: true }));
    },
  }],
});
const { default: GeoReadinessPanel } = await import(
  `data:text/javascript;base64,${Buffer.from(bundled.outputFiles[0].text).toString("base64")}`
);
const renderPanel = (geoReadiness) => renderToStaticMarkup(
  React.createElement(GeoReadinessPanel, { geoReadiness, customerAccess: "preview" }),
);

test("the panel shows an incomplete assessment without a score and with rounded bounds", () => {
  const html = renderPanel(INCOMPLETE);
  assert.match(html, /GEO assessment incomplete/);
  assert.match(html, /Missing evidence is unknown, not a failed readiness check\./);
  assert.match(html, /at least 50% in every assessment area/);
  assert.match(html, /aria-label="GEO readiness score unavailable">—</);
  assert.match(html, />Not scored</);
  assert.doesNotMatch(html, /out of 100/);
  assert.match(html, /Unresolved outcomes: <\/dt><dd[^>]*>43\.5–92\.4 possible/);
  assert.doesNotMatch(html, /43\.589744|92\.307692/);
  assert.match(html, /not a statistical confidence interval/);
  assert.ok(html.includes(NON_CITATION));
});

test("an assessed panel keeps its score and shows no incomplete explanation", () => {
  const html = renderPanel(ASSESSED);
  assert.match(html, /aria-label="GEO readiness score 71">71</);
  assert.match(html, />out of 100</);
  assert.doesNotMatch(html, /GEO assessment incomplete|not a failed readiness check|Not scored/);
});
