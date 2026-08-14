import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const scanFormSource = readFileSync(new URL("../../src/components/scan/ScanWebsiteForm.jsx", import.meta.url), "utf8");
const fixListSource = readFileSync(new URL("../../src/pages/FixList.jsx", import.meta.url), "utf8");
const recoverySource = readFileSync(new URL("../../src/lib/scanStorageRecovery.js", import.meta.url), "utf8");
const fixItemEntity = JSON.parse(readFileSync(new URL("../../base44/entities/FixItem.jsonc", import.meta.url), "utf8"));

test("missing, empty, and malformed descriptions become one customer task", () => {
  assert.match(scanFormSource, /META_DESCRIPTION_GAP_RULES/);
  assert.match(scanFormSource, /meta_description_unusable/);
  assert.match(scanFormSource, /Add usable meta descriptions to/);
  assert.match(fixListSource, /mergeMetaDescriptionRecommendations/);
  assert.match(fixListSource, /Why these pages are grouped/);
});

test("the unified card explains search appearance without promising rankings", () => {
  assert.match(fixListSource, /search engines must create their own snippet/);
  assert.match(fixListSource, /potentially reducing qualified clicks/);
  assert.doesNotMatch(fixListSource, /meta descriptions improve rankings/i);
});

test("metadata state evidence survives browser and quota-safe persistence", () => {
  for (const field of ["meta_description_element_count", "meta_description_values", "meta_description_duplicate"]) {
    assert.match(scanFormSource, new RegExp(field));
  }
  for (const field of ["metadata_state_counts", "combined_rules", "grouping_explanation"]) {
    assert.match(scanFormSource, new RegExp(field));
    assert.match(recoverySource, new RegExp(field));
  }
});

test("fix instructions include template fallback and rendered-source verification", () => {
  assert.match(fixListSource, /build a reliable fallback/);
  assert.match(fixListSource, /initial server-rendered page source/);
  assert.match(fixListSource, /representative URL from each reported status/);
});


test("FixItem stores grouped recommendation evidence as durable columns", () => {
  for (const field of ["metadata_state_counts", "combined_rules", "grouping_explanation"]) {
    assert.ok(fixItemEntity.properties[field], `FixItem missing ${field}`);
  }
});
