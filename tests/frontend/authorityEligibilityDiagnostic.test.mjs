import { RELEASE_FINGERPRINT } from "../../src/lib/generatedReleaseContract.js";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  firstFailedAuthorityPredicate,
  isAuthorityEligible,
} from "../../base44/functions/persistDurableScanAuthority/authoritySnapshot.js";

function eligiblePayload() {
  return {
    scan: {
      scanner_version: "python_scanner_v3_bounded_request",
      scanner_build_revision: "authenticated_health_probe_v1",
      advanced_scan_backend: "python_scanner_api",
      deno_fallback_used: false,
      beta_revision_fingerprint: RELEASE_FINGERPRINT,
      metadata_evidence_version: "metadata_evidence_v1",
      title_evidence_version: "title_evidence_v1",
    },
    review: {
      archetype_classifier_version: "archetype_classifier_v9_local_business_hospitality",
      review_version: "python_review_v2_structural_marketplace",
      review_evidence_calibration_version: "review_evidence_calibration_v6_health_score_v2",
      beta_revision_fingerprint: RELEASE_FINGERPRINT,
      ai_review_backend: "python_review_api",
      python_review_fallback_used: false,
      release_gate_eligible: true,
      score_is_provisional: false,
      evidence_quality_blocking: false,
    },
  };
}

const failures = [
  ["scanner_version", ({ scan }) => { scan.scanner_version = "stale"; }],
  ["scanner_build_revision", ({ scan }) => { scan.scanner_build_revision = "stale"; }],
  ["advanced_scan_backend", ({ scan }) => { scan.advanced_scan_backend = "stale"; }],
  ["deno_fallback_used", ({ scan }) => { scan.deno_fallback_used = true; }],
  ["archetype_classifier_version", ({ review }) => { review.archetype_classifier_version = "stale"; }],
  ["review_version", ({ review }) => { review.review_version = "stale"; }],
  ["review_evidence_calibration_version", ({ review }) => { review.review_evidence_calibration_version = "stale"; }],
  ["beta_revision_fingerprint", ({ review }) => { review.beta_revision_fingerprint = "stale"; }],
  ["metadata_evidence_version", ({ scan }) => { scan.metadata_evidence_version = ""; }],
  ["title_evidence_version", ({ scan }) => { scan.title_evidence_version = ""; }],
  ["ai_review_backend", ({ review }) => { review.ai_review_backend = "stale"; }],
  ["python_review_fallback_used", ({ review }) => { review.python_review_fallback_used = true; }],
  ["release_gate_eligible", ({ review }) => { review.release_gate_eligible = false; }],
  ["score_is_provisional", ({ review }) => { review.score_is_provisional = true; }],
  ["evidence_quality_blocking", ({ review }) => { review.evidence_quality_blocking = true; }],
];

test("authority diagnostics preserve the existing eligible result", () => {
  const payload = eligiblePayload();
  assert.equal(firstFailedAuthorityPredicate(payload.scan, payload.review), "");
  assert.equal(isAuthorityEligible(payload.scan, payload.review), true);
});

test("authority diagnostics name the first failed predicate in gate order", () => {
  for (const [expected, mutate] of failures) {
    const payload = eligiblePayload();
    mutate(payload);
    assert.equal(firstFailedAuthorityPredicate(payload.scan, payload.review), expected);
    assert.equal(isAuthorityEligible(payload.scan, payload.review), false);
  }

  const payload = eligiblePayload();
  payload.scan.scanner_version = "stale";
  payload.review.release_gate_eligible = false;
  assert.equal(firstFailedAuthorityPredicate(payload.scan, payload.review), "scanner_version");
});

test("durable persistence publishes only the fixed predicate name", () => {
  const source = readFileSync(
    new URL("../../base44/functions/persistDurableScanAuthority/index.ts", import.meta.url),
    "utf8",
  );
  assert.match(source, /firstFailedAuthorityPredicate\(scanResult, review\)/);
  assert.match(source, /`authority_snapshot_not_eligible__\$\{failedPredicate\}`/);
  assert.doesNotMatch(source, /JSON\.stringify\((?:scanResult|review)\)/);
});
