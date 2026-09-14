import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  authoritySnapshotFromRows,
  createAuthoritySeal,
  verifyAuthoritySeal,
} from "../../base44/functions/getCustomerScanResultV4/projection.js";

const SECRET = "reader-parity-test-secret";
const NOW = "2026-09-14T17:30:00.000Z";
const V6 = "standard_review_snapshot_hmac_v6_report_evidence";
const REPAIR_CONTRACT = "repair_contract_v2_shadow_calibrated";
const REPAIR_PRIORITY = "repair_priority_v2_technical_severity";

function baseRows({ canonical = false } = {}) {
  const run = {
    id: "scan_preview_reader_parity",
    project_id: "project_preview_reader_parity",
    normalized_domain: "example.com",
    website_url: "https://example.com/",
    status: "complete",
    authority_seal_version: V6,
    authority_sealed_at: NOW,
    beta_revision_fingerprint: "fingerprint_preview_reader_parity",
    release_gate_eligible: true,
    score_is_provisional: false,
    evidence_quality_blocking: false,
  };
  const fixList = {
    id: "fixlist_preview_reader_parity",
    scan_run_id: run.id,
    project_id: run.project_id,
    website_url: run.website_url,
    ...(canonical ? {
      repair_contract_version: REPAIR_CONTRACT,
      repair_snapshot_contract_version: REPAIR_CONTRACT,
      repair_snapshot_contract_complete: true,
      repair_priority_model_version: REPAIR_PRIORITY,
    } : {}),
  };
  const fixItems = [{
    id: "row_preview_reader_parity",
    fix_list_id: fixList.id,
    scan_run_id: run.id,
    project_id: run.project_id,
    fix_id: "fix_preview_reader_parity",
    rule: "missing_meta_description",
    issue_title: "Missing meta description",
    priority: "high",
    user_status: "open",
    raw_finding: {},
    ...(canonical ? {
      repair_contract_version: REPAIR_CONTRACT,
      repair_snapshot_contract_version: REPAIR_CONTRACT,
      repair_snapshot_contract_complete: true,
      repair_priority_model_version: REPAIR_PRIORITY,
      canonical_action_rank: 1,
    } : {}),
  }];
  return { run, fixList, fixItems };
}

test("customer authority verification ignores mutable user_status drift after sealing", async () => {
  const { run, fixList, fixItems } = baseRows();
  const sealed = authoritySnapshotFromRows({ run, fixList, fixItems, userId: "user_preview" });
  const proof = await createAuthoritySeal(sealed, SECRET);

  const mutatedRows = structuredClone(fixItems);
  mutatedRows[0].user_status = "done";
  mutatedRows[0].completed_at = "2026-09-14T18:00:00.000Z";
  mutatedRows[0].completed_by_user_id = "user_preview";

  const rebuilt = authoritySnapshotFromRows({
    run,
    fixList,
    fixItems: mutatedRows,
    userId: "user_preview",
  });

  assert.equal(rebuilt.recommendations[0].user_status, "open");
  assert.equal(await verifyAuthoritySeal(rebuilt, SECRET, proof), true);
});

test("customer authority reconstruction accepts canonical repair evidence groups from the top-level row", () => {
  const { run, fixList, fixItems } = baseRows({ canonical: true });
  const groups = [{
    fix_id: "child_fr",
    family: "category_listing",
    locale: "fr",
    representative_url: "https://example.com/fr/category/a",
    affected_urls: ["https://example.com/fr/category/a"],
    count: 1,
    priority: "high",
    action_priority: "important",
    evidence_class: "confirmed_problem",
    evidence_status: "confirmed",
    verification_state: "verified",
    repair_verification_state: "open",
  }];
  fixItems[0].repair_evidence_groups = groups;

  const rebuilt = authoritySnapshotFromRows({
    run,
    fixList,
    fixItems,
    userId: "user_preview",
  });

  assert.deepEqual(rebuilt.recommendations[0].raw_finding.repair_evidence_groups, groups);
});

test("authority verification failure logs bounded release identity without logging proofs or secrets", () => {
  const source = readFileSync("base44/functions/getCustomerScanResultV4/entry.ts", "utf8");

  assert.match(source, /getCustomerScanResult authority verification failed/);
  assert.match(source, /scan_id:\s*cleanId\(run\.id\)/);
  assert.match(source, /build_id:\s*FUNCTION_BUILD_ID/);
  assert.match(source, /runtime_activation_id:\s*BASE44_RUNTIME_ACTIVATION_ID/);
  assert.match(source, /authority_seal_version:\s*cleanText\(run\.authority_seal_version, 160\)/);
  assert.match(source, /release_fingerprint:\s*runReleaseFingerprint/);
  assert.match(source, /fix_item_count:\s*fixItems\.length/);
  assert.doesNotMatch(source, /authority verification failed[\\s\\S]{0,800}(proof|secret):/);
});
