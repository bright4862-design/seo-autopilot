import assert from "node:assert/strict";
import test from "node:test";

import { buildAuthoritySnapshot } from "../../base44/functions/persistDurableScanAuthority/authoritySnapshot.js";
import { authorityRowsFromSnapshot } from "../../base44/functions/persistDurableScanAuthority/authorityRows.js";
import {
  createAuthoritySeal,
  verifyAuthoritySeal,
} from "../../base44/functions/persistDurableScanAuthority/authoritySeal.js";
import { authoritySnapshotFromRows } from "../../base44/functions/grokChat/authoritySnapshot.js";
import {
  REPAIR_CONTRACT_V2,
  REPAIR_PRIORITY_MODEL_V2,
  RULE_EVALUATION_CONTRACT_V1,
  applyRepairContractV2Candidate,
  rehydrateRepairContractV2Candidate,
} from "../../base44/functions/persistDurableScanAuthority/repairContractV2Candidate.js";

const NOW = "2026-08-19T16:20:00.000Z";
const SECRET = "repair-v2-candidate-secret-that-is-never-deployed";

function finding({ fixId, rule, priority = "medium", page = "/" }) {
  return {
    fix_id: fixId,
    rule,
    category: "technical",
    issue_title: `Resolve ${rule}`,
    plain_english_explanation: `Confirmed ${rule} evidence.`,
    why_it_matters: `${rule} matters.`,
    recommended_value: `Resolve ${rule}.`,
    simple_next_step: `Verify ${rule}.`,
    page_scope: "page",
    page_template_family: page === "/" ? "homepage" : "product_page",
    page_url: page,
    affected_pages: [page],
    source_pages: [page],
    evidence_status: "confirmed",
    verification_state: "open",
    confidence_score: 95,
    priority,
    difficulty: "developer",
    who_can_do_this: "your_web_person",
    requires_developer: true,
    what_to_do_steps: ["Make the change.", "Verify the page."],
  };
}

function legacySnapshot() {
  return buildAuthoritySnapshot({
    scan: {
      submitted_url: "https://example.com/",
      scanner_version: "python_scanner_v3_bounded_request",
      scanner_build_revision: "authenticated_health_probe_v1",
      advanced_scan_backend: "python_scanner_api",
      deno_fallback_used: false,
      beta_revision_fingerprint: "03dbfa67f4b708cf",
      metadata_evidence_version: "metadata_v1",
      title_evidence_version: "title_v1",
      pages_found: 150,
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
      health_score: 63,
      health_grade: "Needs work",
      recommendations: [
        finding({ fixId: "a-home-noindex", rule: "indexability", priority: "high", page: "/" }),
        finding({ fixId: "z-meta-description", rule: "meta_description", priority: "critical", page: "/products/a" }),
      ],
    },
    identity: {
      scan_id: "scan_v2_candidate",
      project_id: "project_v2_candidate",
      normalized_domain: "example.com",
    },
    userId: "user_v2_candidate",
    now: NOW,
  });
}

function v2Contract() {
  return {
    repair_contract_version: REPAIR_CONTRACT_V2,
    repair_priority_model_version: REPAIR_PRIORITY_MODEL_V2,
    repair_identity_version: "repair_identity_v1_conservative",
    repair_verification_version: "repair_verification_v1_comparable_eligible",
    // Deliberately opposite alphabetical fix_id order: customer priority must be
    // persisted separately from deterministic HMAC recommendation serialization.
    canonical_action_fix_ids: ["a-home-noindex", "z-meta-description"],
    repairs: [
      {
        fix_id: "a-home-noindex",
        base_severity: "high",
        evidence_class: "confirmed_problem",
        action_priority: "fix_first",
        action_priority_score: 97,
        priority_reason: "Homepage may be hidden from Google",
        priority_context: {
          affected_checked: 1,
          checked_eligible: 1,
          indexable_affected: 1,
          indexable_checked_eligible: 1,
          important_affected: 1,
        },
        repair_identity_version: "repair_identity_v1_conservative",
        repair_fingerprint: "fp_home_noindex",
        repair_surface: "homepage",
        remediation_family: "indexability",
        shared_repair_confirmed: false,
        rule_definition_version: "indexability_rule_v1",
        comparison_profile_version: "standard150_compare_v1",
        repair_verification_version: "repair_verification_v1_comparable_eligible",
        repair_verification_state: "ready_to_verify",
      },
      {
        fix_id: "z-meta-description",
        base_severity: "low",
        evidence_class: "improvement",
        action_priority: "improve",
        action_priority_score: 31,
        priority_reason: "1 searchable product page checked is affected",
        priority_context: {
          affected_checked: 1,
          checked_eligible: 1,
          indexable_affected: 1,
          indexable_checked_eligible: 1,
        },
        repair_identity_version: "repair_identity_v1_conservative",
        repair_fingerprint: "fp_meta_description",
        repair_surface: "cms_field",
        remediation_family: "meta_description",
        shared_repair_confirmed: false,
        rule_definition_version: "meta_description_rule_v1",
        comparison_profile_version: "standard150_compare_v1",
        repair_verification_version: "repair_verification_v1_comparable_eligible",
        repair_verification_state: "ready_to_verify",
      },
    ],
    rule_evaluation_contract_version: RULE_EVALUATION_CONTRACT_V1,
    rule_evaluations: [
      {
        rule: "canonical",
        rule_definition_version: "canonical_rule_v1",
        evaluated: true,
        applicable: true,
        passed: true,
        eligible_checked_count: 150,
        evaluated_page_count: 150,
        limitation_code: "",
      },
      {
        rule: "schema",
        rule_definition_version: "schema_rule_v1",
        evaluated: false,
        applicable: true,
        passed: false,
        eligible_checked_count: 0,
        evaluated_page_count: 0,
        limitation_code: "evidence_unavailable",
      },
    ],
  };
}

function rowsFor(snapshot, proof) {
  return authorityRowsFromSnapshot(snapshot, {
    fixListId: "fixlist_v2_candidate",
    ownerUserId: "user_v2_candidate",
    proof,
  });
}

function legacyReconstruction(rows) {
  return authoritySnapshotFromRows({
    scan: { id: "scan_v2_candidate", project_id: "project_v2_candidate", ...rows.scanRun },
    fixList: { id: "fixlist_v2_candidate", ...rows.fixList },
    fixItems: [...rows.fixItems].reverse(),
    userId: "user_v2_candidate",
  });
}

test("historical signed snapshot remains byte-for-byte reconstructable with no v2 keys", async () => {
  const snapshot = legacySnapshot();
  const proof = await createAuthoritySeal(snapshot, SECRET);
  const rows = rowsFor(snapshot, proof);
  const reconstructedLegacy = legacyReconstruction(rows);
  const candidateAware = rehydrateRepairContractV2Candidate(reconstructedLegacy, rows.fixList, rows.fixItems);

  assert.deepEqual(reconstructedLegacy, snapshot);
  assert.deepEqual(candidateAware, snapshot);
  assert.equal("repair_contract_version" in candidateAware.fix_list, false);
  assert.equal(await verifyAuthoritySeal(candidateAware, SECRET, proof), true);
});

test("complete v2 snapshot round-trips through existing rows and real HMAC serializer", async () => {
  const snapshot = applyRepairContractV2Candidate(legacySnapshot(), v2Contract());
  const proof = await createAuthoritySeal(snapshot, SECRET);
  const rows = rowsFor(snapshot, proof);

  // Existing reconstruction intentionally returns the historical payload shape.
  // The isolated candidate rehydrator adds v2 keys only when the persisted parent
  // explicitly proves a complete supported v2 snapshot.
  const reconstructed = rehydrateRepairContractV2Candidate(
    legacyReconstruction(rows),
    rows.fixList,
    rows.fixItems,
  );

  assert.deepEqual(reconstructed, snapshot);
  assert.equal(await verifyAuthoritySeal(reconstructed, SECRET, proof), true);
  assert.equal(reconstructed.fix_list.repair_snapshot_contract_complete, true);
  assert.deepEqual(reconstructed.fix_list.canonical_action_fix_ids, [
    "a-home-noindex",
    "z-meta-description",
  ]);
  assert.deepEqual(reconstructed.recommendations.map((fix) => fix.fix_id), [
    "a-home-noindex",
    "z-meta-description",
  ]);
  assert.deepEqual(reconstructed.recommendations.map((fix) => fix.canonical_action_rank), [1, 2]);
  assert.equal(reconstructed.recommendations[0].action_priority, "fix_first");
  assert.equal(reconstructed.recommendations[1].action_priority, "improve");
  assert.equal(reconstructed.fix_list.rule_evaluations[0].passed, true);
  assert.equal(reconstructed.fix_list.rule_evaluations[1].passed, false);
});

test("canonical customer order is independent from deterministic fix-id serialization", () => {
  const legacy = legacySnapshot();
  const contract = v2Contract();
  contract.canonical_action_fix_ids = ["z-meta-description", "a-home-noindex"];
  const snapshot = applyRepairContractV2Candidate(legacy, contract);

  assert.deepEqual(snapshot.recommendations.map((fix) => fix.fix_id), [
    "a-home-noindex",
    "z-meta-description",
  ]);
  assert.deepEqual(snapshot.fix_list.canonical_action_fix_ids, [
    "z-meta-description",
    "a-home-noindex",
  ]);
  assert.deepEqual(snapshot.recommendations.map((fix) => [fix.fix_id, fix.canonical_action_rank]), [
    ["a-home-noindex", 2],
    ["z-meta-description", 1],
  ]);
  assert.deepEqual(snapshot.fix_list.top_action_fix_ids, legacy.fix_list.top_action_fix_ids);
});

test("partial v2 parent state fails closed rather than falling back to legacy", () => {
  const snapshot = legacySnapshot();
  const rows = rowsFor(snapshot, "0".repeat(64));
  rows.fixList.repair_contract_version = REPAIR_CONTRACT_V2;

  assert.throws(
    () => rehydrateRepairContractV2Candidate(legacyReconstruction(rows), rows.fixList, rows.fixItems),
    /repair_contract_v2_row_snapshot_contract/,
  );
});

test("missing repair annotation prevents a snapshot from being marked complete", () => {
  const contract = v2Contract();
  contract.repairs = contract.repairs.slice(0, 1);
  assert.throws(
    () => applyRepairContractV2Candidate(legacySnapshot(), contract),
    /repair_contract_v2_repair_annotations:count/,
  );
});

test("tampering with persisted v2 repair evidence changes the signed payload", async () => {
  const snapshot = applyRepairContractV2Candidate(legacySnapshot(), v2Contract());
  const proof = await createAuthoritySeal(snapshot, SECRET);
  const rows = rowsFor(snapshot, proof);
  rows.fixItems[0].priority_reason = "Tampered customer reason";

  const reconstructed = rehydrateRepairContractV2Candidate(
    legacyReconstruction(rows),
    rows.fixList,
    rows.fixItems,
  );
  assert.equal(await verifyAuthoritySeal(reconstructed, SECRET, proof), false);
});
