import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const page = fs.readFileSync(new URL("../../src/pages/FixList.jsx", import.meta.url), "utf8");
const panel = fs.readFileSync(new URL("../../src/components/fixlist/GeoReadinessPanel.jsx", import.meta.url), "utf8");

test("the full result and free preview both use the reusable GEO panel", () => {
  assert.match(page, /<GeoReadinessPanel[\s\S]*?cards=\{customerRepairCards\}/);
  assert.match(page, /<GeoReadinessPanel[\s\S]*?customerAccess="preview"/);
});

test("the panel names evidence limits and unknown-outcome bounds without citation claims", () => {
  assert.match(panel, /GEO readiness/);
  assert.match(panel, /Unresolved outcomes/);
  assert.match(panel, /not a statistical confidence interval/);
  assert.match(panel, /nonCitationLabel/);
  assert.doesNotMatch(panel, /citation score|AI visibility score/i);
});

test("GEO remains separate from the SEO score and repair counts", () => {
  assert.doesNotMatch(panel, /healthScore|fix_count|total_fixes|displayedRepairCount/);
});
