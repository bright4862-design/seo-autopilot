import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

import {
  REVIEW_ATTESTATION_VERSION,
  buildAuthoritySnapshot,
  hasCompleteAcceptanceEvidence as hasCompleteAuthorityAcceptanceEvidence,
} from "../../base44/functions/persistDurableScanAuthority/authoritySnapshot.js";
import { authorityRowsFromSnapshot } from "../../base44/functions/persistDurableScanAuthority/authorityRows.js";
import {
  LIMITED_RESULT_INTEGRITY_VERSION,
  buildLimitedResultSnapshot,
  hasCompleteAcceptanceEvidence as hasCompleteLimitedAcceptanceEvidence,
  limitedRowsFromSnapshot,
  requiresCompleteAcceptanceEvidence,
} from "../../base44/functions/persistLimitedScanResult/limitedResultIntegrity.js";
import {
  authoritySnapshotFromRows,
  buildCustomerProjection,
} from "../../base44/functions/getCustomerScanResult/projection.js";
import { RELEASE_COMPONENT_VERSIONS, RELEASE_FINGERPRINT } from "../../src/lib/generatedReleaseContract.js";

const ACCEPTANCE_VERSION = RELEASE_COMPONENT_VERSIONS.acceptance_evidence_version;

function acceptedSnapshot() {
  return buildAuthoritySnapshot({
    scan: {
      submitted_url: "https://example.com/",
      scanner_version: "python_scanner_v3_bounded_request",
      scanner_build_revision: "authenticated_health_probe_v1",
      advanced_scan_backend: "python_scanner_api",
      deno_fallback_used: false,
      beta_revision_fingerprint: RELEASE_FINGERPRINT,
      metadata_evidence_version: "metadata_v1",
      title_evidence_version: "title_v1",
      pages_found: 200,
      pages_crawled: 150,
      worker_peak_memory_bytes: 268_435_456,
    },
    review: {
      archetype_classifier_version: "archetype_classifier_v10_structural_finance_member_retail",
      review_version: "python_review_v2_structural_marketplace",
      review_evidence_calibration_version: "review_evidence_calibration_v6_health_score_v2",
      ai_review_backend: "python_review_api",
      python_review_fallback_used: false,
      release_gate_eligible: true,
      score_is_provisional: false,
      evidence_quality_blocking: false,
      beta_revision_fingerprint: RELEASE_FINGERPRINT,
      metadata_evidence_version: "metadata_v1",
      title_evidence_version: "title_v1",
      scan_status: "complete",
      health_score: 82,
      health_grade: "Good",
      site_fingerprint: {
        classification: {
          state: "classified",
          evidence_sufficiency: "sufficient",
          usable_pages: 150,
          complete_small_site_inventory: false,
        },
        coverage_assessment: {
          state: "sufficient",
          coverage_authority_version: "coverage_authority_v1_shared_decision",
        },
      },
      classification_integrity: {
        version: ACCEPTANCE_VERSION,
        state: "classified",
        verdict: "classified",
        classifier_version: "archetype_classifier_v10_structural_finance_member_retail",
        evidence_sufficiency: "sufficient",
        usable_pages: 150,
        complete_small_site_inventory: false,
      },
      coverage_authority_evidence: {
        coverage_authority_evidence_version: "coverage_authority_evidence_v2_authoritative",
        assessment: "sufficient",
      },
      recommendations: [],
    },
    identity: {
      scan_id: "scan_acceptance",
      project_id: "project_acceptance",
      normalized_domain: "example.com",
    },
    userId: "user_acceptance",
    now: "2026-08-27T08:00:00.000Z",
  });
}

test("authoritative rows seal and project every Standard 150 observation", () => {
  const snapshot = acceptedSnapshot();

  assert.equal(REVIEW_ATTESTATION_VERSION, "standard_review_snapshot_hmac_v5_score_explanation");
  assert.equal(snapshot.version, REVIEW_ATTESTATION_VERSION);
  assert.equal(snapshot.scan.coverage_authority_evidence.assessment, "sufficient");
  assert.equal(snapshot.scan.classification_integrity.state, "classified");
  assert.equal(snapshot.scan.classification_verdict, "classified");
  assert.equal(snapshot.scan.worker_peak_memory_bytes, 268_435_456);

  const rows = authorityRowsFromSnapshot(snapshot, {
    fixListId: "fixlist_acceptance",
    ownerUserId: "user_acceptance",
    proof: "a".repeat(64),
  });
  const run = {
    id: "scan_acceptance",
    project_id: "project_acceptance",
    ...rows.scanRun,
  };
  const fixList = { id: "fixlist_acceptance", ...rows.fixList };
  const rebuilt = authoritySnapshotFromRows({
    run,
    fixList,
    fixItems: [],
    userId: "user_acceptance",
  });
  assert.deepEqual(rebuilt, snapshot);

  const projected = buildCustomerProjection({
    run,
    fixList,
    fixItems: [],
    fullAccess: true,
    authorityVerified: true,
  });
  assert.equal(projected.run.coverage_authority_evidence.assessment, "sufficient");
  assert.equal(projected.run.classification_integrity.state, "classified");
  assert.equal(projected.run.classification_verdict, "classified");
  assert.equal(projected.run.worker_peak_memory_bytes, 268_435_456);
});

test("locked projections do not expose acceptance evidence", () => {
  const snapshot = acceptedSnapshot();
  const rows = authorityRowsFromSnapshot(snapshot, {
    fixListId: "fixlist_acceptance",
    ownerUserId: "user_acceptance",
    proof: "a".repeat(64),
  });
  const run = { id: "scan_acceptance", project_id: "project_acceptance", ...rows.scanRun };
  const projected = buildCustomerProjection({
    run,
    fixList: null,
    fixItems: [],
    fullAccess: false,
    authorityVerified: false,
  });

  assert.equal("coverage_authority_evidence" in projected.run, false);
  assert.equal("classification_integrity" in projected.run, false);
  assert.equal("worker_peak_memory_bytes" in projected.run, false);
});

test("limited rows bind and project the same acceptance observations", () => {
  const snapshot = buildLimitedResultSnapshot({
    identity: {
      scan_id: "scan_limited",
      project_id: "project_limited",
      owner_user_id: "user_limited",
      request_id: "request_limited",
      attempt_count: 1,
      normalized_domain: "example.com",
    },
    scan: {
      submitted_url: "https://example.com/",
      scanner_version: "python_scanner_v3_bounded_request",
      scanner_build_revision: "authenticated_health_probe_v1",
      beta_revision_fingerprint: RELEASE_FINGERPRINT,
      worker_peak_memory_bytes: 201_326_592,
      peak_memory_bytes: 201_326_592,
      pages_found: 2_000,
      pages_crawled: 40,
    },
    review: {
      scan_status: "inconclusive_insufficient_evidence",
      health_score: 48,
      health_grade: "Insufficient evidence",
      limitation: "The retained sample is materially thin.",
      coverage_state: "limited_coverage",
      coverage_reasons: ["coverage_ratio_below_minimum"],
      coverage_authority_version: "coverage_authority_v1_shared_decision",
      coverage_authority_evidence: {
        coverage_authority_evidence_version: "coverage_authority_evidence_v2_authoritative",
        assessment: "insufficient_sample",
      },
      classification_integrity: {
        version: ACCEPTANCE_VERSION,
        state: "inconclusive_insufficient_evidence",
        verdict: "inconclusive_insufficient_evidence",
        classifier_version: "archetype_classifier_v10_structural_finance_member_retail",
        evidence_sufficiency: "insufficient",
        usable_pages: 40,
        complete_small_site_inventory: false,
      },
      classification_verdict: "inconclusive_insufficient_evidence",
      recommendations: [{ fix_id: "fix_limited", issue_title: "Review coverage", priority: "medium" }],
    },
    now: "2026-08-27T08:00:00.000Z",
  });

  assert.equal(
    LIMITED_RESULT_INTEGRITY_VERSION,
    "standard_limited_result_integrity_v4_focused_scope_effective_path",
  );
  assert.equal(snapshot.scan.coverage_authority_evidence.assessment, "insufficient_sample");
  assert.equal(snapshot.scan.classification_integrity.state, "inconclusive_insufficient_evidence");
  assert.equal(snapshot.scan.worker_peak_memory_bytes, 201_326_592);

  const rows = limitedRowsFromSnapshot(snapshot, {
    fixListId: "fixlist_limited",
    proof: "b".repeat(64),
  });
  const projected = buildCustomerProjection({
    run: { id: "scan_limited", project_id: "project_limited", ...rows.scanRun },
    fixList: { id: "fixlist_limited", ...rows.fixList },
    fixItems: rows.fixItems,
    fullAccess: true,
    authorityVerified: false,
    resultIntegrityVerified: true,
  });

  assert.equal(projected.authority_verified, false);
  assert.equal(projected.result_integrity_verified, true);
  assert.equal(projected.run.coverage_authority_evidence.assessment, "insufficient_sample");
  assert.equal(projected.run.classification_verdict, "inconclusive_insufficient_evidence");
  assert.equal(projected.run.worker_peak_memory_bytes, 201_326_592);
});


test("new authoritative writes fail closed when measured memory is missing", () => {
  const scan = {
    worker_peak_memory_bytes: undefined,
  };
  const review = {
    coverage_authority_evidence: {
      coverage_authority_evidence_version: "coverage_authority_evidence_v2_authoritative",
      assessment: "sufficient",
    },
    classification_integrity: {
      version: ACCEPTANCE_VERSION,
      state: "classified",
      verdict: "classified",
      classifier_version: "classifier-v1",
      evidence_sufficiency: "sufficient",
      usable_pages: 150,
      complete_small_site_inventory: false,
    },
  };
  assert.equal(hasCompleteAuthorityAcceptanceEvidence(scan, review), false);
  const writerSource = readFileSync(
    new URL("../../base44/functions/persistDurableScanAuthority/entry.ts", import.meta.url),
    "utf8",
  );
  assert.match(writerSource, /!hasCompleteAcceptanceEvidence\(authorityScanResult, review\)/);
  assert.match(writerSource, /authority_acceptance_evidence_incomplete/);
});

test("a verdict alone cannot manufacture classification integrity on a new limited write", () => {
  assert.equal(hasCompleteLimitedAcceptanceEvidence(
    { worker_peak_memory_bytes: 123_456_789 },
    {
      coverage_authority_evidence: {
        coverage_authority_evidence_version: "coverage_authority_evidence_v2_authoritative",
        assessment: "insufficient_sample",
      },
      classification_verdict: "classified",
    },
  ), false);
});

test("customer projection suppresses incomplete current-contract acceptance evidence", () => {
  const projected = buildCustomerProjection({
    run: {
      id: "scan-incomplete",
      project_id: "p",
      status: "complete",
      beta_revision_fingerprint: RELEASE_FINGERPRINT,
      authority_seal_version: REVIEW_ATTESTATION_VERSION,
      coverage_authority_evidence: {
        coverage_authority_evidence_version: "coverage_authority_evidence_v2_authoritative",
        assessment: "sufficient",
      },
      classification_verdict: "classified",
      worker_peak_memory_bytes: 0,
    },
    fixList: { id: "f", is_authoritative: true },
    fixItems: [],
    fullAccess: true,
    authorityVerified: true,
  });

  assert.equal("coverage_authority_evidence" in projected.run, false);
  assert.equal("classification_integrity" in projected.run, false);
  assert.equal("classification_verdict" in projected.run, false);
  assert.equal("worker_peak_memory_bytes" in projected.run, false);
});


test("null or stale classification evidence cannot satisfy a new acceptance contract", () => {
  const scan = { worker_peak_memory_bytes: 123_456_789 };
  const baseReview = {
    coverage_authority_evidence: {
      coverage_authority_evidence_version: "coverage_authority_evidence_v2_authoritative",
      assessment: "sufficient",
    },
    classification_integrity: {
      version: ACCEPTANCE_VERSION,
      state: "classified",
      verdict: "classified",
      classifier_version: "classifier-v1",
      evidence_sufficiency: "sufficient",
      usable_pages: null,
      complete_small_site_inventory: false,
    },
  };
  assert.equal(hasCompleteAuthorityAcceptanceEvidence(scan, baseReview), false);
  assert.equal(hasCompleteLimitedAcceptanceEvidence(scan, baseReview), false);

  const staleReview = {
    ...baseReview,
    classification_integrity: {
      ...baseReview.classification_integrity,
      usable_pages: 10,
      version: "standard150_acceptance_evidence_v1",
    },
  };
  assert.equal(hasCompleteAuthorityAcceptanceEvidence(scan, staleReview), false);
  assert.equal(hasCompleteLimitedAcceptanceEvidence(scan, staleReview), false);
});

test("only genuine historical limited-v1 recovery is exempt from the new completeness gate", () => {
  assert.equal(requiresCompleteAcceptanceEvidence(
    "limited",
    "standard_limited_result_integrity_v1",
  ), false);
  assert.equal(requiresCompleteAcceptanceEvidence(
    "limited",
    LIMITED_RESULT_INTEGRITY_VERSION,
  ), true);
  assert.equal(requiresCompleteAcceptanceEvidence("queued", ""), true);
});
