import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import {
  CURRENT_IDENTITY_AUTHORITY_VERSION,
  CURRENT_IDENTITY_EVIDENCE_VERSION,
  CURRENT_REPAIR_COVERAGE_VERSION,
  HISTORICAL_AUTHORITY_VERSIONS,
  KNOWN_STAGE2_OBSERVED_EVIDENCE_VERSIONS,
  classifyEvidenceCompatibility,
  requireReadableEvidence,
} from "../../scripts/stage4EvidenceCompatibility.mjs";

function current(overrides = {}) {
  return {
    authority_seal_version: CURRENT_IDENTITY_AUTHORITY_VERSION,
    evidence_url_identity_version: CURRENT_IDENTITY_EVIDENCE_VERSION,
    repair_coverage_version: CURRENT_REPAIR_COVERAGE_VERSION,
    ...overrides,
  };
}

test("all frozen historical authority fixtures remain readable without mutation", () => {
  const path = "tests/fixtures/geo/historical-seals.json";
  const original = fs.readFileSync(path, "utf8");
  const fixtures = JSON.parse(original);
  const observedVersions = new Set();
  for (const fixture of fixtures) {
    const run = fixture?.data?.run || {};
    const before = JSON.stringify(fixture);
    const result = classifyEvidenceCompatibility(run);
    assert.equal(result.readable, true, `${run.authority_seal_version} must remain readable`);
    assert.equal(result.mode, "historical");
    assert.equal(JSON.stringify(fixture), before, "compatibility checks must not rewrite historical bytes");
    observedVersions.add(run.authority_seal_version);
  }
  for (const version of observedVersions) assert.ok(HISTORICAL_AUTHORITY_VERSIONS.includes(version));
  assert.equal(fs.readFileSync(path, "utf8"), original, "fixture bytes must remain unchanged");
});

test("the current identity seal requires its exact identity and coverage versions", () => {
  assert.deepEqual(classifyEvidenceCompatibility(current()), {
    readable: true,
    mode: "current_identity",
    reason: "supported_current_evidence",
  });
  assert.equal(classifyEvidenceCompatibility(current({ evidence_url_identity_version: "future_identity_v99" })).readable, false);
  assert.equal(classifyEvidenceCompatibility(current({ repair_coverage_version: "future_coverage_v99" })).readable, false);
});

test("known Stage-2 observed evidence can be admitted only with bounded verified pages", () => {
  for (const version of KNOWN_STAGE2_OBSERVED_EVIDENCE_VERSIONS) {
    const result = classifyEvidenceCompatibility(current({
      observed_evidence_version: version,
      verified_observed_pages: ["https://example.com/a"],
    }));
    assert.equal(result.readable, true, version);
    assert.equal(result.mode, "current_with_observed_evidence");
  }
  assert.equal(classifyEvidenceCompatibility(current({
    observed_evidence_version: "soft_404_probe_v1_active_baseline",
    verified_observed_pages: [],
  })).readable, false);
});

test("unknown authority and observed evidence versions fail closed", () => {
  assert.throws(() => requireReadableEvidence({ authority_seal_version: "standard_review_snapshot_hmac_future" }), /unsupported evidence compatibility/);
  assert.deepEqual(classifyEvidenceCompatibility(current({
    observed_evidence_version: "future_probe_v9",
    verified_observed_pages: ["https://example.com/a"],
  })), {
    readable: false,
    mode: "rejected",
    reason: "unknown_observed_evidence_version",
  });
});
