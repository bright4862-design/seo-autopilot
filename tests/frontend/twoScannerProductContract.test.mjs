import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const scanFormSource = readFileSync(
  new URL("../../src/components/scan/ScanWebsiteForm.jsx", import.meta.url),
  "utf8",
);

test("the customer scan picker exposes only Standard 150 and Premium 5000", () => {
  const scanModesBlock = scanFormSource.match(/const SCAN_MODES = \[([\s\S]*?)\n\];/)?.[1] || "";

  assert.match(scanModesBlock, /Standard · 150/);
  assert.match(scanModesBlock, /Premium · 5,000/);
  assert.match(scanModesBlock, /premium_5000[\s\S]*disabled: true/);
  assert.doesNotMatch(scanModesBlock, /Quick check|\bDeep\b|Full site|\bbasic\b|\bquick\b|\bdeep\b/);
});

test("Standard 150 remains the only selectable beta request", () => {
  assert.match(scanFormSource, /useState\("advanced"\)/);
  assert.match(scanFormSource, /disabled=\{isLoading \|\| mode\.disabled\}/);
  assert.match(scanFormSource, /Premium large-site scans will be enabled after production benchmarking/);
});
