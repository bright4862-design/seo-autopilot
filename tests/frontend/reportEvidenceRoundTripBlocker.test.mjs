import assert from "node:assert/strict";
import test from "node:test";

import {
  buildAuthoritySnapshot,
} from "../../base44/functions/persistDurableScanAuthority/authoritySnapshot.js";
import { authorityRowsFromSnapshot } from "../../base44/functions/persistDurableScanAuthority/authorityRows.js";
import {
  createAuthoritySeal,
  verifyAuthoritySeal,
} from "../../base44/functions/persistDurableScanAuthority/authoritySeal.js";
import { authoritySnapshotFromRows } from "../../base44/functions/getCustomerScanResult/projection.js";
import {
  buildLimitedResultSnapshot,
  createLimitedResultProof,
  limitedRowsFromSnapshot,
  verifyLimitedResultProof,
} from "../../base44/functions/getCustomerScanResult/limitedResultIntegrity.js";

const NOW = "2026-09-09T09:00:00.000Z";
const SECRET = "report-evidence-round-trip-test-secret-never-deployed";

const redirectEvidence = {
  requested_url: "https://example.com/legacy-page",
  redirect_chain: [
    {
      url: "https://example.com/legacy-page",
      status: 301,
      location: "https://example.com/",
    },
  ],
  final_url: "https://example.com/",
  final_status: 200,
  final_content_type: "text/html; charset=utf-8",
  body_bytes: 1234,
  html_parse_ok: true,
  fetch_error: "",
  robots_status: "allowed",
  canonical_url: "https://example.com/",
  noindex: false,
  classification: "redirect_to_wrong_destination",
};

function finding() {
  return {
    fix_id: "redirect-wrong-destination-1",
    rule: "redirect_destination_failed",
    category: "indexability",
    issue_title: "Fix a redirect that sends visitors to the wrong page",
    plain_english_explanation: "The requested deep URL collapses to the homepage.",
    why_it_matters: "The destination is usable but not a relevant replacement.",
    recommended_value: "Restore the intended page or choose a verified relevant replacement.",
    simple_next_step: "Review the observed destination before changing the redirect.",
    page_scope: "page",
    page_template_family: "standard",
    page_url: "/legacy-page",
    affected_pages: ["/legacy-page"],
    evidence_status: "confirmed",
    verification_state: "verified",
    confidence_score: 99,
    priority: "high",
    difficulty: "developer",
    who_can_do_this: "your_web_person",
    requires_developer: true,
    raw_finding: {
      redirect_outcome: "redirect_to_wrong_destination",
      redirect_fetch_evidence: structuredClone(redirectEvidence),
      redirect_fetch_evidence_samples: [structuredClone(redirectEvidence)],
      redirect_observed_count: 1,
      redirect_evidence_truncated: false,
      non_scoring: false,
      score_impact: 0,
    },
  };
}

function authoritySnapshot() {
  return buildAuthoritySnapshot({
    scan: {
      submitted_url: "https://example.com/",
      pages_found: 2,
      pages_crawled: 2,
    },
    review: {
      scan_status: "complete",
      health_score: 80,
      health_grade: "Needs attention",
      recommendations: [finding()],
    },
    identity: {
      scan_id: "scan_report_evidence",
      project_id: "project_report_evidence",
      normalized_domain: "example.com",
    },
    userId: "user_report_evidence",
    now: NOW,
  });
}

test("authority report evidence survives signing, stored rows, reconstruction, and proof verification", async () => {
  const snapshot = authoritySnapshot();
  assert.deepEqual(snapshot.recommendations[0].raw_finding.redirect_fetch_evidence, redirectEvidence);

  const proof = await createAuthoritySeal(snapshot, SECRET);
  const rows = authorityRowsFromSnapshot(snapshot, {
    fixListId: "fixlist_report_evidence",
    ownerUserId: "user_report_evidence",
    proof,
  });
  const storedFixItems = structuredClone(rows.fixItems);
  const reconstructed = authoritySnapshotFromRows({
    run: {
      id: "scan_report_evidence",
      project_id: "project_report_evidence",
      normalized_domain: "example.com",
      ...structuredClone(rows.scanRun),
    },
    fixList: { id: "fixlist_report_evidence", ...structuredClone(rows.fixList) },
    fixItems: storedFixItems,
    userId: "user_report_evidence",
  });

  assert.deepEqual(reconstructed, snapshot);
  assert.equal(await verifyAuthoritySeal(reconstructed, SECRET, proof), true);
});

test("limited report evidence survives stored rows and proof verification", async () => {
  const snapshot = buildLimitedResultSnapshot({
    identity: {
      scan_id: "scan_limited_report_evidence",
      project_id: "project_report_evidence",
      owner_user_id: "user_report_evidence",
      request_id: "request_report_evidence",
      attempt_count: 1,
      normalized_domain: "example.com",
    },
    scan: {
      submitted_url: "https://example.com/",
      beta_revision_fingerprint: "053180f4bdc70857",
      pages_found: 2,
      pages_crawled: 1,
    },
    review: {
      scan_status: "limited",
      health_score: 0,
      health_grade: "",
      limitation: "One redirect destination could not be fully verified.",
      coverage_state: "insufficient",
      coverage_reasons: ["access_limited"],
      coverage_authority_version: "coverage_test_v1",
      recommendations: [finding()],
    },
    now: NOW,
  });

  assert.deepEqual(snapshot.recommendations[0].raw_finding.redirect_fetch_evidence, redirectEvidence);
  const proof = await createLimitedResultProof(snapshot, SECRET);
  const rows = limitedRowsFromSnapshot(snapshot, { fixListId: "limited_fixlist", proof });
  const rebuilt = buildLimitedResultSnapshot({
    identity: {
      scan_id: snapshot.scan_id,
      project_id: snapshot.project_id,
      owner_user_id: snapshot.owner_user_id,
      request_id: snapshot.request_id,
      attempt_count: snapshot.attempt_count,
      normalized_domain: snapshot.normalized_domain,
    },
    scan: structuredClone(rows.scanRun),
    review: {
      scan_status: rows.scanRun.scan_status,
      health_score: rows.scanRun.health_score,
      health_grade: rows.scanRun.health_grade,
      limitation: rows.scanRun.limitation,
      coverage_state: rows.scanRun.coverage_state,
      coverage_reasons: structuredClone(rows.scanRun.coverage_reasons),
      coverage_authority_version: rows.scanRun.coverage_authority_version,
      recommendations: structuredClone(rows.fixItems),
    },
    now: snapshot.sealed_at,
    version: snapshot.version,
  });

  assert.deepEqual(rebuilt, snapshot);
  assert.equal(await verifyLimitedResultProof(rebuilt, SECRET, proof), true);
});
