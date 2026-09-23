import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { transform } from "esbuild";

const componentUrl = new URL("../../src/components/fixlist/ScanComparisonPanel.jsx", import.meta.url);
const source = (await readFile(componentUrl, "utf8"))
  .replace('from "react"', `from ${JSON.stringify(import.meta.resolve("react"))}`)
  .replace('from "../../lib/scanComparisonPanelModel.js"', `from ${JSON.stringify(new URL("../../src/lib/scanComparisonPanelModel.js", import.meta.url).href)}`);
const compiled = await transform(source, { loader: "jsx", jsxFactory: "React.createElement", format: "esm" });
const moduleSource = `import React from ${JSON.stringify(import.meta.resolve("react"))};\n${compiled.code}`;
const { default: Panel } = await import(`data:text/javascript;base64,${Buffer.from(moduleSource).toString("base64")}`);

function presentation() {
  return {
    version: "scan_comparison_presentation_v1", previous_scan_id: "previous", current_scan_id: "current",
    score_line: "Health score changed from 75 to 72.",
    sample_line: "The assessed sample was 126 pages before and 139 pages now.",
    score_caution: "Because the assessed sample size changed, the score difference alone does not prove the site improved or regressed.",
    counts: { fixed: 0, still_detected: 0, came_back: 0, new_or_came_back: 1, could_not_verify: 6 },
    new_or_came_back_is_verified_claim: false, score_direction_claim_allowed: false,
    overall_improvement_or_regression_claim: null,
  };
}
function render(props = {}) {
  return renderToStaticMarkup(React.createElement(Panel, {
    presentation: presentation(), currentScanId: "current", authorityVerified: true, ...props,
  }));
}

test("Funbooker-shaped comparison renders unknowns and sample caution without claiming deterioration", () => {
  const html = render();
  assert.match(html, /What changed since the previous scan/);
  assert.match(html, /Could not verify<\/dt><dd[^>]*>6<\/dd>/);
  assert.match(html, /Not matched<\/dt><dd[^>]*>1<\/dd>/);
  assert.match(html, /75 to 72/);
  assert.match(html, /126 pages before and 139 pages now/);
  assert.match(html, /does not prove/);
  assert.match(html, /Differences in coverage or repair identity/);
  assert.doesNotMatch(html, /Newly observed|absent from the previous/);
  assert.doesNotMatch(html, /worse by|improved by|regressed by/);
  assert.match(html, /<section aria-labelledby="[^"]+"/);
  assert.match(html, /<dl/);
});

test("returned repairs are visible separately from unverified candidates", () => {
  const data = presentation(); data.counts.came_back = 2; data.counts.new_or_came_back = 3;
  assert.match(render({ presentation: data }), /Not matched<\/dt><dd[^>]*>1<\/dd>/);
  assert.match(render({ presentation: data }), /Returned<\/dt><dd[^>]*>2<\/dd>/);
});

for (const props of [
  { currentScanId: "another-scan" }, { currentScanId: undefined },
  { authorityVerified: false }, { authorityVerified: "true" },
  { presentation: { ...presentation(), version: "scan_comparison_v1" } },
  { presentation: { ...presentation(), score_caution: "" } },
]) {
  test(`unsafe comparison renders no evidence: ${JSON.stringify(props)}`, () => {
    const html = render(props);
    assert.match(html, /Comparison unavailable/);
    assert.doesNotMatch(html, /75 to 72|126 pages|<dl|another-scan|scan_comparison_v1/);
  });
}

test("first scan without comparison has no empty panel", () => {
  assert.equal(render({ presentation: null }), "");
});

test("server-provided text is escaped and source evidence remains unchanged", () => {
  const data = presentation(); data.score_line = "<img src=x onerror=alert(1)>";
  const before = structuredClone(data);
  const html = render({ presentation: data });
  assert.doesNotMatch(html, /<img/);
  assert.match(html, /&lt;img/);
  assert.deepEqual(data, before);
});
