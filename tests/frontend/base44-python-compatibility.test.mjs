import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const reviewFunction = readFileSync("base44/functions/aiReviewScan/entry.ts", "utf8");
const scanFunction = readFileSync("base44/functions/runAdvancedScan/entry.ts", "utf8");

test("Base44 accepts the deployed Python scanner, review, and calibration versions", () => {
  assert.match(scanFunction, /PYTHON_SCANNER_VERSION = "python_scanner_v3_bounded_request"/);
  assert.match(reviewFunction, /PYTHON_REVIEW_VERSION = "python_review_v2_structural_marketplace"/);
  assert.match(reviewFunction, /PYTHON_REVIEW_CALIBRATION_VERSION = "review_evidence_calibration_v5_utility_redirect"/);
});

test("Base44 rejects stale or uncalibrated Python review responses", () => {
  assert.match(reviewFunction, /reviewVersion !== PYTHON_REVIEW_VERSION/);
  assert.match(reviewFunction, /calibrationVersion !== PYTHON_REVIEW_CALIBRATION_VERSION/);
  assert.match(reviewFunction, /Python review calibration mismatch/);
});
