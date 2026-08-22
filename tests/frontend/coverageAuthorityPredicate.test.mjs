import assert from "node:assert/strict";
import test from "node:test";

import {
  firstFailedAuthorityPredicate,
  isAuthorityEligible,
} from "../../base44/functions/persistDurableScanAuthority/authoritySnapshot.js";
import { RELEASE_COMPONENT_VERSIONS, RELEASE_FINGERPRINT } from "../../src/lib/generatedReleaseContract.js";

/**
 * Patch C part 1, item 6 - Base44 refuses a thin crawl on its own evidence.
 *
 * Python already sets release_gate_eligible false for a limited crawl, so today
 * the gate holds. But it holds on one side only: if that flag were ever true
 * while the coverage assessment said limited -- a stale worker, a hand-built
 * envelope, a future refactor that sets the flag before the assessment runs --
 * Base44 would seal it. The authority predicate must be able to say no using
 * the coverage state itself, not just the summary boolean derived from it.
 */

function scan() {
  return {
    scanner_version: RELEASE_COMPONENT_VERSIONS.scanner_version,
    scanner_build_revision: RELEASE_COMPONENT_VERSIONS.scanner_build_revision,
    advanced_scan_backend: "python_scanner_api",
    deno_fallback_used: false,
    beta_revision_fingerprint: RELEASE_FINGERPRINT,
    metadata_evidence_version: "metadata_v1",
    title_evidence_version: "title_v1",
  };
}

function review({ coverageState = "sufficient", ...overrides } = {}) {
  return {
    archetype_classifier_version: RELEASE_COMPONENT_VERSIONS.archetype_classifier_version,
    review_version: RELEASE_COMPONENT_VERSIONS.review_version,
    review_evidence_calibration_version: RELEASE_COMPONENT_VERSIONS.review_evidence_calibration_version,
    ai_review_backend: "python_review_api",
    python_review_fallback_used: false,
    release_gate_eligible: true,
    score_is_provisional: false,
    evidence_quality_blocking: false,
    beta_revision_fingerprint: RELEASE_FINGERPRINT,
    metadata_evidence_version: "metadata_v1",
    title_evidence_version: "title_v1",
    scan_status: "complete",
    site_fingerprint: {
      coverage_assessment: {
        state: coverageState,
        coverage_authority_version: "coverage_authority_v1_shared_decision",
      },
    },
    ...overrides,
  };
}

test("a sufficient crawl is still authoritative", () => {
  assert.equal(firstFailedAuthorityPredicate(scan(), review()), "");
  assert.equal(isAuthorityEligible(scan(), review()), true);
});

for (const state of ["limited_coverage", "inventory_unproven", "access_limited"]) {
  test(`Base44 refuses ${state} even when the review claims eligibility`, () => {
    /** The exact promotion this predicate exists to stop. */
    const claimed = review({ coverageState: state, release_gate_eligible: true, score_is_provisional: false });

    assert.equal(firstFailedAuthorityPredicate(scan(), claimed), "coverage_state");
    assert.equal(isAuthorityEligible(scan(), claimed), false);
  });
}

test("a missing coverage assessment is refused rather than assumed sufficient", () => {
  /** Fail closed: absence of the verdict is not the verdict "sufficient". */
  const withoutAssessment = review();
  delete withoutAssessment.site_fingerprint;

  assert.equal(firstFailedAuthorityPredicate(scan(), withoutAssessment), "coverage_state");
});

test("an unrecognised coverage state is refused", () => {
  assert.equal(firstFailedAuthorityPredicate(scan(), review({ coverageState: "probably_fine" })), "coverage_state");
});

test("the coverage authority version must be present", () => {
  const noVersion = review();
  noVersion.site_fingerprint.coverage_assessment.coverage_authority_version = "";

  assert.equal(firstFailedAuthorityPredicate(scan(), noVersion), "coverage_authority_version");
});

test("the existing predicates are untouched", () => {
  assert.equal(firstFailedAuthorityPredicate(scan(), review({ release_gate_eligible: false })), "release_gate_eligible");
  assert.equal(firstFailedAuthorityPredicate(scan(), review({ score_is_provisional: true })), "score_is_provisional");
  assert.equal(firstFailedAuthorityPredicate({ ...scan(), deno_fallback_used: true }, review()), "deno_fallback_used");
});
