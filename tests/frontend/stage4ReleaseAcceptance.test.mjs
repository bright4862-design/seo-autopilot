import assert from "node:assert/strict";
import test from "node:test";

import {
  EXPECTED_SCANNER_FUNCTIONS,
  EXPECTED_SCANNER_BUILD_IDS,
  EXPECTED_SCANNER_ROUTE_GENERATION,
  SCANNER_RUNTIME_ROLES,
  STAGE4_RELEASE_RECORD_VERSION,
  evaluateStage4ReleaseAcceptance,
} from "../../scripts/stage4ReleaseAcceptance.mjs";

import { RELEASE_FINGERPRINT, RELEASE_COMPONENT_VERSIONS } from "../../src/lib/generatedReleaseContract.js";
import { FUNCTION_BUILD_ID as V9_START_BUILD_ID } from "../../base44/functions/startStandardScanJobV9/generatedBuildId.js";
import { buildCustomerProjection as buildPublicV8Projection } from "../../base44/functions/getCustomerScanResultV8/projection.js";
import { buildCustomerProjection as buildStagedV9Projection } from "../../base44/functions/getCustomerScanResultV9/projection.js";

const SHA = "a".repeat(40);
const PROOF = "b".repeat(64);
const DIGEST = `sha256:${"c".repeat(64)}`;
const RECEIPT = "receipt:verified-stage4-evidence";

function actualCustomerProjection(projection = buildPublicV8Projection) {
  return projection({
    // Construct a real, sanitized V9 customer response from synthetic persisted
    // rows. The stored HMAC is deliberately absent from the reader projection.
    run: {
      id: "scan-acceptance-1", project_id: "project-acceptance-1",
      status: "complete", scan_mode: "standard_150",
      beta_revision_fingerprint: RELEASE_FINGERPRINT, authority_proof: PROOF,
    },
    fixList: {
      id: "fix-list-1", project_id: "project-acceptance-1",
      scan_run_id: "scan-acceptance-1", authority_proof: PROOF,
    },
    fixItems: [], fullAccess: true, authorityVerified: true,
  });
}

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
      route_generation: EXPECTED_SCANNER_ROUTE_GENERATION,
      site: {
        verified: true,
        source_sha: SHA,
        hosts_verified: ["getfixlist.com", "getfixlist.base44.app"],
        verification_reference: RECEIPT,
      },
      functions: EXPECTED_SCANNER_FUNCTIONS.map((name) => ({
        name,
        verified: true,
        source_sha: SHA,
        runtime_build_id: EXPECTED_SCANNER_BUILD_IDS[name],
        verification_reference: `${RECEIPT}:${name}`,
      })),
      worker: {
        beta_revision_fingerprint: RELEASE_FINGERPRINT,
        component_versions: { ...RELEASE_COMPONENT_VERSIONS },
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
        total_claim_budget: 2,
        per_owner_claim_budget: 2,
        public_claims_closed: true,
        activation_reference: `${RECEIPT}:cohort`,
      },
      scan: {
        beta_revision_fingerprint: RELEASE_FINGERPRINT,
        scan_id: "scan-acceptance-1",
        project_id: "project-acceptance-1",
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
        customer_result: actualCustomerProjection(),
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
        project_id: "project-acceptance-1",
        normalized_domain: "example.com",
        status: "complete",
        mode: "standard_150",
        pages_crawled: 150,
        beta_revision_fingerprint: RELEASE_FINGERPRINT,
        release_gate_eligible: true,
        authority_proof: "d".repeat(64),
        fix_list_id: "fix-list-2",
        source_sha: SHA,
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

test("source release manifest supplies all six scanner roles at one route generation", () => {
  assert.equal(EXPECTED_SCANNER_FUNCTIONS.length, SCANNER_RUNTIME_ROLES.length);
  assert.equal(SCANNER_RUNTIME_ROLES.length, 6);
  assert.match(EXPECTED_SCANNER_ROUTE_GENERATION, /^V\d+$/);
  for (const role of SCANNER_RUNTIME_ROLES) {
    assert.ok(EXPECTED_SCANNER_FUNCTIONS.includes(`${role}${EXPECTED_SCANNER_ROUTE_GENERATION}`));
  }
});

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

test("deployed route generation must match the source release manifest", () => {
  const record = validRecord();
  record.deployment.route_generation = "V999";
  const result = evaluateStage4ReleaseAcceptance(record);
  assert.equal(result.status, "failed");
  assert.ok(result.failures.some((value) => value.includes("route generation")));
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
  record.acceptance.reload.customer_result.run.id = "scan-other";
  record.acceptance.reload.customer_result.fixList.scan_run_id = "scan-other";
  record.acceptance.history.scan_ids = ["scan-other"];
  const result = evaluateStage4ReleaseAcceptance(record);
  assert.equal(result.pass, false);
  assert.ok(result.failures.some((value) => value.includes("exact scan_id reload")));
  assert.ok(result.failures.some((value) => value.includes("reload returned a different FixList")));
  assert.ok(result.failures.some((value) => value.includes("history does not include")));
});

test("distinct signed-shaped rescan cannot reuse the baseline FixList identity", () => {
  const baseline = validRecord();
  assert.equal(evaluateStage4ReleaseAcceptance(baseline).pass, true);
  // V8 persistence associates each FixList with the exact ScanRun. A new ScanRun
  // must not be certified using the previous run's saved FixList.
  for (const duplicate of [baseline.acceptance.scan.fix_list_id, `  ${baseline.acceptance.scan.fix_list_id}  `]) {
    const record = validRecord();
    record.acceptance.rescan.fix_list_id = duplicate;
    const result = evaluateStage4ReleaseAcceptance(record);
    assert.equal(result.status, "failed");
    assert.ok(result.failures.includes("rescan FixList must differ from baseline acceptance FixList"));
  }
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

test("source-bound worker and persisted scan fingerprint are required beyond matching source SHA", () => {
  const record = validRecord();
  assert.equal(evaluateStage4ReleaseAcceptance(record).pass, true, "synthetic control");
  record.deployment.worker.beta_revision_fingerprint = "01ebe8e90df1e6bd";
  record.acceptance.scan.beta_revision_fingerprint = "e0eca935c350e590";
  const result = evaluateStage4ReleaseAcceptance(record);
  assert.equal(result.pass, false);
  assert.ok(result.failures.some((value) => value.includes("worker release fingerprint")));
  assert.ok(result.failures.some((value) => value.includes("customer acceptance fingerprint")));
});

test("source-matching SHA and fingerprint cannot conceal a drifted or incomplete worker component map", () => {
  const record = validRecord();
  record.deployment.worker.component_versions.scanner_version = "foreign_scanner";
  let result = evaluateStage4ReleaseAcceptance(record);
  assert.equal(result.pass, false);
  assert.ok(result.failures.some((value) => value.includes("worker component versions")));

  record.deployment.worker.component_versions = { ...RELEASE_COMPONENT_VERSIONS };
  delete record.deployment.worker.component_versions.scanner_version;
  result = evaluateStage4ReleaseAcceptance(record);
  assert.equal(result.pass, false);

  record.deployment.worker.component_versions = { ...RELEASE_COMPONENT_VERSIONS, invented_marker: "surprise" };
  result = evaluateStage4ReleaseAcceptance(record);
  assert.equal(result.pass, false);

  record.deployment.worker.component_versions = { ...RELEASE_COMPONENT_VERSIONS };
  assert.equal(evaluateStage4ReleaseAcceptance(record).pass, true, "full exact-map control");
});

test("every current scanner route has an exact source-generated package digest", () => {
  assert.equal(Object.keys(EXPECTED_SCANNER_BUILD_IDS).length, 6);
  for (const name of EXPECTED_SCANNER_FUNCTIONS) {
    assert.match(EXPECTED_SCANNER_BUILD_IDS[name], /^[a-f0-9]{64}$/, name);
  }
  assert.equal(evaluateStage4ReleaseAcceptance(validRecord()).pass, true, "synthetic positive control");
});

test("a valid source SHA does not authorize foreign or placeholder Base44 packages", () => {
  const record = validRecord();
  record.deployment.functions[0].runtime_build_id = "build-1";
  let result = evaluateStage4ReleaseAcceptance(record);
  assert.equal(result.pass, false);
  assert.ok(result.failures.some((failure) => failure.includes("runtime package build ID")));

  assert.notEqual(V9_START_BUILD_ID, EXPECTED_SCANNER_BUILD_IDS.startStandardScanJobV8);
  record.deployment.functions[0].runtime_build_id = V9_START_BUILD_ID;
  result = evaluateStage4ReleaseAcceptance(record);
  assert.equal(result.pass, false, "V9 digest cannot masquerade as a V8 runtime package");

  record.deployment.functions[0].runtime_build_id = "";
  result = evaluateStage4ReleaseAcceptance(record);
  assert.equal(result.pass, false, "missing package identity cannot pass");
  assert.ok(result.failures.some((failure) => failure.includes("runtime_build_id missing")));

  record.deployment.functions[0].runtime_build_id = EXPECTED_SCANNER_BUILD_IDS.startStandardScanJobV8;
  assert.equal(evaluateStage4ReleaseAcceptance(record).pass, true, "exact package restored");
});

test("a matching final row must not hide a conflicting duplicate Base44 runtime identity", () => {
  const record = validRecord();
  const correct = record.deployment.functions[0];
  const foreign = {
    ...correct,
    verified: false,
    runtime_build_id: V9_START_BUILD_ID,
    verification_reference: "receipt:foreign-runtime-observation",
  };
  // The old Map lookup would keep only the final matching row and report PASS.
  record.deployment.functions.unshift(foreign);
  assert.equal(new Map(record.deployment.functions.map((fn) => [fn.name, fn])).get(correct.name), correct);
  const result = evaluateStage4ReleaseAcceptance(record);
  assert.equal(result.pass, false);
  assert.ok(result.failures.some((failure) => failure.includes("distinct source-declared functions")));

  // Changing row order must not turn contradictory evidence into acceptance.
  record.deployment.functions.reverse();
  const reversed = evaluateStage4ReleaseAcceptance(record);
  assert.equal(reversed.pass, false);
  assert.ok(reversed.failures.some((failure) => failure.includes("distinct source-declared functions")));
});

test("a mixed V8/V9 roster is refused, but a reordered exact V8 roster remains valid", () => {
  const record = validRecord();
  record.deployment.functions.reverse();
  assert.equal(evaluateStage4ReleaseAcceptance(record).pass, true, "function evidence ordering is immaterial");

  record.deployment.functions.push({
    ...record.deployment.functions[0],
    name: "startStandardScanJobV9",
    runtime_build_id: V9_START_BUILD_ID,
  });
  let result = evaluateStage4ReleaseAcceptance(record);
  assert.equal(result.pass, false);
  assert.ok(result.failures.some((failure) => failure.includes("distinct source-declared functions")));

  record.deployment.functions.pop();
  record.deployment.functions.push({ ...record.deployment.functions[0] });
  result = evaluateStage4ReleaseAcceptance(record);
  assert.equal(result.pass, false, "even identical duplicate rows are ambiguous evidence");
  assert.ok(result.failures.some((failure) => failure.includes("distinct source-declared functions")));
});

// Composition: exact-source package roster + CI provenance coherence.
test("CI evidence URL must identify the same run in the source repository", () => {
  const baseline = validRecord();
  assert.equal(evaluateStage4ReleaseAcceptance(baseline).pass, true);

  const mutations = [
    ["different run", (record) => {
      record.ci.run_url = "https://github.com/bright4862-design/seo-autopilot/actions/runs/654321";
    }],
    ["different repository", (record) => {
      record.ci.run_url = "https://github.com/another-owner/seo-autopilot/actions/runs/123456";
    }],
    ["unsafe numeric run ID", (record) => {
      record.ci.run_id = Number.MAX_SAFE_INTEGER + 1;
      record.ci.run_url = `https://github.com/bright4862-design/seo-autopilot/actions/runs/${record.ci.run_id}`;
    }],
  ];

  for (const [description, mutate] of mutations) {
    const record = validRecord();
    mutate(record);
    const result = evaluateStage4ReleaseAcceptance(record);
    assert.equal(result.status, "failed", description);
    assert.equal(result.pass, false, description);
    assert.ok(result.failures.some((failure) => failure.includes("CI run")), description);
  }
});


// Composition on #496: full seven-draft matrix, sourced from #458/#459/#470.
test("independently persisted rescan identity is required even if comparison is verified", () => {
  const baseline = evaluateStage4ReleaseAcceptance(validRecord());
  assert.equal(baseline.status, "pass", JSON.stringify(baseline.failures));

  const cases = [
    ["mode", "standard_500", "rescan was not Standard 150"],
    ["pages_crawled", 151, "rescan pages_crawled"],
    ["pages_crawled", 0, "rescan pages_crawled"],
    ["pages_crawled", 2.5, "rescan pages_crawled"],
    ["authority_proof", "", "rescan authority proof"],
    ["authority_proof", "not-a-proof", "rescan authority proof"],
    ["authority_proof", PROOF, "rescan reused baseline authority proof"],
    ["fix_list_id", "", "rescan FixList id"],
    ["source_sha", "9".repeat(40), "rescan source"],
  ];
  for (const [field, invalid, reason] of cases) {
    const record = validRecord();
    record.acceptance.rescan[field] = invalid;
    const result = evaluateStage4ReleaseAcceptance(record);
    assert.equal(result.status, "failed", field);
    assert.ok(result.failures.some((value) => value.includes(reason)), field);
  }

  const unsigned = validRecord();
  for (const key of ["mode", "pages_crawled", "authority_proof", "fix_list_id", "source_sha"]) {
    delete unsigned.acceptance.rescan[key];
  }
  const result = evaluateStage4ReleaseAcceptance(unsigned);
  assert.equal(result.status, "failed");
  assert.equal(result.failures.filter((value) => value.startsWith("rescan ")).length, 5);
});

test("a distinct, valid, bounded Standard 150 rescan retains the acceptance shape", () => {
  const record = validRecord();
  record.acceptance.rescan.scan_id = "scan-acceptance-3";
  record.acceptance.rescan.pages_crawled = 1;
  record.acceptance.rescan.authority_proof = "e".repeat(64);
  record.acceptance.rescan.fix_list_id = "fix-list-3";
  assert.equal(evaluateStage4ReleaseAcceptance(record).pass, true);
});

test("a linked rescan needs a second fresh claim for the same owner", () => {
  assert.equal(evaluateStage4ReleaseAcceptance(validRecord()).pass, true);
  for (const [total, perOwner, fragment] of [
    [1, 1, "total claim budget"],
    [2, 1, "per-owner claim budget"],
    [2, undefined, "per-owner claim budget"],
    [2, 3, "per-owner claim budget"],
    [2, 1.5, "per-owner claim budget"],
    [0, 0, "total claim budget"],
    [4, 2, "total claim budget"],
  ]) {
    const record = validRecord();
    record.acceptance.cohort.total_claim_budget = total;
    if (perOwner === undefined) delete record.acceptance.cohort.per_owner_claim_budget;
    else record.acceptance.cohort.per_owner_claim_budget = perOwner;
    const result = evaluateStage4ReleaseAcceptance(record);
    assert.equal(result.status, "failed", `total=${total}, perOwner=${perOwner}`);
    assert.ok(result.failures.some((value) => value.includes(fragment)));
  }
  const spare = validRecord();
  spare.acceptance.cohort.total_claim_budget = 3;
  spare.acceptance.cohort.per_owner_claim_budget = 2;
  assert.equal(evaluateStage4ReleaseAcceptance(spare).pass, true);
});

test("Stage-4 evidence refuses timestamps that reverse the scan-to-readback sequence", () => {
  assert.equal(evaluateStage4ReleaseAcceptance(validRecord()).pass, true, "chronological control");
  for (const [step, observedAt, message] of [
    ["reload", "2026-09-19T20:09:59Z", "reload observation precedes accepted scan"],
    ["history", "2026-09-19T20:09:59Z", "history observation precedes accepted scan"],
    ["rescan", "2026-09-19T20:09:59Z", "rescan observation must follow accepted scan"],
    ["rescan", "2026-09-19T20:10:00Z", "rescan observation must follow accepted scan"],
  ]) {
    const record = validRecord();
    record.acceptance[step].observed_at = observedAt;
    const result = evaluateStage4ReleaseAcceptance(record);
    assert.equal(result.status, "failed", step);
    assert.ok(result.failures.includes(message), step);
  }
  const offset = validRecord();
  offset.acceptance.reload.observed_at = "2026-09-19T22:11:00+02:00";
  assert.equal(evaluateStage4ReleaseAcceptance(offset).pass, true, "equivalent timezone");
});


test("rollback cannot point back to the serving worker revision", () => {
  const record = validRecord();
  assert.equal(evaluateStage4ReleaseAcceptance(record).pass, true, "distinct rollback baseline");
  record.deployment.worker.rollback_target = record.deployment.worker.revision;
  let result = evaluateStage4ReleaseAcceptance(record);
  assert.equal(result.pass, false, "self-rollback must fail");
  assert.ok(result.failures.some((failure) => failure.includes("rollback target must differ")));

  record.deployment.worker.rollback_target = `  ${record.deployment.worker.revision}  `;
  result = evaluateStage4ReleaseAcceptance(record);
  assert.equal(result.pass, false, "whitespace must not disguise a self-rollback");

  record.deployment.worker.rollback_target = "fixlist-standard150-worker-00122-old";
  assert.equal(evaluateStage4ReleaseAcceptance(record).pass, true, "distinct rollback remains allowed");
});

test("composition does not short-circuit simultaneous cross-family regressions", () => {
  const record = validRecord();
  assert.equal(evaluateStage4ReleaseAcceptance(record).pass, true, "positive composed control");

  // Five independent families can fail at once. One repaired predicate must
  // not conceal the others in a short-circuited release decision.
  record.ci.run_url = "https://github.com/unrelated/seo-autopilot/actions/runs/123456";
  record.deployment.functions[0].runtime_build_id = V9_START_BUILD_ID;
  record.acceptance.cohort.total_claim_budget = 1;
  record.acceptance.cohort.per_owner_claim_budget = 1;
  record.acceptance.rescan.pages_crawled = 151;
  record.acceptance.reload.observed_at = "2026-09-19T20:09:59Z";
  record.deployment.worker.rollback_target = record.deployment.worker.revision;

  const result = evaluateStage4ReleaseAcceptance(record);
  assert.equal(result.status, "failed");
  assert.equal(result.pass, false);
  for (const reason of [
    "CI run URL",
    "runtime package build ID",
    "total claim budget",
    "per-owner claim budget",
    "rescan pages_crawled",
    "reload observation precedes accepted scan",
    "rollback target must differ from serving worker revision",
  ]) assert.ok(result.failures.some((failure) => failure.includes(reason)), reason);
});

test("matching ScanRun, FixList and HMAC text cannot masquerade as a verified full customer read-back", () => {
  assert.equal(evaluateStage4ReleaseAcceptance(validRecord()).pass, true, "synthetic baseline");

  for (const [field, bad, message] of [
    ["access", "preview", "customer reload did not return full-access FixList"],
    ["authority_verified", false, "customer reload did not verify full signed authority"],
    ["release_contract_current", false, "customer reload did not verify current release contract"],
  ]) {
    const record = validRecord();
    // Persisted proof existence does not substitute for verified reader response.
    record.acceptance.reload.customer_result[field] = bad;
    let result = evaluateStage4ReleaseAcceptance(record);
    assert.equal(result.pass, false, field);
    assert.ok(result.failures.includes(message), field);
    delete record.acceptance.reload.customer_result[field];
    result = evaluateStage4ReleaseAcceptance(record);
    assert.equal(result.pass, false, `missing ${field}`);
    assert.ok(result.failures.includes(message), `missing ${field}`);
  }
});

test("public V8 and staged V9 sanitized projections both omit the stored authority proof", () => {
  for (const [generation, builder] of [["public V8", buildPublicV8Projection], ["staged V9", buildStagedV9Projection]]) {
    const response = actualCustomerProjection(builder);
    for (const row of [response, response.run, response.fixList]) {
      assert.equal(Object.hasOwn(row, "authority_proof"), false, generation);
    }
    const record = validRecord();
    record.acceptance.reload.customer_result = response;
    assert.equal(evaluateStage4ReleaseAcceptance(record).pass, true, generation);
  }
  const record = validRecord();
  assert.equal(Object.hasOwn(record.acceptance.reload, "authority_proof"), false);
  assert.equal(evaluateStage4ReleaseAcceptance(record).pass, true, "sanitized public V8 baseline");

  record.acceptance.reload.authority_proof = PROOF;
  let result = evaluateStage4ReleaseAcceptance(record);
  assert.equal(result.pass, false);
  assert.ok(result.failures.includes("customer reload must not echo private persisted proof"));
  delete record.acceptance.reload.authority_proof;
  record.acceptance.reload.customer_result.run.authority_proof = PROOF;
  result = evaluateStage4ReleaseAcceptance(record);
  assert.equal(result.pass, false);
  assert.ok(result.failures.includes("customer reload must not echo private persisted proof"));
});

test("customer read-back binds scan, FixList, project and release separately", () => {
  for (const [name, change, reason] of [
    ["foreign customer project", r => { r.customer_result.run.project_id = "foreign"; }, "customer reload project"],
    ["foreign FixList project", r => { r.customer_result.fixList.project_id = "foreign"; }, "customer reload project"],
    ["foreign scan", r => { r.customer_result.run.id = "foreign"; }, "exact scan_id reload"],
    ["foreign FixList scan", r => { r.customer_result.fixList.scan_run_id = "foreign"; }, "reload returned a different FixList"],
    ["foreign release", r => { r.customer_result.run.beta_revision_fingerprint = "f".repeat(16); }, "completed current-release result"],
    ["incomplete scan", r => { r.customer_result.run.status = "limited"; }, "completed current-release result"],
    ["missing response", r => { delete r.customer_result; }, "customer reload response not successful"],
  ]) {
    const record = validRecord();
    change(record.acceptance.reload);
    const result = evaluateStage4ReleaseAcceptance(record);
    assert.equal(result.pass, false, name);
    assert.ok(result.failures.some(x => x.includes(reason)), name);
  }
});

test("linked rescan must retain the accepted owner project identity", () => {
  assert.equal(evaluateStage4ReleaseAcceptance(validRecord()).pass, true, "same-project positive control");

  for (const [label, mutate] of [
    ["foreign project", (record) => { record.acceptance.rescan.project_id = "project-foreign"; }],
    ["missing project", (record) => { delete record.acceptance.rescan.project_id; }],
    ["empty project", (record) => { record.acceptance.rescan.project_id = "  "; }],
  ]) {
    const record = validRecord();
    mutate(record);
    // Matching parent_scan_id, domain, distinct HMAC shape and completed status
    // cannot substitute for an owner/project-bound rescan receipt.
    const result = evaluateStage4ReleaseAcceptance(record);
    assert.equal(result.pass, false, label);
    assert.ok(result.failures.includes("rescan project does not match acceptance baseline"), label);
  }
});

test("a linked comparison rescan must be eligible under the exact frozen release", () => {
  assert.equal(evaluateStage4ReleaseAcceptance(validRecord()).pass, true, "current eligible rescan positive control");
  for (const [name, mutate, reason] of [
    ["historical fingerprint", r => { r.acceptance.rescan.beta_revision_fingerprint = "0".repeat(16); }, "rescan fingerprint does not match frozen source"],
    ["missing fingerprint", r => { delete r.acceptance.rescan.beta_revision_fingerprint; }, "rescan fingerprint does not match frozen source"],
    ["ineligible rescan", r => { r.acceptance.rescan.release_gate_eligible = false; }, "rescan is not release-gate eligible"],
    ["missing eligibility", r => { delete r.acceptance.rescan.release_gate_eligible; }, "rescan is not release-gate eligible"],
  ]) {
    const record = validRecord();
    mutate(record);
    // Distinct ScanRun/FixList, matching project, source SHA, and HMAC-shaped
    // proof remain valid, isolating the release-identity and authority checks.
    const verdict = evaluateStage4ReleaseAcceptance(record);
    assert.equal(verdict.pass, false, name);
    assert.ok(verdict.failures.includes(reason), name);
  }
});

test("an operator-CLI canary is not a published customer-UI Stage-4 journey", () => {
  // Positive control: an otherwise complete synthetic release record has the
  // expected evidence shapes. Neither control is live release proof.
  assert.equal(evaluateStage4ReleaseAcceptance(validRecord()).pass, true);
  const record = validRecord();
  // The authenticated staged owner canary calls Base44 functions from a CLI.
  // It does not submit from the published customer UI, observe saved history,
  // or perform the distinct comparison rescan required by Stage 4.
  record.acceptance.scan.submission_surface = "staged_owner_canary_cli";
  record.acceptance.history = {};
  record.acceptance.rescan = {};
  const result = evaluateStage4ReleaseAcceptance(record);
  assert.equal(result.pass, false);
  assert.equal(result.status, "failed");
  for (const required of [
    "published customer UI",
    "history",
    "rescan",
  ]) {
    assert.ok(result.failures.some(message => message.includes(required)), required);
  }
});
