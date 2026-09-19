import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const SECRET = "preview-seal-test-secret\n";
const FULL_PROOF = "a".repeat(64);

function fixture() {
  const run = {
    id: "scan_preview_1",
    project_id: "project_preview_1",
    owner_user_id: "owner_preview_1",
    website_url: "https://example.com",
    normalized_domain: "example.com",
    status: "complete",
    status_detail: "Your FixList is ready.",
    pages_found: 184,
    pages_crawled: 150,
    pages_retained: 150,
    queued_at: "2026-09-15T10:00:00.000Z",
    started_at: "2026-09-15T10:00:03.000Z",
    reviewing_at: "2026-09-15T10:01:00.000Z",
    completed_at: "2026-09-15T10:01:23.940Z",
    worker_heartbeat_at: "2026-09-15T10:01:23.940Z",
    health_score: 60,
    health_grade: "Needs work",
    release_gate_eligible: true,
    beta_revision_fingerprint: "0123456789abcdef",
    authority_seal_version: "standard_review_snapshot_hmac_geo_v1",
    geo_readiness: JSON.parse(readFileSync("tests/fixtures/geo/runtime.json", "utf8")).failures,
    authority_sealed_at: "2026-09-15T10:01:23.940Z",
    authority_proof: FULL_PROOF,
    fix_list_id: "fixlist_preview_1",
  };
  const fixList = {
    id: "fixlist_preview_1",
    scan_run_id: run.id,
    project_id: run.project_id,
    website_url: run.website_url,
    health_score: 60,
    health_grade: "Needs work",
    total_fixes: 3,
    critical_count: 1,
    high_count: 1,
    medium_count: 1,
    low_count: 0,
    generated_at: run.completed_at,
  };
  const fixItems = Array.from({ length: 3 }, (_, index) => ({
    id: `row_${index + 1}`,
    fix_id: `fix_${index + 1}`,
    issue_title: `Issue ${index + 1}`,
    customer_category: "Technical SEO",
    priority: index === 0 ? "critical" : "high",
    action_priority: index < 2 ? "fix_first" : "improve",
    action_priority_score: 100 - index,
    canonical_action_rank: index + 1,
    page_count: index + 2,
    page_url: `https://example.com/example-${index + 1}`,
    affected_pages: [`https://example.com/example-${index + 1}`, `https://example.com/hidden-${index + 1}`],
    source_pages: [`https://example.com/source-${index + 1}`],
    plain_english_explanation: `Explanation ${index + 1}`,
    why_it_matters: `Why ${index + 1}`,
    current_value: "private current value",
    recommended_value: `Recommendation ${index + 1}`,
    simple_next_step: `Next step ${index + 1}`,
    what_to_do_steps: ["private step"],
    family_breakdown: [{ family: "private" }],
    raw_finding: { private: true },
    difficulty: "medium",
    who_can_do_this: "SEO manager",
    requires_developer: false,
    evidence_class: "confirmed_problem",
  }));
  return { run, fixList, fixItems };
}

test("writer and reader build the same bounded signed customer preview", async () => {
  const writerPath = "../../base44/functions/persistDurableScanAuthorityV4/customerPreviewSeal.js";
  const readerPath = "../../base44/functions/getCustomerScanResultV4/customerPreviewSeal.js";
  assert.equal(existsSync(new URL(writerPath, import.meta.url)), true, "writer preview seal module must exist");
  assert.equal(existsSync(new URL(readerPath, import.meta.url)), true, "reader preview seal module must exist");
  const {
    CUSTOMER_PREVIEW_SEAL_VERSION: WRITER_PREVIEW_VERSION,
    buildCustomerPreviewPayload: buildWriterPreview,
    createCustomerPreviewProof,
    serializeCustomerPreviewPayload,
  } = await import(writerPath);
  const {
    CUSTOMER_PREVIEW_SEAL_VERSION: READER_PREVIEW_VERSION,
    buildCustomerPreviewPayload: buildReaderPreview,
    parseCustomerPreviewPayload,
    verifyCustomerPreviewProof,
  } = await import(readerPath);

  const { run, fixList, fixItems } = fixture();
  const args = {
    run,
    fixList,
    fixItems,
    ownerUserId: run.owner_user_id,
    fullAuthorityProof: FULL_PROOF,
  };
  const writerPayload = buildWriterPreview(args);
  const readerPayload = buildReaderPreview(args);

  assert.equal(WRITER_PREVIEW_VERSION, "standard_customer_preview_hmac_v2_geo_readiness");
  assert.equal(READER_PREVIEW_VERSION, WRITER_PREVIEW_VERSION);
  assert.deepEqual(readerPayload, writerPayload);
  assert.equal(writerPayload.scan_id, run.id);
  assert.equal(writerPayload.owner_user_id, run.owner_user_id);
  assert.equal(writerPayload.full_authority_proof, FULL_PROOF);
  assert.equal(writerPayload.release_fingerprint, run.beta_revision_fingerprint);
  assert.equal(writerPayload.fixList.total_fixes, 3);
  assert.equal(writerPayload.fixItems.length, 2);
  assert.deepEqual(writerPayload.fixItems.map((item) => item.issue_title), ["Issue 1", "Issue 2"]);
  assert.equal(writerPayload.fixItems[0].preview_example_page, "https://example.com/example-1");

  const forbidden = [
    "affected_pages",
    "source_pages",
    "current_value",
    "what_to_do_steps",
    "family_breakdown",
    "raw_finding",
  ];
  for (const item of writerPayload.fixItems) {
    for (const key of forbidden) assert.equal(key in item, false, `${key} leaked into signed preview`);
  }

  const proof = await createCustomerPreviewProof(writerPayload, SECRET);
  const serialized = serializeCustomerPreviewPayload(writerPayload);
  const parsed = parseCustomerPreviewPayload(serialized);
  assert.equal(await verifyCustomerPreviewProof(parsed, SECRET, proof), true);

  const tampered = structuredClone(parsed);
  tampered.fixItems[0].issue_title = "Tampered";
  assert.equal(await verifyCustomerPreviewProof(tampered, SECRET, proof), false);

  const rebound = structuredClone(parsed);
  rebound.full_authority_proof = "b".repeat(64);
  assert.equal(await verifyCustomerPreviewProof(rebound, SECRET, proof), false);
});

test("V4 persistence writes preview authority only after final full authority verification", () => {
  const writer = readFileSync("base44/functions/persistDurableScanAuthorityV4/entry.ts", "utf8");
  const authorityGate = writer.indexOf("if (!authorityPersisted)");
  const previewWrite = writer.indexOf("customer_preview_proof");
  assert.ok(authorityGate >= 0, "full authority persistence gate must remain present");
  assert.ok(previewWrite > authorityGate, "preview proof must be persisted only after full authority verifies");
});

test("V4 unpaid reader prefers the signed preview while paid reads keep full authority verification", () => {
  const reader = readFileSync("base44/functions/getCustomerScanResultV4/entry.ts", "utf8");
  const previewBranch = reader.indexOf("hasCustomerPreviewArtifact(run)");
  const fullRows = reader.indexOf("const fixList = await loadFixList");
  const fullVerify = reader.indexOf("verifyAuthoritySeal(snapshot, secret, proof)");
  assert.ok(previewBranch >= 0, "unpaid signed-preview branch must exist");
  assert.ok(previewBranch < fullRows, "signed preview must not reconstruct the full FixList first");
  assert.ok(fullVerify > fullRows, "paid/full path must retain existing full authority verification");
  assert.match(reader, /result_preview_invalid/);
});

test("signed customer preview is release-versioned and schema-bound", () => {
  const crossRuntime = JSON.parse(readFileSync("data/cross-runtime-release-components.json", "utf8"));
  const revision = JSON.parse(readFileSync("data/beta-crawler-revision.json", "utf8"));
  const scanRunSchema = readFileSync("base44/entities/ScanRun.jsonc", "utf8");

  assert.equal(
    crossRuntime.components.customer_preview_seal_version,
    "standard_customer_preview_hmac_v2_geo_readiness",
  );
  assert.equal(
    revision.component_versions.customer_preview_seal_version,
    "standard_customer_preview_hmac_v2_geo_readiness",
  );
  assert.equal(
    crossRuntime.components.customer_result_reader_version,
    "customer_result_reader_v9_published_route_identity",
  );
  assert.equal(
    revision.component_versions.customer_result_reader_version,
    "customer_result_reader_v9_published_route_identity",
  );
  for (const field of [
    "customer_preview_seal_version",
    "customer_preview_sealed_at",
    "customer_preview_payload",
    "customer_preview_proof",
  ]) {
    assert.match(scanRunSchema, new RegExp(`"${field}"`));
  }
});

test("the pre-preview release remains readable as historical authority", () => {
  for (const name of ["getCustomerScanResult", "getCustomerScanResultV2", "getCustomerScanResultV3", "getCustomerScanResultV4"]) {
    const compatibility = readFileSync(`base44/functions/${name}/releaseCompatibility.js`, "utf8");
    assert.match(compatibility, /"a511d61013ef9fe3"/);
  }
});

test("current-release terminal replay repairs only a missing signed preview after full authority verifies", () => {
  const writer = readFileSync("base44/functions/persistDurableScanAuthorityV4/entry.ts", "utf8");
  const replayFullVerify = writer.indexOf("await verifyAuthoritySeal(replaySnapshot, secret, scan.authority_proof)");
  const replayPreview = writer.indexOf("await ensureVerifiedCustomerPreview({", replayFullVerify);
  const replayRelease = writer.indexOf("await persistExactAdmissionRelease({", replayFullVerify);
  assert.ok(replayFullVerify >= 0, "terminal replay must retain full authority verification");
  assert.ok(replayPreview > replayFullVerify, "preview replay may happen only after full authority verifies");
  assert.ok(replayRelease > replayPreview, "admission release must follow preview recovery for current-release rows");
  assert.match(writer.slice(replayFullVerify, replayRelease), /beta_revision_fingerprint[^\n]+BASE44_HANDLER_RELEASE_FINGERPRINT/);
});


for (const authorityVersion of ["standard_review_snapshot_hmac_geo_v1", "standard_review_snapshot_hmac_identity_v1"]) test(`actual V6 unpaid request reads ${authorityVersion} signed preview without loading full result rows`, async () => {
  const [{
    buildCustomerPreviewPayload,
    createCustomerPreviewProof,
    serializeCustomerPreviewPayload,
    customerPreviewPayloadMatchesRun,
    hasCustomerPreviewArtifact,
    parseCustomerPreviewPayload,
    verifyCustomerPreviewProof,
  }, projection, limitedIntegrity, releaseContract, compatibility, buildIdentity] = await Promise.all([
    import("../../base44/functions/getCustomerScanResultV6/customerPreviewSeal.js"),
    import("../../base44/functions/getCustomerScanResultV6/projection.js"),
    import("../../base44/functions/getCustomerScanResultV6/limitedResultIntegrity.js"),
    import("../../base44/functions/getCustomerScanResultV6/generatedReleaseContract.js"),
    import("../../base44/functions/getCustomerScanResultV6/releaseCompatibility.js"),
    import("../../base44/functions/getCustomerScanResultV6/generatedBuildId.js"),
  ]);
  const { run: sourceRun, fixList, fixItems } = fixture();
  const run = {
    ...sourceRun,
    authority_seal_version: authorityVersion,
    beta_revision_fingerprint: releaseContract.RELEASE_FINGERPRINT,
    score_is_provisional: false,
    evidence_quality_blocking: false,
  };
  const previewPayload = buildCustomerPreviewPayload({
    run,
    fixList,
    fixItems,
    ownerUserId: run.owner_user_id,
    fullAuthorityProof: run.authority_proof,
  });
  const previewProof = await createCustomerPreviewProof(previewPayload, SECRET);
  Object.assign(run, {
    customer_preview_seal_version: "standard_customer_preview_hmac_v2_geo_readiness",
    customer_preview_sealed_at: run.authority_sealed_at,
    customer_preview_payload: serializeCustomerPreviewPayload(previewPayload),
    customer_preview_proof: previewProof,
  });

  let fullRowReads = 0;
  const base44 = {
    auth: { me: async () => ({ id: run.owner_user_id, email: "unpaid@example.com" }) },
    asServiceRole: {
      entities: {
        ScanRun: { get: async (id) => id === run.id ? structuredClone(run) : null },
        BusinessProject: {
          get: async (id) => id === run.project_id
            ? { id, owner_user_id: run.owner_user_id, website_url: run.website_url }
            : null,
        },
        Access: { filter: async () => [] },
        FixList: {
          get: async () => { fullRowReads += 1; throw new Error("preview must not load FixList"); },
          filter: async () => { fullRowReads += 1; throw new Error("preview must not filter FixList"); },
        },
        FixItem: {
          filter: async () => { fullRowReads += 1; throw new Error("preview must not load FixItems"); },
        },
      },
    },
  };

  const harnessName = `__customerPreviewV6Harness_${Date.now()}_${Math.random().toString(16).slice(2)}`;
  const entrySource = readFileSync("base44/functions/getCustomerScanResultV6/entry.ts", "utf8");
  const javascript = ts.transpileModule(entrySource, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  }).outputText.replace(/^import[\s\S]*?;\s*$/gm, "");
  const prelude = `const {
    createClientFromRequest,
    secrets,
    buildLimitedResultSnapshot,
    verifyLimitedResultProof,
    authoritySnapshotFromRows,
    buildCustomerProjection,
    buildScanHistoryProjection,
    evaluatePaidAccess,
    recordOwnedByUser,
    verifyAuthoritySeal,
    RELEASE_FINGERPRINT,
    FUNCTION_BUILD_ID,
    isReadableAuthorityReleaseFingerprint,
    customerPreviewPayloadMatchesRun,
    hasCustomerPreviewArtifact,
    parseCustomerPreviewPayload,
    verifyCustomerPreviewProof,
  } = globalThis.${harnessName};`;

  let handler = null;
  const priorDeno = globalThis.Deno;
  globalThis.Deno = {
    env: { get: () => "" },
    serve: (candidate) => { handler = candidate; },
  };
  globalThis[harnessName] = {
    createClientFromRequest: () => base44,
    secrets: { get: (name) => name === "SCAN_EVIDENCE_SIGNING_KEY" ? SECRET : "" },
    buildLimitedResultSnapshot: limitedIntegrity.buildLimitedResultSnapshot,
    verifyLimitedResultProof: limitedIntegrity.verifyLimitedResultProof,
    authoritySnapshotFromRows: projection.authoritySnapshotFromRows,
    buildCustomerProjection: projection.buildCustomerProjection,
    buildScanHistoryProjection: projection.buildScanHistoryProjection,
    evaluatePaidAccess: projection.evaluatePaidAccess,
    recordOwnedByUser: projection.recordOwnedByUser,
    verifyAuthoritySeal: projection.verifyAuthoritySeal,
    RELEASE_FINGERPRINT: releaseContract.RELEASE_FINGERPRINT,
    FUNCTION_BUILD_ID: buildIdentity.FUNCTION_BUILD_ID,
    isReadableAuthorityReleaseFingerprint: compatibility.isReadableAuthorityReleaseFingerprint,
    customerPreviewPayloadMatchesRun,
    hasCustomerPreviewArtifact,
    parseCustomerPreviewPayload,
    verifyCustomerPreviewProof,
  };

  try {
    await import(`data:text/javascript;base64,${Buffer.from(`${prelude}\n${javascript}\n// harness:${harnessName}`).toString("base64")}`);
    assert.equal(typeof handler, "function");
    const response = await handler(new Request("https://function.example", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action: "get", scan_id: run.id }),
    }));
    const body = await response.json();
    assert.equal(response.status, 200);
    assert.equal(body.success, true);
    assert.equal(body.access, "preview");
    assert.equal(body.authority_verified, true);
    assert.equal(body.release_contract_current, true);
    assert.equal(body.fixList.total_fixes, 3);
    assert.equal(body.fixItems.length, 2);
    assert.deepEqual(body.fixItems.map((item) => item.issue_title), ["Issue 1", "Issue 2"]);
    assert.equal(body.fixItems[0].preview_example_page, "https://example.com/example-1");
    assert.equal("affected_pages" in body.fixItems[0], false);
    assert.equal("raw_finding" in body.fixItems[0], false);
    assert.equal(fullRowReads, 0);
    assert.equal(body.run.geo_readiness.assessment_status, "assessed");
    assert.equal(body.run.geo_readiness.sample_pages, 1);
    assert.equal("observations" in body.run.geo_readiness, false);
    assert.equal("findings" in body.run.geo_readiness, false);
  } finally {
    delete globalThis[harnessName];
    if (priorDeno === undefined) delete globalThis.Deno;
    else globalThis.Deno = priorDeno;
  }
});
