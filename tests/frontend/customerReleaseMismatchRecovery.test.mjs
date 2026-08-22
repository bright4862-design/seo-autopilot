import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const reader = readFileSync("base44/functions/getCustomerScanResult/index.ts", "utf8");
const scanRuns = readFileSync("src/lib/scanRuns.js", "utf8");
const fixList = readFileSync("src/pages/FixList.jsx", "utf8");

test("a mixed release is retryable and does not tell the customer to rescan", () => {
  assert.match(
    reader,
    /run\.beta_revision_fingerprint !== RELEASE_FINGERPRINT[\s\S]*?503,[\s\S]*?"result_release_mismatch"/,
  );
  assert.match(scanRuns, /result_release_mismatch:\s*"release_mismatch"/);
  assert.match(
    scanRuns,
    /CUSTOMER_RECOVERY_RETRYABLE_KINDS = new Set\(\[[^\]]*"release_mismatch"/,
  );
  assert.match(fixList, /release_mismatch:[\s\S]*?action:\s*"retry"/);
  assert.match(fixList, /Your scan is saved/);
  assert.doesNotMatch(
    fixList.match(/release_mismatch:[\s\S]*?\n  },/)?.[0] || "",
    /fresh scan|new_scan/i,
  );
});

test("invalid authority evidence remains a non-retryable scan failure", () => {
  const authorityGuard = reader.match(/const proof = cleanProof[\s\S]*?if \(run\.beta_revision_fingerprint/)?.[0] || "";
  assert.match(authorityGuard, /result_not_authoritative/);
  assert.match(authorityGuard, /release_gate_eligible !== true/);
  assert.match(authorityGuard, /score_is_provisional === true/);
  assert.match(authorityGuard, /evidence_quality_blocking === true/);
});
