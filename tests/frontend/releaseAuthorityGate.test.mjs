import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { buildFixListFields, buildScanRunFields } from "../../src/lib/scanRunModel.js";

const authoritativeRecord = {
  scan_mode: "advanced",
  scanner_version: "python_scanner_v3_bounded_request",
  scanner_build_revision: "hard_page_cap_response_v1",
  archetype_classifier_version: "archetype_classifier_v8_platform_product_routes",
  advanced_scan_backend: "python_scanner_api",
  deno_fallback_used: false,
  review_version: "python_review_v2_structural_marketplace",
  review_evidence_calibration_version: "review_evidence_calibration_v5_utility_redirect",
  ai_review_backend: "python_review_api",
  python_review_fallback_used: false,
  beta_revision_fingerprint: "4a560c34a3d68c6b",
  release_gate_eligible: true,
};

test("exact current authority markers pass the durable release gate", () => {
  assert.equal(buildScanRunFields(authoritativeRecord).release_gate_eligible, true);
  assert.equal(buildFixListFields(authoritativeRecord).is_authoritative, true);
});

test("review quality true cannot override missing deployment authority markers", () => {
  const missingFingerprint = { ...authoritativeRecord, beta_revision_fingerprint: "" };
  assert.equal(buildScanRunFields(missingFingerprint).release_gate_eligible, false);
  assert.equal(buildFixListFields(missingFingerprint).is_authoritative, false);
});

test("stale classifier or explicit review rejection fails the release gate", () => {
  assert.equal(
    buildScanRunFields({ ...authoritativeRecord, archetype_classifier_version: "archetype_classifier_v4_publisher_route_families" }).release_gate_eligible,
    false
  );
  assert.equal(
    buildScanRunFields({ ...authoritativeRecord, release_gate_eligible: false }).release_gate_eligible,
    false
  );
});

test("the frontend re-evaluates the completed record instead of AND-ing the scanner-stage gate", () => {
  const source = readFileSync(
    new URL("../../src/components/scan/ScanWebsiteForm.jsx", import.meta.url),
    "utf8"
  );

  assert.match(source, /const mergedRecord = \{/);
  assert.match(
    source,
    /release_gate_eligible: buildScanRunFields\(mergedRecord\)\.release_gate_eligible/
  );
  assert.doesNotMatch(
    source,
    /scanData\?\.release_gate_eligible === true && aiData\?\.release_gate_eligible === true/
  );
});
