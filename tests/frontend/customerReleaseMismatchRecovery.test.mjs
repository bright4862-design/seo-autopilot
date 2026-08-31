import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const reader = readFileSync("base44/functions/getCustomerScanResult/entry.ts", "utf8");
const compatibility = readFileSync("base44/functions/getCustomerScanResult/releaseCompatibility.js", "utf8");
const scanRuns = readFileSync("src/lib/scanRuns.js", "utf8");
const fixList = readFileSync("src/pages/FixList.jsx", "utf8");

test("a known-compatible historical release remains readable after the app advances", () => {
  assert.match(
    compatibility,
    /HISTORICAL_READABLE_RELEASE_FINGERPRINTS = Object\.freeze\(\[[\s\S]*?"5d94e93c54a9efb6"/,
    "the immediately previous verified Standard 150 release must stay explicitly readable",
  );
  assert.match(
    compatibility,
    /CUSTOMER_RESULT_READER_VERSION = "customer_result_reader_v2_historical_release_compatibility"/,
    "historical reader semantics must carry an explicit release component version",
  );
  assert.match(
    reader,
    /const runReleaseFingerprint = cleanText\(run\.beta_revision_fingerprint, 64\);[\s\S]*?!isReadableAuthorityReleaseFingerprint\(runReleaseFingerprint, RELEASE_FINGERPRINT\)[\s\S]*?503,[\s\S]*?"result_release_mismatch"/,
    "unknown release fingerprints must still fail closed",
  );
  assert.match(
    reader,
    /snapshot\.release_fingerprint !== runReleaseFingerprint/,
    "the verified snapshot must stay bound to the fingerprint persisted on its own ScanRun",
  );
  assert.doesNotMatch(
    reader,
    /snapshot\.release_fingerprint !== RELEASE_FINGERPRINT/,
    "historical authority must not be rewritten to the reader's current release fingerprint",
  );
});

test("an unknown mixed release is retryable and does not tell the customer to rescan", () => {
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
  const authorityGuard = reader.match(/const proof = cleanProof[\s\S]*?const runReleaseFingerprint/)?.[0] || "";
  assert.match(authorityGuard, /result_not_authoritative/);
  assert.match(authorityGuard, /release_gate_eligible !== true/);
  assert.match(authorityGuard, /score_is_provisional === true/);
  assert.match(authorityGuard, /evidence_quality_blocking === true/);
});
