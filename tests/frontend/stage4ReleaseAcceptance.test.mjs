import assert from "node:assert/strict";
import test from "node:test";

import {
  EXPECTED_SCANNER_FUNCTIONS,
  STAGE4_RELEASE_RECORD_VERSION,
  evaluateStage4ReleaseAcceptance,
} from "../../scripts/stage4ReleaseAcceptance.mjs";

const SHA = "a".repeat(40);
const PROOF = "b".repeat(64);
const DIGEST = `sha256:${"c".repeat(64)}`;
const RECEIPT = "receipt:verified-stage4-evidence";

function validRecord(overrides = {}) {
  const record = {
    version: STAGE4_RELEASE_RECORD_VERSION,
    provenance: "live_authorized",
    observed_at: "2026-09-19T20:00:00Z",
    source: { merged_sha: SHA },
    review: { status: "approved", evidence_reference: RECEIPT },
    ci: {
      sha: SHA,
      conclusion: "success",
      run_id: 123456,
      run_url: "https://github.com/bright4862-design/seo-autopilot/actions/runs/123456",
    },
    schema: { named_schema_parity: true, evidence_reference: RECEIPT },
    deployment: {
      site: {
        verified: true,
        source_sha: SHA,
        hosts_verified: ["getfixlist.com", "getfixlist.base44.app"],
        verification_reference: RECEIPT,
      },
      functions: EXPECTED_SCANNER_FUNCTIONS.map((name, index) => ({
        name,
        verified: true,
        source_sha: SHA,
        runtime_build_id: `build-${index + 1}`,
        verification_reference: `${RECEIPT}:${name}`,
      })),
      worker: {
        verified: true,
        source_sha: SHA,
        image_digest: DIGEST,
        traffic_percent: 100,
        revision: "fixlist-standard150-worker-00123-abc",
        rollback_target: "fixlist-standard150-worker-00122-old",
        rollback_ready: true,
        private_scan_job_unauth_status: 403,
        promotion_reference: `${RECEIPT}:promotion`,
        rollback_reference: `${RECEIPT}:rollback`,
      },
    },
    acceptance: {
      cohort: {
        mode: "acceptance_only",
        total_claim_budget: 1,
        public_claims_closed: true,
        activation_reference: `${RECEIPT}:cohort`,
      },
      scan: {
        scan_id: "scan-acceptance-1",
        mode: "standard_150",
        submission_surface: "published_customer_ui",
        observed_at: "2026-09-19T20:10:00Z",
        evidence_reference: `${RECEIPT}:scan`,
        status: "complete",
        pages_crawled: 150,
        release_gate_eligible: true,
        authority_proof: PROOF,
        fix_list_id: "fix-list-1",
        source_sha: SHA,
        normalized_domain: "example.com",
      },
      reload: {
        observed_at: "2026-09-19T20:11:00Z",
        evidence_reference: `${RECEIPT}:reload`,
        requested_scan_id: "scan-acceptance-1",
        loaded_scan_id: "scan-acceptance-1",
        fix_list_id: "fix-list-1",
        authority_proof: PROOF,
      },
      history: {
        observed_at: "2026-09-19T20:12:00Z",
        evidence_reference: `${RECEIPT}:history`,
        owner_scoped: true,
        scan_ids: ["scan-acceptance-1"],
      },
      rescan: {
        observed_at: "2026-09-19T20:20:00Z",
        evidence_reference: `${RECEIPT}:rescan`,
        scan_id: "scan-acceptance-2",
        parent_scan_id: "scan-acceptance-1",
        normalized_domain: "example.com",
        status: "complete",
        comparison: "improved",
        comparison_evidence_verified: true,
      },
      closed_and_drained: true,
      close_drain_reference: `${RECEIPT}:close-drain`,
    },
    public_release: {
      opened_after_acceptance: true,
      claims_open: true,
      opening_reference: `${RECEIPT}:public-open`,
    },
  };
  return { ...record, ...overrides };
}

test("test fixtures can exercise the complete shape but can never establish live acceptance", () => {
  const result = evaluateStage4ReleaseAcceptance(validRecord({ test_fixture: true }));
  assert.equal(result.status, "not_assessed");
  assert.equal(result.pass, false);
  assert.ok(result.blockers.some((value) => value.includes("test fixture")));
});

test("all six scanner runtime identities are explicit release gates", () => {
  assert.equal(EXPECTED_SCANNER_FUNCTIONS.length, 6);
  const record = validRecord();
  record.deployment.functions = record.deployment.functions.slice(0, 5);
  const result = evaluateStage4ReleaseAcceptance(record);
  assert.equal(result.status, "failed");
  assert.ok(result.failures.some((value) => value.includes("missing runtime identity")));
});

test("site, CI, function and worker source must all match the exact merged SHA", () => {
  const record = validRecord();
  record.ci.sha = "d".repeat(40);
  record.deployment.site.source_sha = "e".repeat(40);
  record.deployment.functions[0].source_sha = "f".repeat(40);
  record.deployment.worker.source_sha = "1".repeat(40);
  const result = evaluateStage4ReleaseAcceptance(record);
  assert.equal(result.pass, false);
  assert.ok(result.failures.some((value) => value.includes("CI SHA")));
  assert.ok(result.failures.some((value) => value.includes("Base44 site source")));
  assert.ok(result.failures.some((value) => value.includes(`${EXPECTED_SCANNER_FUNCTIONS[0]} source`)));
  assert.ok(result.failures.some((value) => value.includes("worker source")));
});

test("Standard 150 page cap and persisted authority are mandatory", () => {
  const record = validRecord();
  record.acceptance.scan.pages_crawled = 151;
  record.acceptance.scan.authority_proof = "not-a-proof";
  record.acceptance.scan.fix_list_id = "";
  const result = evaluateStage4ReleaseAcceptance(record);
  assert.equal(result.pass, false);
  assert.ok(result.failures.some((value) => value.includes("Standard 150 bounds")));
  assert.ok(result.failures.some((value) => value.includes("authority proof")));
  assert.ok(result.failures.some((value) => value.includes("FixList id")));
});

test("exact scan reload and owner-scoped history cannot drift to a different result", () => {
  const record = validRecord();
  record.acceptance.reload.loaded_scan_id = "scan-other";
  record.acceptance.reload.authority_proof = "d".repeat(64);
  record.acceptance.history.scan_ids = ["scan-other"];
  const result = evaluateStage4ReleaseAcceptance(record);
  assert.equal(result.pass, false);
  assert.ok(result.failures.some((value) => value.includes("exact scan_id reload")));
  assert.ok(result.failures.some((value) => value.includes("authority proof changed")));
  assert.ok(result.failures.some((value) => value.includes("history does not include")));
});

test("rescan comparison and rollback readiness are explicit rather than inferred", () => {
  const record = validRecord();
  record.deployment.worker.rollback_ready = false;
  record.acceptance.rescan.comparison = "";
  record.acceptance.rescan.comparison_evidence_verified = false;
  const result = evaluateStage4ReleaseAcceptance(record);
  assert.equal(result.pass, false);
  assert.ok(result.failures.some((value) => value.includes("rollback path")));
  assert.ok(result.failures.some((value) => value.includes("rescan comparison result")));
  assert.ok(result.failures.some((value) => value.includes("comparison evidence")));
});

test("claimed live state without traceable receipts fails closed", () => {
  const record = validRecord();
  record.review.evidence_reference = "";
  record.ci.run_id = 0;
  record.deployment.site.verification_reference = "";
  record.deployment.worker.promotion_reference = "";
  record.acceptance.scan.evidence_reference = "";
  record.acceptance.reload.evidence_reference = "";
  record.acceptance.close_drain_reference = "";
  record.public_release.opening_reference = "";
  const result = evaluateStage4ReleaseAcceptance(record);
  assert.equal(result.status, "failed");
  for (const fragment of [
    "review evidence reference",
    "CI run id",
    "site verification receipt",
    "worker promotion receipt",
    "scan evidence reference",
    "reload evidence reference",
    "close/drain receipt",
    "public opening receipt",
  ]) assert.ok(result.failures.some((value) => value.includes(fragment)), fragment);
});
