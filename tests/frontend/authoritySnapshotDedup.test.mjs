import assert from "node:assert/strict";
import test from "node:test";

import {
  buildAuthoritySnapshot,
  MAX_AUTHORITY_FIXES,
} from "../../base44/functions/persistDurableScanAuthority/authoritySnapshot.js";
import { authorityRowsFromSnapshot } from "../../base44/functions/persistDurableScanAuthority/authorityRows.js";
import {
  createAuthoritySeal,
  verifyAuthoritySeal,
} from "../../base44/functions/persistDurableScanAuthority/authoritySeal.js";
import { authoritySnapshotFromRows } from "../../base44/functions/grokChat/authoritySnapshot.js";

const NOW = "2026-08-14T18:00:00.000Z";

function finding({
  fixId,
  rule,
  pageScope = "page",
  family,
  pages,
  priority = "medium",
  title,
}) {
  return {
    fix_id: fixId,
    rule,
    category: rule.startsWith("redirect_") ? "indexability" : "canonical",
    issue_title: title || `Resolve ${rule}`,
    plain_english_explanation: `Confirmed ${rule} evidence.`,
    why_it_matters: `Repeated ${rule} evidence creates avoidable crawl work.`,
    recommended_value: `Resolve ${rule} once for the affected template.`,
    simple_next_step: `Verify ${rule} after the change.`,
    page_scope: pageScope,
    page_template_family: family,
    page_url: pageScope === "page" ? pages[0] : "",
    affected_pages: pages,
    evidence_status: "confirmed",
    verification_state: "verified",
    confidence_score: 94,
    priority,
    difficulty: "developer",
    who_can_do_this: "your_web_person",
    requires_developer: true,
    what_to_do_steps: ["Update the shared rule.", "Verify every affected URL."],
  };
}

function snapshotFor(recommendations) {
  return buildAuthoritySnapshot({
    scan: {
      submitted_url: "https://www.ikessandwich.com/",
      scanner_version: "python_scanner_v3_bounded_request",
      scanner_build_revision: "authenticated_health_probe_v1",
      advanced_scan_backend: "python_scanner_api",
      deno_fallback_used: false,
      beta_revision_fingerprint: "03dbfa67f4b708cf",
      metadata_evidence_version: "metadata_v1",
      title_evidence_version: "title_v1",
      pages_found: 163,
      pages_crawled: 150,
    },
    review: {
      archetype_classifier_version: "archetype_classifier_v9_local_business_hospitality",
      review_version: "python_review_v2_structural_marketplace",
      review_evidence_calibration_version: "review_evidence_calibration_v6_health_score_v2",
      ai_review_backend: "python_review_api",
      python_review_fallback_used: false,
      release_gate_eligible: true,
      score_is_provisional: false,
      evidence_quality_blocking: false,
      beta_revision_fingerprint: "03dbfa67f4b708cf",
      metadata_evidence_version: "metadata_v1",
      title_evidence_version: "title_v1",
      scan_status: "complete",
      health_score: 56,
      health_grade: "Needs work",
      recommendations,
    },
    identity: {
      scan_id: "scan_ikes",
      project_id: "project_ikes",
      normalized_domain: "www.ikessandwich.com",
    },
    userId: "user_ikes",
    now: NOW,
  });
}

function ikesDuplicateFixture() {
  const locationPages = Array.from(
    { length: 105 },
    (_, index) => `/locations/location-${String(index + 1).padStart(3, "0")}`,
  );
  const recommendations = [
    finding({
      fixId: "canonical-family",
      rule: "canonical_missing",
      pageScope: "family",
      family: "location_landing",
      pages: ["/locations/location-001", "/locations/location-002"],
    }),
    finding({
      fixId: "noindex-family",
      rule: "redirect_destination_noindex",
      pageScope: "family",
      family: "location_landing",
      pages: locationPages,
      priority: "high",
    }),
    ...locationPages.slice(0, 30).map((page, index) => finding({
      fixId: `noindex-page-${String(index + 1).padStart(2, "0")}`,
      rule: "redirect_destination_noindex",
      family: "location_landing",
      pages: [page],
      priority: "high",
    })),
    finding({
      fixId: "chain-family",
      rule: "redirect_chain",
      pageScope: "family",
      family: "location_landing",
      pages: ["/locations/location-001", "/locations/location-002"],
    }),
    finding({
      fixId: "chain-page-1",
      rule: "redirect_chain",
      family: "location_landing",
      pages: ["https://ikessandwich.com/locations/location-001/"],
    }),
    finding({
      fixId: "chain-page-2",
      rule: "redirect_chain",
      family: "location_landing",
      pages: ["/locations/location-002/"],
    }),
    finding({
      fixId: "chain-contact-outlier",
      rule: "redirect_chain",
      family: "contact",
      pages: ["/contact"],
    }),
  ];
  assert.equal(recommendations.length, 36);
  return recommendations;
}

test("authority snapshot collapses the Ike-style 36-row overlap to four distinct actions", () => {
  const snapshot = snapshotFor(ikesDuplicateFixture());

  assert.deepEqual(
    snapshot.recommendations.map((fix) => fix.fix_id),
    ["canonical-family", "chain-contact-outlier", "chain-family", "noindex-family"],
  );
  assert.equal(snapshot.fix_list.total_fixes, 4);
  assert.equal(snapshot.fix_list.critical_count, 0);
  assert.equal(snapshot.fix_list.high_count, 1);
  assert.equal(snapshot.fix_list.medium_count, 3);
  assert.equal(snapshot.fix_list.low_count, 0);
  assert.deepEqual(snapshot.fix_list.top_action_fix_ids, [
    "canonical-family",
    "chain-contact-outlier",
    "chain-family",
  ]);
});

test("coverage suppression keeps uncovered and materially distinct page evidence", () => {
  const snapshot = snapshotFor([
    finding({
      fixId: "chain-family",
      rule: "redirect_chain",
      pageScope: "family",
      family: "location_landing",
      pages: ["/locations/a", "/locations/b"],
    }),
    finding({
      fixId: "covered-chain-page",
      rule: "redirect_chain",
      family: "location_landing",
      pages: ["/locations/a"],
    }),
    finding({
      fixId: "uncovered-chain-page",
      rule: "redirect_chain",
      family: "location_landing",
      pages: ["/locations/c"],
    }),
    finding({
      fixId: "distinct-rule-same-page",
      rule: "redirect_destination_failed",
      family: "location_landing",
      pages: ["/locations/a"],
    }),
    finding({
      fixId: "distinct-family-same-page",
      rule: "redirect_chain",
      family: "contact",
      pages: ["/locations/a"],
    }),
  ]);

  assert.deepEqual(snapshot.recommendations.map((fix) => fix.fix_id), [
    "chain-family",
    "distinct-family-same-page",
    "distinct-rule-same-page",
    "uncovered-chain-page",
  ]);
});

test("deduplicated recommendations survive persisted-row proof reconstruction", async () => {
  const snapshot = snapshotFor(ikesDuplicateFixture());
  const secret = "authority-dedup-test-secret-that-is-never-deployed";
  const proof = await createAuthoritySeal(snapshot, secret);
  const rows = authorityRowsFromSnapshot(snapshot, {
    fixListId: "fixlist_ikes",
    ownerUserId: "user_ikes",
    proof,
  });

  assert.equal(rows.fixItems.length, snapshot.fix_list.total_fixes);
  const reconstructed = authoritySnapshotFromRows({
    scan: { id: "scan_ikes", project_id: "project_ikes", ...rows.scanRun },
    fixList: { id: "fixlist_ikes", ...rows.fixList },
    fixItems: [...rows.fixItems].reverse(),
    userId: "user_ikes",
  });
  assert.deepEqual(reconstructed, snapshot);
  assert.equal(await verifyAuthoritySeal(reconstructed, secret, proof), true);
});

test("authority dedup preserves the existing first-100 input cap", () => {
  const recommendations = Array.from({ length: MAX_AUTHORITY_FIXES + 1 }, (_, index) => finding({
    fixId: `fix-${String(index + 1).padStart(3, "0")}`,
    rule: "missing_h1",
    family: "standard",
    pages: [`/page-${index + 1}`],
  }));
  const snapshot = snapshotFor(recommendations);

  assert.equal(snapshot.recommendations.length, MAX_AUTHORITY_FIXES);
  assert.equal(snapshot.recommendations.some((fix) => fix.fix_id === "fix-101"), false);
});
