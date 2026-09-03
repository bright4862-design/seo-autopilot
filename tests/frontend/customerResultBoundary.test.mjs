import { RELEASE_FINGERPRINT } from "../../src/lib/generatedReleaseContract.js";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { buildAuthoritySnapshot } from "../../base44/functions/persistDurableScanAuthority/authoritySnapshot.js";
import { authorityRowsFromSnapshot } from "../../base44/functions/persistDurableScanAuthority/authorityRows.js";
import {
  authoritySnapshotFromRows,
  buildCustomerProjection,
  createAuthoritySeal,
  evaluatePaidAccess,
  verifyAuthoritySeal,
} from "../../base44/functions/getCustomerScanResult/projection.js";

const APP_ID = "6a498732ec779dfaaeab0e53";
const PLAN_ID = "standard150_lifetime";
const USER = { id: "user_1", email: "owner@example.com" };

function paidAccess(overrides = {}) {
  return {
    id: "access_1",
    owner_user_id: USER.id,
    user_email: USER.email,
    access_status: "active",
    has_full_access: true,
    plan_id: PLAN_ID,
    app_id: APP_ID,
    grant_source: "stripe_checkout",
    stripe_checkout_session_id: "cs_paid_1",
    paid_at: "2026-08-14T18:00:00.000Z",
    ...overrides,
  };
}

function sealedRows() {
  const snapshot = buildAuthoritySnapshot({
    scan: {
      scanner_version: "python_scanner_v3_bounded_request",
      scanner_build_revision: "authenticated_health_probe_v1",
      scanner_wrapper_version: "runStandard150Scan_v1_python_required",
      advanced_scan_backend: "python_scanner_api",
      deno_fallback_used: false,
      beta_revision_fingerprint: RELEASE_FINGERPRINT,
      metadata_evidence_version: "metadata_v1",
      title_evidence_version: "title_v1",
      website_url: "https://example.com/",
      pages_found: 12,
      pages_crawled: 10,
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
      beta_revision_fingerprint: RELEASE_FINGERPRINT,
      metadata_evidence_version: "metadata_v1",
      title_evidence_version: "title_v1",
      scan_status: "complete",
      health_score: 84,
      health_grade: "Good",
      customer_summary: "A sealed customer summary.",
      recommendations: [{
        fix_id: "fix_1",
        rule: "canonical_missing",
        issue_title: "Add a canonical",
        plain_english_explanation: "This page is missing its canonical tag.",
        affected_pages: ["https://example.com/a"],
        priority: "high",
      }],
    },
    identity: {
      scan_id: "scan_1",
      project_id: "project_1",
      normalized_domain: "example.com",
    },
    userId: USER.id,
    now: "2026-08-14T18:05:00.000Z",
  });
  return { snapshot };
}

test("paid access requires one exact active owner-bound grant", () => {
  assert.equal(evaluatePaidAccess({ rows: [paidAccess()], user: USER }).ok, true);
  assert.equal(evaluatePaidAccess({ rows: [], user: USER }).ok, false);
  assert.equal(evaluatePaidAccess({ rows: [paidAccess(), paidAccess({ id: "access_2" })], user: USER }).ok, false);
  assert.equal(evaluatePaidAccess({ rows: [paidAccess({ owner_user_id: "other" })], user: USER }).ok, false);
  assert.equal(evaluatePaidAccess({ rows: [paidAccess({ access_status: "pending" })], user: USER }).ok, false);
});

test("the result projection verifies the exact persisted authority snapshot", async () => {
  const { snapshot } = sealedRows();
  const secret = "unit-test-result-boundary-secret";
  const proof = await createAuthoritySeal(snapshot, secret);
  const rows = authorityRowsFromSnapshot(snapshot, {
    fixListId: "fixlist_1",
    ownerUserId: USER.id,
    proof,
  });
  const run = { id: "scan_1", project_id: "project_1", ...rows.scanRun };
  const fixList = { id: "fixlist_1", ...rows.fixList };
  const fixItems = rows.fixItems.map((item, index) => ({ id: `row_${index + 1}`, ...item }));
  const reconstructed = authoritySnapshotFromRows({ run, fixList, fixItems, userId: USER.id });

  assert.deepEqual(reconstructed, snapshot);
  assert.equal(await verifyAuthoritySeal(reconstructed, secret, proof), true);

  const projection = buildCustomerProjection({
    run,
    fixList,
    fixItems,
    fullAccess: true,
    authorityVerified: true,
  });
  assert.equal(projection.authority_verified, true);
  assert.equal(projection.access, "full");
  assert.equal(projection.fixItems.length, 1);
  assert.equal(projection.fixItems[0].issue_title, "Add a canonical");
  assert.equal("authority_proof" in projection.run, false);
  assert.equal("owner_user_id" in projection.fixItems[0], false);

  const tampered = authoritySnapshotFromRows({
    run,
    fixList,
    fixItems: [{ ...fixItems[0], issue_title: "Tampered" }],
    userId: USER.id,
  });
  assert.equal(await verifyAuthoritySeal(tampered, secret, proof), false);
});

test("locked and non-authoritative projections never contain paid FixItems", () => {
  const { snapshot } = sealedRows();
  const rows = authorityRowsFromSnapshot(snapshot, {
    fixListId: "fixlist_1",
    ownerUserId: USER.id,
    proof: "a".repeat(64),
  });
  const run = { id: "scan_1", project_id: "project_1", ...rows.scanRun };
  const fixList = { id: "fixlist_1", ...rows.fixList };
  const fixItems = rows.fixItems.map((item) => ({ id: "row_1", ...item }));

  const locked = buildCustomerProjection({ run, fixList, fixItems, fullAccess: false, authorityVerified: true });
  assert.equal(locked.access, "locked");
  assert.equal(locked.authority_verified, false);
  assert.equal(locked.fixList, null);
  assert.deepEqual(locked.fixItems, []);

  const unverified = buildCustomerProjection({ run, fixList, fixItems, fullAccess: true, authorityVerified: false });
  assert.equal(unverified.authority_verified, false);
  assert.equal(unverified.fixList, null);
  assert.deepEqual(unverified.fixItems, []);
});

test("customer results cross one server projection and authority rows are admin-only", () => {
  const entry = readFileSync("base44/functions/getCustomerScanResult/entry.ts", "utf8");
  const scanRuns = readFileSync("src/lib/scanRuns.js", "utf8");
  const fixListSchema = JSON.parse(readFileSync("base44/entities/FixList.jsonc", "utf8"));
  const fixItemSchema = JSON.parse(readFileSync("base44/entities/FixItem.jsonc", "utf8"));

  assert.match(entry, /await base44\.auth\.me\(\)/);
  assert.match(entry, /const serviceEntities = base44\.asServiceRole\.entities/);
  assert.match(entry, /serviceEntities\.Access/);
  assert.match(entry, /serviceEntities\.FixList/);
  assert.match(entry, /serviceEntities\.FixItem/);
  assert.match(entry, /verifyAuthoritySeal\(snapshot, secret, proof\)/);
  assert.ok(entry.indexOf("evaluatePaidAccess") < entry.indexOf("serviceEntities.FixItem"));

  const reopen = scanRuns.match(/export async function getScanRunWithFixList[\s\S]*?\n\}/)?.[0] || "";
  assert.match(reopen, /base44\.functions\.invoke\("getCustomerScanResultV2"/);
  assert.doesNotMatch(reopen, /entities\.(?:FixList|FixItem)/);

  for (const schema of [fixListSchema, fixItemSchema]) {
    for (const operation of ["create", "read", "update", "delete"]) {
      assert.equal(schema.rls[operation].user_condition.role, "admin", `${schema.name}.${operation}`);
    }
  }
});

test("saved results use the same exact owner-bound manual grant rule as scan admission", () => {
  const manual = paidAccess({
    grant_source: "manual_grant",
    paid_at: "",
    stripe_checkout_session_id: "",
    granted_at: "2026-08-15T17:00:00.000Z",
  });
  assert.equal(evaluatePaidAccess({ rows: [manual], user: USER }).ok, true);
  assert.equal(evaluatePaidAccess({ rows: [{ ...manual, owner_user_id: "" }], user: USER }).ok, false);
  assert.equal(evaluatePaidAccess({ rows: [{ ...manual, owner_user_id: "other" }], user: USER }).ok, false);
  assert.equal(evaluatePaidAccess({ rows: [{ ...manual, user_email: "other@example.com" }], user: USER }).ok, false);
});

test("customer result verification preserves exact signing-key bytes", async () => {
  const { snapshot } = sealedRows();
  const secret = "unit-test-result-boundary-secret\n";
  const proof = await createAuthoritySeal(snapshot, secret);
  assert.equal(await verifyAuthoritySeal(snapshot, secret, proof), true);
  assert.equal(await verifyAuthoritySeal(snapshot, secret.trim(), proof), false);

  const entry = readFileSync("base44/functions/getCustomerScanResult/entry.ts", "utf8");
  assert.match(entry, /secrets\.get\("SCAN_EVIDENCE_SIGNING_KEY"\)/);
  assert.match(entry, /String\(mutableSigningKey\(\) \|\| ""\)/);
  assert.doesNotMatch(entry, /cleanText\(mutableSigningKey\(\)/);
});


test("canonical v2 authority survives persistence reconstruction and projects ranked rows", async () => {
  const v2 = "repair_contract_v2_shadow_calibrated";
  const priorityModel = "repair_priority_v2_technical_severity";
  const canonicalRepairs = [
    {
      fix_id: "fix-first",
      rule: "internal_link_redirect",
      category: "internal_link",
      issue_title: "Update homepage links to use their final URLs",
      affected_pages: ["https://example.com/"],
      priority: "high",
      repair_contract_version: v2,
      repair_priority_model_version: priorityModel,
      base_severity: "high",
      technical_severity_source: "rule_taxonomy",
      evidence_class: "confirmed_problem",
      action_priority: "fix_first",
      action_priority_score: 4300,
      priority_reason: "1 important checked page is affected.",
      canonical_action_rank: 1,
      repair_identity_version: "repair_identity_v2_technical",
      repair_fingerprint: "abc123abc123abc123abc123",
      repair_identity_state: "stable",
      repair_identity_stable: true,
      repair_surface: "shared_navigation",
      remediation_family: "replace_redirecting_internal_link",
      priority_context: { affected_checked: 1, checked_eligible: 1, shared_repair_confirmed: false },
    },
    {
      fix_id: "improve-second",
      rule: "missing_meta_description",
      category: "meta_description",
      issue_title: "Add a search description to this page",
      affected_pages: ["https://example.com/a"],
      priority: "medium",
      repair_contract_version: v2,
      repair_priority_model_version: priorityModel,
      base_severity: "medium",
      technical_severity_source: "rule_taxonomy",
      evidence_class: "improvement",
      action_priority: "improve",
      action_priority_score: 2300,
      priority_reason: "1 checked page is affected.",
      canonical_action_rank: 2,
      repair_identity_version: "repair_identity_v2_technical",
      repair_fingerprint: "def456def456def456def456",
      repair_identity_state: "stable",
      repair_identity_stable: true,
      repair_surface: "cms_field",
      remediation_family: "update_meta_description",
      priority_context: { affected_checked: 1, checked_eligible: 1, shared_repair_confirmed: false },
    },
  ];
  const snapshot = buildAuthoritySnapshot({
    scan: {
      scanner_version: "python_scanner_v3_bounded_request",
      scanner_build_revision: "authenticated_health_probe_v1",
      scanner_wrapper_version: "runStandard150Scan_v1_python_required",
      advanced_scan_backend: "python_scanner_api",
      deno_fallback_used: false,
      beta_revision_fingerprint: RELEASE_FINGERPRINT,
      metadata_evidence_version: "metadata_v1",
      title_evidence_version: "title_v1",
      website_url: "https://example.com/",
      pages_found: 12,
      pages_crawled: 10,
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
      beta_revision_fingerprint: RELEASE_FINGERPRINT,
      metadata_evidence_version: "metadata_v1",
      title_evidence_version: "title_v1",
      scan_status: "complete",
      health_score: 72,
      health_grade: "Needs attention",
      recommendations: [...canonicalRepairs].reverse(),
      repair_contract_version: v2,
      repair_snapshot_contract_version: v2,
      repair_snapshot_contract_complete: true,
      repair_priority_model_version: priorityModel,
      canonical_action_fix_ids: canonicalRepairs.map((item) => item.fix_id),
      canonical_repairs: canonicalRepairs,
    },
    identity: { scan_id: "scan_v2", project_id: "project_1", normalized_domain: "example.com" },
    userId: USER.id,
    now: "2026-08-20T20:00:00.000Z",
  });

  assert.equal(snapshot.fix_list.repair_snapshot_contract_complete, true);
  assert.deepEqual(snapshot.fix_list.canonical_action_fix_ids, ["fix-first", "improve-second"]);
  assert.deepEqual(snapshot.recommendations.map((item) => item.action_priority), ["fix_first", "improve"]);

  const secret = "unit-test-v2-authority-secret";
  const proof = await createAuthoritySeal(snapshot, secret);
  const rows = authorityRowsFromSnapshot(snapshot, { fixListId: "fixlist_v2", ownerUserId: USER.id, proof });
  const run = { id: "scan_v2", project_id: "project_1", ...rows.scanRun };
  const fixList = { id: "fixlist_v2", ...rows.fixList };
  const fixItems = rows.fixItems.map((item, index) => ({ id: `v2_${index}`, ...item })).reverse();
  const reconstructed = authoritySnapshotFromRows({ run, fixList, fixItems, userId: USER.id });

  assert.deepEqual(reconstructed, snapshot);
  assert.equal(await verifyAuthoritySeal(reconstructed, secret, proof), true);

  const projection = buildCustomerProjection({ run, fixList, fixItems, fullAccess: true, authorityVerified: true });
  assert.deepEqual(projection.fixItems.map((item) => item.action_priority), ["fix_first", "improve"]);
  assert.equal(projection.fixItems[0].repair_snapshot_contract_complete, true);
  assert.equal(projection.fixItems[0].priority_reason, "1 important checked page is affected.");
});
