import test from "node:test";
import assert from "node:assert/strict";
import { collectPublished150Canary } from "../../scripts/collect-published-150-canary.mjs";
import { APP_ID, observeOrdinaryPilotRun, renderOrdinaryOperatorReadback } from "../../scripts/staged_scan_acceptance.mjs";
import { buildCustomerPreviewPayload } from "../../base44/functions/persistDurableScanAuthorityV9/customerPreviewSealStage1Legacy.js";
import { buildCustomerProjection } from "../../base44/functions/getCustomerScanResultV9/projection.js";
import { RELEASE_FINGERPRINT } from "../../base44/functions/getCustomerScanResultV9/generatedReleaseContract.js";

const source = "a".repeat(40);
const fixture = "https://fixlist-staged-fixture-919035207432.europe-west1.run.app/";
const operatorId = "6a498da58ef5cec1f5cd4486";
const observed = Date.now() - 60_000;
const run = {
  id: "scan_fixture_1", project_id: "project_fixture", owner_user_id: "customer_fixture", fix_list_id: "fixlist_fixture",
  request_id: "request_fixture_1", website_url: fixture, scan_mode: "standard_150", page_cap: 150,
  pipeline_mode: "staged", status: "complete", pages_crawled: 150, pages_planned: 150,
  last_committed_batch: 2, attempt_count: 1, beta_revision_fingerprint: RELEASE_FINGERPRINT,
  started_at: new Date(observed).toISOString(), completed_at: new Date(observed + 20_000).toISOString(),
  admission_mode: "acceptance_only", admission_acceptance_source_sha: source,
  admission_cohort_evidence_version: "admission_claim_evidence_v1",
  admission_cohort_evidence_proof: "c".repeat(64), authority_proof: "d".repeat(64),
  advanced_scan_backend: "python_scanner_api", deno_fallback_used: false,
  ai_review_backend: "python_review_api", python_review_fallback_used: false,
};
const provenance = {
  source_sha: source, release_fingerprint: run.beta_revision_fingerprint,
  expires_at: new Date(observed + 120_000).toISOString(),
  ordinary_pilot: { operator_user_id: operatorId, owner_user_id: run.owner_user_id },
  base44_functions: [
    { name: "startStandardScanJobV9", route_name: "startStandardScanJobV9B1111111111111111" },
    { name: "getCustomerScanResultV9", route_name: "getCustomerScanResultV9B2222222222222222" },
  ],
};
const context = {
  operator: { run, observed_at: new Date(observed).toISOString() },
  provenance, complete: true, batches: 3,
};
const launch = { accepted: true, scan_id: run.id, request_id: run.request_id, page_cap: 150,
  scan_mode: "standard_150", pipeline_mode: "staged" };
const fixList = { id: run.fix_list_id, scan_run_id: run.id, project_id: run.project_id, website_url: fixture };
const preview = buildCustomerPreviewPayload({
  run, fixList, fixItems: [], ownerUserId: run.owner_user_id, fullAuthorityProof: run.authority_proof,
});
const projection = buildCustomerProjection({
  signedPreview: true, authorityVerified: true, previewAccess: true,
  run: preview.run, fixList: preview.fixList, fixItems: preview.fixItems,
});
const browser = {
  schema_version: "published_150_browser_readback_v1", source_sha: source,
  owner_user_id: run.owner_user_id, role: "user", launched_by_form: true,
  launch_url: "https://getfixlist.com/onboarding", displayed_page_cap: 150, launch,
  launch_route: provenance.base44_functions[0].route_name,
  result_route: provenance.base44_functions[1].route_name,
  refreshed_during_progress: true, reopened_from_history: true, reopened_after_sign_in: true,
  history_url: `https://getfixlist.com/dashboard?scan_id=${run.id}`,
  history_reopened_at: new Date(observed + 25_000).toISOString(),
  saved_projection: projection, history_projection: projection,
};

test("published 150 readback feeds the receipt verifier for the same preview or full report", () => {
  assert.equal(Object.hasOwn(projection.run, "scan_mode"), false);
  assert.equal(Object.hasOwn(projection.run, "beta_revision_fingerprint"), false);
  const full = buildCustomerProjection({ run, fixList, fixItems: [], authorityVerified: true, fullAccess: true });
  for (const read of [projection, full]) {
    const report = collectPublished150Canary(context, { ...browser, saved_projection: read, history_projection: read });
    assert.equal(report.schema_version, "staged_150_published_canary_v1");
    assert.equal(report.authority_verified, true);
    assert.equal(report.scan_id, run.id);
    assert.equal(report.committed_batch_count, 3);
    assert.equal(report.browser.access, read.access);
    assert.equal(report.acceptance_verified, false);
    assert.equal("saved_projection" in report, false);
  }
});

test("local preview, administrator, wrong route, stale source and unsigned history cannot certify the published path", () => {
  for (const overrides of [
    { launch_url: "http://127.0.0.1:4173/onboarding" },
    { role: "admin" },
    { launch_route: "startStandardScanJobV9B0000000000000000" },
    { source_sha: "f".repeat(40) },
    { launch: { ...launch, page_cap: 500 } },
    { refreshed_during_progress: false },
    { history_url: `https://getfixlist.com/dashboard?scan_id=${run.id}&scan_id=other_scan` },
    { history_projection: { ...projection, authority_verified: false } },
    { history_projection: { ...projection, run: { ...projection.run, scan_mode: "standard_500" } } },
    { history_projection: { ...projection, run: { ...projection.run, beta_revision_fingerprint: "f".repeat(16) } } },
    { history_projection: { ...projection, run: { ...projection.run, completed_at: run.started_at } } },
    { history_projection: { ...projection, fix_list_id: "fixlist_other" } },
    { reopened_after_sign_in: false },
  ]) {
    assert.throws(() => collectPublished150Canary(context, { ...browser, ...overrides }), /published_browser_.*_unverified/);
  }
});

test("ordinary 150 operator readback confirms worker provenance and a single request record", async () => {
  const config = {
    appId: APP_ID, sourceSha: source, provenance, ownerId: run.owner_user_id,
    targetUrl: fixture, projectId: run.project_id, requestId: run.request_id,
    ordinaryScanId: run.id, ordinaryPageCap: 150, maxWait: 30, pollSeconds: 1,
  };
  const account = { id: operatorId, role: "admin", email: "bright4862@gmail.com" };
  const entities = scan => ({ ScanRun: {
    get: async id => { assert.equal(id, scan.id); return scan; },
    filter: async (query, sort, limit) => {
      assert.deepEqual(query, { owner_user_id: scan.owner_user_id, request_id: scan.request_id });
      assert.equal(sort, "-created_date");
      assert.equal(limit, 2);
      return [{ id: scan.id }];
    },
  } });
  const observe = async data => observeOrdinaryPilotRun({ auth: { me: async () => account }, entities: data }, config, () => observed);
  const result = await observe(entities(run));
  assert.equal(result.schema_version, "staged_150_ordinary_operator_readback_v1");
  assert.equal(result.run.canonical_request_count, 1);
  assert.equal(result.run.durable_worker_owned, true);
  assert.match(renderOrdinaryOperatorReadback(config), /FIXLIST_STAGED_150_ORDINARY_OPERATOR=/);
  await assert.rejects(observe(entities({ ...run, deno_fallback_used: true })), /ordinary_operator_worker_evidence_missing/);
  const duplicates = entities(run);
  duplicates.ScanRun.filter = async () => [{ id: run.id }, { id: "duplicate_scan" }];
  await assert.rejects(observe(duplicates), /ordinary_operator_duplicate_request/);
});
