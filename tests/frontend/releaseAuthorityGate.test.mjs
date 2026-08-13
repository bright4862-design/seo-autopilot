import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { buildFixListFields, buildScanRunFields } from "../../src/lib/scanRunModel.js";

const authoritativeRecord = {
  scan_mode: "advanced",
  scan_status: "complete",
  score_is_provisional: false,
  scanner_version: "python_scanner_v3_bounded_request",
  scanner_build_revision: "authenticated_health_probe_v1",
  archetype_classifier_version: "archetype_classifier_v9_local_business_hospitality",
  advanced_scan_backend: "python_scanner_api",
  deno_fallback_used: false,
  review_version: "python_review_v2_structural_marketplace",
  review_evidence_calibration_version: "review_evidence_calibration_v5_utility_redirect",
  ai_review_backend: "python_review_api",
  python_review_fallback_used: false,
  beta_revision_fingerprint: "5caec7fdcabceee7",
  release_gate_eligible: true,
};

test("exact current authority markers pass the durable release gate", () => {
  assert.equal(buildScanRunFields(authoritativeRecord).release_gate_eligible, true);
  assert.equal(buildFixListFields(authoritativeRecord).is_authoritative, true);
});

test("unknown and legacy scanner build markers fail the durable release gate", () => {
  for (const scanner_build_revision of ["unknown_build", "leaf_seed_grok_proxy_v1"]) {
    const mismatchedRecord = { ...authoritativeRecord, scanner_build_revision };
    assert.equal(buildScanRunFields(mismatchedRecord).release_gate_eligible, false);
    assert.equal(buildFixListFields(mismatchedRecord).is_authoritative, false);
  }
});

test("the current scanner marker with a stale frozen fingerprint fails closed", () => {
  const staleFingerprint = { ...authoritativeRecord, beta_revision_fingerprint: "f9bac4b89ec7c1d8" };
  assert.equal(buildScanRunFields(staleFingerprint).release_gate_eligible, false);
  assert.equal(buildFixListFields(staleFingerprint).is_authoritative, false);
});

test("review quality true cannot override missing deployment authority markers", () => {
  const missingFingerprint = { ...authoritativeRecord, beta_revision_fingerprint: "" };
  assert.equal(buildScanRunFields(missingFingerprint).release_gate_eligible, false);
  assert.equal(buildFixListFields(missingFingerprint).is_authoritative, false);
});

test("stale classifier fails the release gate", () => {
  assert.equal(
    buildScanRunFields({ ...authoritativeRecord, archetype_classifier_version: "archetype_classifier_v4_publisher_route_families" }).release_gate_eligible,
    false
  );
});

test("a complete authoritative record overrides an inherited stale false", () => {
  const staleFalse = { ...authoritativeRecord, release_gate_eligible: false };
  assert.equal(buildScanRunFields(staleFalse).release_gate_eligible, true);
  assert.equal(buildFixListFields(staleFalse).is_authoritative, true);
});

test("provisional or limited Python Review results fail the release gate", () => {
  assert.equal(
    buildScanRunFields({ ...authoritativeRecord, score_is_provisional: true }).release_gate_eligible,
    false
  );
  assert.equal(
    buildScanRunFields({ ...authoritativeRecord, scan_status: "incomplete_evidence" }).release_gate_eligible,
    false
  );
});

test("scanner or review fallback fails the release gate", () => {
  assert.equal(
    buildScanRunFields({ ...authoritativeRecord, deno_fallback_used: true }).release_gate_eligible,
    false
  );
  assert.equal(
    buildScanRunFields({ ...authoritativeRecord, python_review_fallback_used: true }).release_gate_eligible,
    false
  );
});

// Regression: scanner-stage eligibility is provisional until Python Review adds its authority markers.
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
  assert.match(source, /mergePersistedScanRunRecord\(/);
  assert.match(source, /navigate\(`\/dashboard\?scan=complete&scan_id=\$\{encodeURIComponent\(scanId\)\}`\)/);
  assert.doesNotMatch(source, /saveScanForDashboard|localStorage\.setItem/);
});

// Regression: ScanRun 6a7378546447b124a1afd2d5 was written with
// release_gate_eligible true and is_authoritative true while authority_proof
// was null on the run, its FixList, and all 18 FixItems. The durable write
// re-inferred eligibility from version strings, discarding the explicit false
// the caller had already set. Version markers are a precondition; only the
// server seal from persistScanAuthority is authority.
test("a durable write cannot claim release authority without a server seal", () => {
  assert.equal(
    buildScanRunFields(authoritativeRecord, { requireAuthorityProof: true }).release_gate_eligible,
    false
  );
  assert.equal(
    buildFixListFields(authoritativeRecord, undefined, { requireAuthorityProof: true }).is_authoritative,
    false
  );
});

test("a durable write with a valid 64-hex seal keeps release authority", () => {
  const sealed = { ...authoritativeRecord, authority_proof: "a".repeat(64) };
  assert.equal(buildScanRunFields(sealed, { requireAuthorityProof: true }).release_gate_eligible, true);
  assert.equal(
    buildFixListFields(sealed, undefined, { requireAuthorityProof: true }).is_authoritative,
    true
  );
});

test("malformed or truncated proofs are not accepted as a seal", () => {
  for (const authority_proof of ["", "not-a-proof", "A".repeat(64), "a".repeat(63), "a".repeat(65)]) {
    assert.equal(
      buildScanRunFields({ ...authoritativeRecord, authority_proof }, { requireAuthorityProof: true }).release_gate_eligible,
      false,
      `proof must be rejected: ${JSON.stringify(authority_proof)}`
    );
  }
});

test("a seal cannot rescue a record that fails the version preconditions", () => {
  const sealedButStale = {
    ...authoritativeRecord,
    authority_proof: "a".repeat(64),
    beta_revision_fingerprint: "f9bac4b89ec7c1d8",
  };
  assert.equal(
    buildScanRunFields(sealedButStale, { requireAuthorityProof: true }).release_gate_eligible,
    false
  );
});

test("the unsigned durable write path requires the seal", () => {
  const scanRuns = readFileSync(new URL("../../src/lib/scanRuns.js", import.meta.url), "utf8");
  assert.match(scanRuns, /buildScanRunFields\(mergedRecord, \{[\s\S]*?requireAuthorityProof: true,?[\s\S]*?\}\)/);
  assert.match(scanRuns, /buildFixListFields\(mergedRecord, fixes, \{ requireAuthorityProof: true \}\)/);
});
