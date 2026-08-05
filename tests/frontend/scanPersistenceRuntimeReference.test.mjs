import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const scanForm = readFileSync("src/components/scan/ScanWebsiteForm.jsx", "utf8");

test("scan persistence path contains no unresolved storage normalizer", () => {
  assert.doesNotMatch(scanForm, /normalizeScanRecordForStorage/);
  assert.match(scanForm, /const durableRecord = mergedFinal;/);
  assert.match(scanForm, /completeScanRun\(scanRunHandle, durableRecord\)/);
});
