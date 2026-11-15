import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import test from "node:test";

import { buildCustomerProjection, buildScanHistoryProjection } from "../../base44/functions/getCustomerScanResultV9/projection.js";
import { buildLimitedResultSnapshot, verifyLimitedResultProof } from "../../base44/functions/getCustomerScanResultV9/limitedResultIntegrity.js";
import * as writer from "../../base44/functions/persistLimitedScanResultV9/limitedResultIntegrity.js";

const key = "v9-limited-coverage-fixture-key";
const coverage = {
  coverage_state: "access_limited",
  coverage_reasons: ["rate_limited", "a".repeat(200)],
  coverage_authority_version: "coverage_authority_v1_shared_decision",
};

async function limitedRun() {
  const identity = {
    scan_id: "scan_limited", project_id: "project_limited", owner_user_id: "owner_limited",
    request_id: "request_limited", attempt_count: 1, normalized_domain: "example.test",
  };
  const scan = {
    scan_mode: "standard_500", pipeline_mode: "staged", page_cap: 500,
    website_url: "https://example.test/", pages_crawled: 50, pages_found: 600,
    scan_coverage: {
      urls_attempted: 50, usable_html_pages: 50, verified_http_failures: 0,
      access_unverified_pages: 0, non_html_resources: 0, unique_retained_destinations: 50,
    },
  };
  const now = "2026-11-14T12:00:00Z";
  const snapshot = writer.buildLimitedResultSnapshot({
    identity, scan, now,
    review: { ...coverage, scan_status: "limited", score_is_provisional: true, release_gate_eligible: false },
  });
  const proof = await writer.createLimitedResultProof(snapshot, key, webcrypto);
  const { scanRun, fixList, fixItems } = writer.limitedRowsFromSnapshot(snapshot, { fixListId: "list_limited", proof });
  const run = {
    ...scanRun, id: identity.scan_id, project_id: identity.project_id,
    coverage_state: " access_limited ",
    coverage_reasons: [" rate_limited ", null, ` ${"a".repeat(201)} `],
    coverage_authority_version: ` ${coverage.coverage_authority_version} `,
  };
  const verified = async row => verifyLimitedResultProof(buildLimitedResultSnapshot({
    identity, scan: row, review: row, now, version: row.result_integrity_version,
  }), key, proof, webcrypto);
  return { run, fixList, fixItems, verified };
}

test("V9 returns the exact signed limited coverage fields to a fully entitled reader", async () => {
  const { run, fixList, fixItems, verified } = await limitedRun();
  const resultIntegrityVerified = await verified(run);
  assert.equal(resultIntegrityVerified, true);
  const projection = buildCustomerProjection({
    run, fixList, fixItems, fullAccess: true, authorityVerified: false, resultIntegrityVerified,
  });
  for (const field of Object.keys(coverage)) assert.deepEqual(projection.run[field], coverage[field]);
  assert.equal(projection.authority_verified, false);
  assert.equal(projection.result_integrity_verified, true);
  assert.equal(projection.run.score_is_provisional, true);
  assert.equal(projection.run.release_gate_eligible, false);
  assert.equal(Object.hasOwn(projection.run, "result_integrity_proof"), false);
  assert.equal(projection.run.scan_coverage_verified, true);
  assert.deepEqual(projection.run.scan_coverage, run.scan_coverage);
  assert.equal(await verified({ ...run, scan_coverage: { ...run.scan_coverage, usable_html_pages: 49 } }), false);
});

test("V9 keeps limited coverage out of previews, locked or unverified results and other statuses", async () => {
  const { run, fixList, fixItems, verified } = await limitedRun();
  const tampered = { ...run, coverage_reasons: ["another_reason"] };
  assert.equal(await verified(tampered), false);
  const cases = [
    { fullAccess: false, previewAccess: true },
    { fullAccess: false },
    { run: tampered, resultIntegrityVerified: false },
    { authorityVerified: true },
    { run: { ...run, status: "complete" }, authorityVerified: true },
    { run: { ...run, status: "crawling" } },
  ];
  for (const settings of cases) {
    const projection = buildCustomerProjection({
      run, fixList, fixItems, fullAccess: true, authorityVerified: false, resultIntegrityVerified: true, ...settings,
    });
    for (const field of Object.keys(coverage)) assert.equal(Object.hasOwn(projection.run, field), false);
    assert.equal(Object.hasOwn(projection.run, "scan_coverage_verified"), false);
  }
  const historical = buildCustomerProjection({
    run: { ...run, result_integrity_version: "standard_limited_result_integrity_v4_focused_scope_effective_path",
      scan_coverage_verified: true },
    fixList, fixItems, fullAccess: true, authorityVerified: false, resultIntegrityVerified: true,
  });
  assert.equal(historical.run.coverage_state, "access_limited");
  assert.equal(Object.hasOwn(historical.run, "scan_coverage_verified"), false);
  const [history] = buildScanHistoryProjection([run]);
  for (const field of Object.keys(coverage)) assert.equal(Object.hasOwn(history, field), false);
});
