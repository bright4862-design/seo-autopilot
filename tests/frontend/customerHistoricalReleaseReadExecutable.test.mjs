import assert from "node:assert/strict";
import { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";
import ts from "typescript";
import stagedDeployments from "../../data/generated-staged-v9-routes.json" with { type: "json" };
import { materializeStagedV9Packages } from "../../scripts/lib/staged-v9-function-packages.mjs";
import { checkHistoricalLimitedReopen } from "./helpers/historicalLimitedFixture.mjs";
import { loadSavedReportClient, savedReportReader } from "./helpers/savedReportClient.mjs";

import { buildAuthoritySnapshot } from "../../base44/functions/persistDurableScanAuthority/authoritySnapshot.js";
import { authorityRowsFromSnapshot } from "../../base44/functions/persistDurableScanAuthority/authorityRows.js";
import { createAuthoritySeal } from "../../base44/functions/persistDurableScanAuthority/authoritySeal.js";
import {
  authoritySnapshotFromRows,
  buildCustomerProjection,
  buildScanHistoryProjection,
  evaluatePaidAccess,
  recordOwnedByUser,
  verifyAuthoritySeal,
} from "../../base44/functions/getCustomerScanResult/projection.js";
import {
  buildLimitedResultSnapshot,
  verifyLimitedResultProof,
} from "../../base44/functions/getCustomerScanResult/limitedResultIntegrity.js";
import { RELEASE_FINGERPRINT } from "../../base44/functions/getCustomerScanResult/generatedReleaseContract.js";
import { isReadableAuthorityReleaseFingerprint } from "../../base44/functions/getCustomerScanResult/releaseCompatibility.js";
import { FUNCTION_BUILD_ID } from "../../base44/functions/getCustomerScanResult/generatedBuildId.js";
import * as activeProjection from "../../base44/functions/getCustomerScanResultV8/projection.js";
import * as activeLimited from "../../base44/functions/getCustomerScanResultV8/limitedResultIntegrity.js";
import * as activePreview from "../../base44/functions/getCustomerScanResultV8/customerPreviewSeal.js";
import * as activeCompatibility from "../../base44/functions/getCustomerScanResultV8/releaseCompatibility.js";
import { FUNCTION_BUILD_ID as ACTIVE_FUNCTION_BUILD_ID } from "../../base44/functions/getCustomerScanResultV8/generatedBuildId.js";
import { buildAuthoritySnapshot as buildStagedAuthoritySnapshot } from "../../base44/functions/persistDurableScanAuthorityV9/authoritySnapshot.js";
import { authorityRowsFromSnapshot as stagedAuthorityRowsFromSnapshot } from "../../base44/functions/persistDurableScanAuthorityV9/authorityRows.js";
import { createAuthoritySeal as createStagedAuthoritySeal } from "../../base44/functions/persistDurableScanAuthorityV9/authoritySeal.js";
import { PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION } from "../../base44/functions/persistDurableScanAuthorityV9/evidenceUrlIdentity.js";
import * as stagedProjection from "../../base44/functions/getCustomerScanResultV9/projection.js";
import * as stagedLimited from "../../base44/functions/getCustomerScanResultV9/limitedResultIntegrity.js";
import * as stagedPreview from "../../base44/functions/getCustomerScanResultV9/customerPreviewSeal.js";
import * as stagedCompatibility from "../../base44/functions/getCustomerScanResultV9/releaseCompatibility.js";
import * as stagedRelease from "../../base44/functions/getCustomerScanResultV9/generatedReleaseContract.js";
import * as stagedBuild from "../../base44/functions/getCustomerScanResultV9/generatedBuildId.js";
import { buildCustomerPreviewPayload as buildStagedPreviewPayload,
  createCustomerPreviewProof as createStagedPreviewProof,
  serializeCustomerPreviewPayload as serializeStagedPreviewPayload,
} from "../../base44/functions/persistDurableScanAuthorityV9/customerPreviewSeal.js";
import * as scanPresentation from "../../src/lib/scanPresentation.js";
import { emptyGeoReadiness } from "../../base44/functions/persistDurableScanAuthorityV9/geoReadiness.js";

const entrySource = readFileSync("base44/functions/getCustomerScanResult/entry.ts", "utf8");
const activeEntrySource = readFileSync("base44/functions/getCustomerScanResultV8/entry.ts", "utf8");
const SECRET = "historical-reader-test-secret-never-deployed";
const STALE_PROCESS_SECRET = "stale-process-signing-key-never-deployed";
const HISTORICAL_FINGERPRINT = "5d94e93c54a9efb6";
// The revision recorded on main immediately before commercial-hub sampling.
// Keep this fixture fixed: deriving it from the new candidate would miss a
// release advance that accidentally makes intact customer history unreadable.
const PREVIOUS_CURRENT_FINGERPRINT = "01ebe8e90df1e6bd";
const PREVIOUS_STAGED_FINGERPRINT = "118544dcf77d86cf";
const PROTECTED_PLAN_STAGED_FINGERPRINT = "2678b7511b2c5190";
const PREVIOUS_PILOT_FINGERPRINT = "b36ca24b8e0f728e";
const UNKNOWN_FINGERPRINT = "aaaaaaaaaaaaaaaa";
let handlerInvocationSequence = 0;

async function importHandler(harnessName, source) {
  const javascript = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  }).outputText.replace(/^import[\s\S]*?;\s*$/gm, "");
  const prelude = `const { ${Object.keys(globalThis[harnessName]).join(",")} } = globalThis.${harnessName};`;
  await import(`data:text/javascript;base64,${Buffer.from(`${prelude}\n${javascript}\n// harness:${harnessName}`).toString("base64")}`);
}

const headingFinding = { fix_id: "fix_hist", rule: "missing_h1", issue_title: "Review this page heading" };

async function sealedRows(fingerprint, staged, notice, { findings = [headingFinding], savedCap = 150 } = {}) {
  const buildSnapshot = staged ? buildStagedAuthoritySnapshot : buildAuthoritySnapshot;
  const published = staged && [PROTECTED_PLAN_STAGED_FINGERPRINT, PREVIOUS_PILOT_FINGERPRINT].includes(fingerprint);
  const evidencePage = "https://www.funbooker.com/fr/ville/paris";
  const snapshot = buildSnapshot({
    ...(published ? { identityVersion: PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION } : {}),
    scan: {
      submitted_url: "https://www.funbooker.com/",
      website_url: "https://www.funbooker.com/",
      scanner_version: "python_scanner_v3_bounded_request",
      scanner_build_revision: "authenticated_health_probe_v1",
      scanner_wrapper_version: "runStandard150Scan_v1_python_required",
      advanced_scan_backend: "python_scanner_api",
      deno_fallback_used: false,
      beta_revision_fingerprint: fingerprint,
      metadata_evidence_version: "metadata_evidence_v1_description_states",
      title_evidence_version: "title_evidence_v1_contextual_duplicates",
      pages_found: 5000,
      pages_crawled: 150,
      pages_retained: 150,
      usable_html_page_count: 150,
      representative_html_page_count: 150,
      default_route_page_count: 0,
      discovery_quality_state: "representative",
      evidence_quality_gate_version: "evidence_quality_gate_v2_shared_coverage_decision",
      crawl_timing: { queue_exhausted: false, sitemap_fetch_count: 1, ...(notice ? { optional_checks_notice_reason: notice } : {}) },
      sampling_evidence: { sitemap_urls_discovered: 5000 },
      coverage_authority_evidence_version: "coverage_authority_evidence_v2_authoritative",
      coverage_authority_evidence: {
        coverage_authority_evidence_version: "coverage_authority_evidence_v2_authoritative",
        assessment: "sufficient",
      },
      classification_integrity: {
        version: "classification_integrity_v1",
        state: "complete",
        verdict: "complete",
        classifier_version: "archetype_classifier_v10_structural_finance_member_retail",
        evidence_sufficiency: "sufficient",
        usable_pages: 150,
        complete_small_site_inventory: false,
      },
      classification_verdict: "complete",
      worker_peak_memory_bytes: 1024,
      ...(staged && savedCap !== null ? {
        scan_mode: savedCap === 500 ? "standard_500" : "standard_150",
        pipeline_mode: "staged",
        page_cap: savedCap,
      } : {}),
    },
    review: {
      archetype_classifier_version: "archetype_classifier_v10_structural_finance_member_retail",
      review_version: "python_review_v2_structural_marketplace",
      review_evidence_calibration_version: "review_evidence_calibration_v6_health_score_v2",
      ai_review_backend: "python_review_api",
      python_review_fallback_used: false,
      release_gate_eligible: true,
      score_is_provisional: false,
      evidence_quality_blocking: false,
      beta_revision_fingerprint: fingerprint,
      metadata_evidence_version: "metadata_evidence_v1_description_states",
      title_evidence_version: "title_evidence_v1_contextual_duplicates",
      scan_status: "complete",
      health_score: 48,
      health_grade: "Needs attention",
      usable_html_page_count: 150,
      representative_html_page_count: 150,
      default_route_page_count: 0,
      discovery_quality_state: "representative",
      evidence_quality_gate_version: "evidence_quality_gate_v2_shared_coverage_decision",
      coverage_authority_evidence: {
        coverage_authority_evidence_version: "coverage_authority_evidence_v2_authoritative",
        assessment: "sufficient",
      },
      classification_integrity: {
        version: "classification_integrity_v1",
        state: "complete",
        verdict: "complete",
        classifier_version: "archetype_classifier_v10_structural_finance_member_retail",
        evidence_sufficiency: "sufficient",
        usable_pages: 150,
        complete_small_site_inventory: false,
      },
      classification_verdict: "complete",
      worker_peak_memory_bytes: 1024,
      ...(staged ? { geo_readiness: emptyGeoReadiness() } : {}),
      recommendations: findings.map(finding => ({
        ...finding,
        priority: "medium", page_url: evidencePage,
        affected_pages: [evidencePage],
        recommended_value: "Keep the verified saved instruction.",
        ...(published ? {
          evidence_url_identity_version: PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION,
          repair_coverage_version: "repair_coverage_v5_published_route_identity",
          page_count: 1,
          family_breakdown: { location_landing: 1 },
          representative_pages_by_family: { location_landing: [evidencePage] },
          affected_pages_complete: true,
          affected_reported: 1,
          affected_observed: 1,
          affected_eligible: 1,
          checked_eligible: 1,
          indexable_affected: 1,
          indexable_checked_eligible: 1,
        } : {}),
      })),
    },
    identity: {
      scan_id: "scan_hist",
      project_id: "project_hist",
      owner_user_id: "user_hist",
      normalized_domain: "funbooker.com",
    },
    userId: "user_hist",
    now: "2026-08-31T10:24:00.000Z",
  });
  const seal = staged ? createStagedAuthoritySeal : createAuthoritySeal;
  const rowsFromSnapshot = staged ? stagedAuthorityRowsFromSnapshot : authorityRowsFromSnapshot;
  const proof = await seal(snapshot, SECRET);
  const rows = rowsFromSnapshot(snapshot, {
    fixListId: "fixlist_hist",
    ownerUserId: "user_hist",
    proof,
  });
  if (published) {
    assert.equal(rows.scanRun.authority_seal_version, "standard_review_snapshot_hmac_identity_v1");
  }
  return {
    run: { id: "scan_hist", project_id: "project_hist", owner_user_id: "user_hist", ...rows.scanRun },
    fixList: { id: "fixlist_hist", ...rows.fixList },
    fixItems: rows.fixItems,
  };
}

function matches(record, query) {
  return Object.entries(query || {}).every(([key, value]) => record?.[key] === value);
}

async function invokeWithFingerprint(fingerprint, {
  active = false, stagedReader, mutateRows = () => {}, callerUserId = "user_hist", signingKey = SECRET,
  notice, paid = true, accessGrant, savedRows, payload = { action: "get", scan_id: "scan_hist" },
} = {}) {
  const invocationId = ++handlerInvocationSequence;
  const harnessName = `__customerHistoricalReaderHarness_${invocationId}`;
  const rows = savedRows ?? await sealedRows(fingerprint, Boolean(stagedReader), notice);
  await mutateRows(rows);
  const access = {
    id: "access_hist",
    owner_user_id: "user_hist",
    user_email: "paid@example.com",
    access_status: "active",
    has_full_access: true,
    plan_id: "standard150_lifetime",
    grant_source: "manual_grant",
    app_id: "6a498732ec779dfaaeab0e53",
    granted_at: "2026-08-31T09:00:00.000Z",
    ...accessGrant,
  };
  const base44 = {
    auth: { me: async () => ({ id: callerUserId, email: "paid@example.com" }) },
    asServiceRole: {
      entities: {
        ScanRun: { get: async (id) => id === rows.run.id ? structuredClone(rows.run) : null },
        BusinessProject: {
          get: async (id) => id === "project_hist"
            ? { id, owner_user_id: "user_hist", website_url: "https://www.funbooker.com/" }
            : null,
        },
        Access: {
          filter: async (query) => paid && matches(access, query) ? [structuredClone(access)] : [],
        },
        FixList: {
          get: async (id) => id === rows.fixList.id ? structuredClone(rows.fixList) : null,
          filter: async () => [structuredClone(rows.fixList)],
        },
        FixItem: {
          filter: async () => structuredClone(rows.fixItems),
        },
      },
    },
  };

  let handler = null;
  const priorDeno = globalThis.Deno;
  globalThis.Deno = {
    env: { get: (name) => name === "SCAN_EVIDENCE_SIGNING_KEY" ? STALE_PROCESS_SECRET : "" },
    serve: (candidate) => { handler = candidate; },
  };
  globalThis[harnessName] = {
    createClientFromRequest: () => base44,
    secrets: { get: (name) => name === "SCAN_EVIDENCE_SIGNING_KEY" ? signingKey : "" },
    buildLimitedResultSnapshot,
    verifyLimitedResultProof,
    authoritySnapshotFromRows,
    buildCustomerProjection,
    buildScanHistoryProjection,
    evaluatePaidAccess,
    recordOwnedByUser,
    verifyAuthoritySeal,
    RELEASE_FINGERPRINT,
    isReadableAuthorityReleaseFingerprint,
    FUNCTION_BUILD_ID,
    ...(active ? {
      ...activeProjection, ...activeLimited, ...activePreview, ...activeCompatibility,
      FUNCTION_BUILD_ID: ACTIVE_FUNCTION_BUILD_ID,
    } : {}),
    ...stagedReader?.modules,
  };

  try {
    await importHandler(harnessName, stagedReader?.entry ?? (active ? activeEntrySource : entrySource));
    assert.equal(typeof handler, "function");
    return await handler(new Request("https://function.example", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    }));
  } finally {
    delete globalThis[harnessName];
    if (priorDeno === undefined) delete globalThis.Deno;
    else globalThis.Deno = priorDeno;
  }
}

async function loadReaderPackage(directory, entry = readFileSync(join(directory, "entry.ts"), "utf8")) {
  const fromReader = file => import(pathToFileURL(join(directory, file)).href);
  return {
    entry,
    modules: {
      ...await fromReader("projection.js"),
      ...await fromReader("limitedResultIntegrity.js"),
      ...await fromReader("customerPreviewSeal.js"),
      ...await fromReader("releaseCompatibility.js"),
      ...await fromReader("generatedReleaseContract.js"),
      ...await fromReader("generatedBuildId.js"),
    },
  };
}

test("the next V9 reader opens prior signed staged results without marking them current", async t => {
  const directory = mkdtempSync(join(tmpdir(), "next-v9-customer-reader-"));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  cpSync("base44/functions/getCustomerScanResultV9", directory, { recursive: true });
  writeFileSync(join(directory, "package.json"), '{"type":"module"}');
  const nextFingerprint = "bbbbbbbbbbbbbbbb";
  const generatedContract = join(directory, "generatedReleaseContract.js");
  writeFileSync(generatedContract, readFileSync(generatedContract, "utf8")
    .replace(/RELEASE_FINGERPRINT = "[a-f0-9]{16}"/, `RELEASE_FINGERPRINT = "${nextFingerprint}"`));
  const nextEntry = readFileSync(join(directory, "entry.ts"), "utf8")
    .replace(/BASE44_HANDLER_RELEASE_FINGERPRINT = "[a-f0-9]{16}"/, `BASE44_HANDLER_RELEASE_FINGERPRINT = "${nextFingerprint}"`);
  const stagedReader = await loadReaderPackage(directory, nextEntry);

  assert.equal(stagedReader.modules.RELEASE_FINGERPRINT, nextFingerprint);
  for (const fingerprint of [PREVIOUS_STAGED_FINGERPRINT, PROTECTED_PLAN_STAGED_FINGERPRINT, PREVIOUS_PILOT_FINGERPRINT]) {
    const response = await invokeWithFingerprint(fingerprint, { stagedReader });
    const body = await response.json();
    assert.equal(response.status, 200, body.error_code);
    assert.equal(body.authority_verified, true);
    assert.equal(body.release_contract_current, false);
    assert.equal(body.run.beta_revision_fingerprint, fingerprint);
    assert.equal(body.run.page_cap, 150);
    assert.equal(body.fixItems[0].recommended_value, "Keep the verified saved instruction.");

    const invalid = await invokeWithFingerprint(fingerprint, { stagedReader, signingKey: "wrong-test-key" });
    assert.equal(invalid.status, 409);
    assert.equal((await invalid.json()).error_code, "result_authority_invalid");
    const otherOwner = await invokeWithFingerprint(fingerprint, { stagedReader, callerUserId: "other_user" });
    assert.equal(otherOwner.status, 404);
    assert.equal((await otherOwner.json()).error_code, "scan_not_found");
  }

  const unknown = await invokeWithFingerprint(UNKNOWN_FINGERPRINT, { stagedReader });
  assert.equal(unknown.status, 503);
  assert.equal((await unknown.json()).error_code, "result_release_mismatch");
});

test("the actual customer reader opens a sealed known-compatible historical release", async () => {
  const response = await invokeWithFingerprint(HISTORICAL_FINGERPRINT);
  const body = await response.json();

  assert.equal(response.status, 200);
  assert.equal(body.success, true);
  assert.equal(body.authority_verified, true);
  assert.equal(body.run.beta_revision_fingerprint, HISTORICAL_FINGERPRINT);
  assert.equal(body.release_contract_current, false);
});

test("the actual customer reader rejects an unknown release before treating it as authority", async () => {
  const response = await invokeWithFingerprint(UNKNOWN_FINGERPRINT);
  const body = await response.json();

  assert.equal(response.status, 503);
  assert.equal(body.success, false);
  assert.equal(body.error_code, "result_release_mismatch");
});

for (const active of [false, true]) {
  const route = active ? "active V8" : "canonical";
  test(`${route} reader preserves sealed prior-current results after the candidate advances`, async () => {
    assert.notEqual(RELEASE_FINGERPRINT, PREVIOUS_CURRENT_FINGERPRINT);
    const response = await invokeWithFingerprint(PREVIOUS_CURRENT_FINGERPRINT, { active });
    const body = await response.json();
    assert.equal(response.status, 200);
    assert.equal(body.success, true);
    assert.equal(body.authority_verified, true);
    assert.equal(body.run.beta_revision_fingerprint, PREVIOUS_CURRENT_FINGERPRINT);
    assert.equal(body.release_contract_current, false);
    assert.equal(body.fixItems.length, 1);
    assert.equal(body.fixItems[0].recommended_value, "Keep the verified saved instruction.");
  });

  for (const [label, options, status, code] of [
    ["unknown release", {}, 503, "result_release_mismatch"],
    ["another owner", { callerUserId: "other_user" }, 404, "scan_not_found"],
    ["missing signing key", { signingKey: "" }, 503, "result_authority_unavailable"],
    ["wrong signing key", { signingKey: "incorrect-test-key" }, 409, "result_authority_invalid"],
    ["changed signed score", { mutateRows: (rows) => { rows.run.health_score = 99; } }, 409, "result_authority_invalid"],
    ["changed FixList identity", { mutateRows: (rows) => { rows.fixList.project_id = "other_project"; } }, 409, "fix_list_mismatch"],
    ["changed FixItem identity", { mutateRows: (rows) => { rows.fixItems[0].scan_run_id = "other_scan"; } }, 409, "fix_items_mismatch"],
    ["missing FixItem", { mutateRows: (rows) => { rows.fixItems = []; } }, 409, "fix_items_incomplete"],
    ["changed saved instruction", { mutateRows: (rows) => { rows.fixItems[0].recommended_value = "Unsigned replacement"; } }, 409, "result_authority_invalid"],
  ]) {
    test(`${route} historical read still rejects ${label}`, async () => {
      const fingerprint = label === "unknown release" ? UNKNOWN_FINGERPRINT : PREVIOUS_CURRENT_FINGERPRINT;
      const response = await invokeWithFingerprint(fingerprint, { active, ...options });
      const body = await response.json();
      assert.equal(response.status, status);
      assert.equal(body.success, false);
      assert.equal(body.error_code, code);
      assert.equal(body.authority_verified, undefined);
      assert.equal(body.fixItems, undefined, "rejected reads must not expose saved findings");
    });
  }
}

const currentStagedReader = {
  entry: readFileSync("base44/functions/getCustomerScanResultV9/entry.ts", "utf8"),
  modules: { ...stagedProjection, ...stagedLimited, ...stagedPreview, ...stagedCompatibility, ...stagedRelease, ...stagedBuild },
};

async function readStagedNotice(options = {}) {
  const response = await invokeWithFingerprint(PREVIOUS_STAGED_FINGERPRINT, { stagedReader: currentStagedReader, ...options });
  return { response, body: await response.json() };
}

test("the actual V9 reader discloses authenticated skipped checks without changing result authority", async () => {
  for (const reason of ["site_rate_limited", "repeat_requests_avoided"]) {
    const { response, body } = await readStagedNotice({ notice: reason });
    assert.equal(response.status, 200, body.error_code);
    assert.equal(body.authority_verified, true);
    assert.equal(body.run.status, "complete");
    assert.equal(body.run.health_score, 48);
    assert.notEqual(body.run.score_is_provisional, true);
    assert.equal(body.run.optional_checks_notice_reason, reason);
    assert.equal(body.fixItems.length, 1);
    assert.ok(scanPresentation.optionalChecksNotice({ ...body.run, authority_verified: body.authority_verified }));
  }

  for (const reason of [undefined, "unknown_unpublished_reason"]) {
    const { response, body } = await readStagedNotice({
      notice: reason,
      mutateRows: rows => { rows.run.optional_checks_notice_reason = "site_rate_limited"; },
    });
    assert.equal(response.status, 200);
    assert.equal(body.authority_verified, true);
    assert.equal(Object.hasOwn(body.run, "optional_checks_notice_reason"), false);
    assert.equal(scanPresentation.optionalChecksNotice({ ...body.run, authority_verified: true }), "");
  }
});

test("changing a signed V9 skipped-check reason invalidates its full authority", async () => {
  const { response, body } = await readStagedNotice({
    notice: "site_rate_limited",
    mutateRows: rows => { rows.run.crawl_timing.optional_checks_notice_reason = "repeat_requests_avoided"; },
  });
  assert.equal(response.status, 409);
  assert.equal(body.error_code, "result_authority_invalid");
});

test("V9 reports a timed-out crawl only with authenticated unfinished coverage", async () => {
  for (const [pages, timing, legacySeal, tampered, expected] of [
    [71, { crawl_deadline_reached: true, queue_exhausted: false, final_queue_size: 1128 }, false, false, "time_limit"],
    [150, { crawl_deadline_reached: true, queue_exhausted: false, final_queue_size: 1128 }, false, false, undefined],
    [71, { crawl_deadline_reached: true, queue_exhausted: true, final_queue_size: 0 }, false, false, undefined],
    [71, { crawl_deadline_reached: true, queue_exhausted: false, final_queue_size: 1128 }, true, false, undefined],
    [71, { crawl_deadline_reached: false, queue_exhausted: false, final_queue_size: 1128 }, false, true, undefined],
  ]) {
    const response = await invokeWithFingerprint(PREVIOUS_PILOT_FINGERPRINT, {
      stagedReader: currentStagedReader,
      mutateRows: async rows => {
        rows.run.pages_crawled = pages;
        rows.run.crawl_timing = timing;
        if (legacySeal) rows.run.authority_seal_version = "standard_review_snapshot_hmac_v1";
        const snapshot = stagedProjection.authoritySnapshotFromRows({ ...rows, userId: rows.run.owner_user_id });
        const proof = await createStagedAuthoritySeal(snapshot, SECRET);
        for (const row of [rows.run, rows.fixList, ...rows.fixItems]) row.authority_proof = proof;
        if (tampered) rows.run.crawl_timing = { ...timing, crawl_deadline_reached: true };
      },
    });
    const body = await response.json();
    assert.equal(response.status, tampered ? 409 : 200, body.error_code);
    if (tampered) assert.equal(body.error_code, "result_authority_invalid");
    else assert.equal(body.run.crawl_stop_reason, expected);
  }
});

test("unsigned v1 timing cannot create a V9 skipped-check notice", async () => {
  const { response, body } = await readStagedNotice({
    mutateRows: async rows => {
      rows.run.authority_seal_version = "standard_review_snapshot_hmac_v1";
      const historical = stagedProjection.authoritySnapshotFromRows({ ...rows, userId: rows.run.owner_user_id });
      assert.equal(Object.hasOwn(historical.scan, "crawl_timing"), false);
      const proof = await createStagedAuthoritySeal(historical, SECRET);
      for (const row of [rows.run, rows.fixList, ...rows.fixItems]) row.authority_proof = proof;
      rows.run.crawl_timing = { optional_checks_notice_reason: "site_rate_limited" };
    },
  });
  assert.equal(response.status, 200, body.error_code);
  assert.equal(body.authority_verified, true);
  assert.equal(Object.hasOwn(body.run, "optional_checks_notice_reason"), false);
  assert.equal(Object.hasOwn(body.run.crawl_timing, "optional_checks_notice_reason"), false);
});

test("signed V9 previews carry only the bounded notice and reject a modified reason", async () => {
  for (const tamper of [false, true]) {
    const { response, body } = await readStagedNotice({
      notice: "site_rate_limited", paid: false,
      mutateRows: async rows => {
        const snapshot = stagedProjection.authoritySnapshotFromRows({ ...rows, userId: rows.run.owner_user_id });
        assert.equal(await stagedProjection.verifyAuthoritySeal(snapshot, SECRET, rows.run.authority_proof), true);
        const payload = buildStagedPreviewPayload({
          ...rows, ownerUserId: rows.run.owner_user_id, fullAuthorityProof: rows.run.authority_proof,
          verifiedOptionalChecksNoticeReason: snapshot.scan.crawl_timing.optional_checks_notice_reason,
        });
        rows.run.customer_preview_seal_version = stagedPreview.CUSTOMER_PREVIEW_SEAL_VERSION;
        rows.run.customer_preview_sealed_at = rows.run.authority_sealed_at;
        rows.run.customer_preview_proof = await createStagedPreviewProof(payload, SECRET);
        if (tamper) payload.run.optional_checks_notice_reason = "repeat_requests_avoided";
        rows.run.customer_preview_payload = serializeStagedPreviewPayload(payload);
      },
    });
    if (tamper) {
      assert.equal(response.status, 409);
      assert.equal(body.error_code, "result_preview_invalid");
    } else {
      assert.equal(response.status, 200, body.error_code);
      assert.equal(body.access, "preview");
      assert.equal(body.run.optional_checks_notice_reason, "site_rate_limited");
      assert.equal(Object.hasOwn(body.run, "crawl_timing"), false);
    }
  }
});

test("reopening historical b36 reports through the customer frontend", async t => {
  const temp = mkdtempSync(join(tmpdir(), "historical-saved-report-"));
  t.after(() => rmSync(temp, { recursive: true, force: true }));
  writeFileSync(join(temp, "package.json"), '{"type":"module"}');
  const candidate = join(temp, "candidate");
  materializeStagedV9Packages(process.cwd(), candidate);
  const v8 = "getCustomerScanResultV8";
  const v9 = stagedDeployments.functions.getCustomerScanResultV9.route_name;
  const readers = {
    [v8]: await loadReaderPackage(join("base44/functions", v8)),
    [v9]: await loadReaderPackage(join(candidate, "base44/functions", v9)),
  };

  async function read(rows, options = {}) {
    const routes = [];
    const attempts = [];
    let body;
    let status;
    const client = loadSavedReportClient(async (route, payload) => {
      assert.ok(Object.hasOwn(readers, route), route);
      assert.deepEqual(payload, { scan_id: rows.run.id });
      routes.push(route);
      const response = await invokeWithFingerprint(rows.run.beta_revision_fingerprint, {
        ...options, savedRows: rows, payload, stagedReader: readers[route],
        accessGrant: {
          grant_source: "stripe_checkout",
          stripe_checkout_session_id: "cs_test_local_historical",
          paid_at: "2026-08-31T09:00:00.000Z",
        },
      });
      status = response.status;
      body = await response.clone().json();
      attempts.push([status, body.error_code]);
      return response;
    }, { userId: options.callerUserId, generation: options.generation });
    const original = structuredClone(rows);
    const result = await savedReportReader(client)(rows.run.id);
    assert.deepEqual(rows, original, "reopening must preserve the persisted rows and proofs");
    return { body, status, routes, attempts, result };
  }

  const rows = await sealedRows(PREVIOUS_PILOT_FINGERPRINT, true, undefined, { findings: [
    headingFinding,
    { fix_id: "fix_hist_2", rule: "missing_title", issue_title: "Review this page title" },
    { fix_id: "fix_hist_3", rule: "missing_description", issue_title: "Review this description" },
  ] });
  const preview = buildStagedPreviewPayload({
    ...rows, ownerUserId: rows.run.owner_user_id, fullAuthorityProof: rows.run.authority_proof,
  });
  rows.run.customer_preview_seal_version = stagedPreview.CUSTOMER_PREVIEW_SEAL_VERSION;
  rows.run.customer_preview_sealed_at = rows.run.authority_sealed_at;
  rows.run.customer_preview_proof = await createStagedPreviewProof(preview, SECRET);
  rows.run.customer_preview_payload = serializeStagedPreviewPayload(preview);

  // The b36 writer at 743aa8786d31c1a2417e852c40b808d687d16337 produced
  // these proofs from the same synthetic inputs and local signing key.
  assert.equal(rows.run.authority_proof, "37ba8ec73a65935e45ea12aae0a516c848d8ecbbaaef352baa64c8f57c1eb6e7");
  assert.equal(rows.run.customer_preview_proof, "1e509fbf5528d70a5236b7ddc76da9378d3e307601e7e79830e5bb67de39218e");

  await t.test("the published pilot verifies the full report on its first V9 read", async () => {
    const { attempts, routes, result } = await read(rows, { generation: "PUBLISHED_PILOT" });
    assert.deepEqual(routes, [v9]);
    assert.deepEqual(attempts, [[200, undefined]]);
    assert.equal(result.ok, true, result.kind);
    assert.equal(result.access, "full");
    assert.equal(result.authority_verified, true);
    assert.equal(result.scan_id, rows.run.id);
    assert.equal(result.fix_list_id, rows.fixList.id);
    assert.equal(result.run.health_score, rows.run.health_score);
    assert.deepEqual(result.fixItems.map(item => item.fix_id), rows.fixItems.map(item => item.fix_id));
  });

  for (const paid of [true, false]) {
    const access = paid ? "full" : "preview";
    await t.test(`complete report preserves its signed ${access} projection`, async () => {
      const { body, routes, attempts, result } = await read(rows, { paid });
      assert.deepEqual(routes, [v8, v9]);
      assert.deepEqual(attempts, [[503, "result_release_mismatch"], [200, undefined]]);
      assert.equal(body.release_contract_current, false);
      assert.equal(result.ok, true, result.kind);
      assert.equal(result.access, access);
      assert.equal(result.authority_verified, true);
      assert.equal(result.scan_id, rows.run.id);
      assert.equal(result.fix_list_id, rows.fixList.id);
      assert.equal(result.run.project_id, rows.run.project_id);
      assert.equal(preview.run.beta_revision_fingerprint, PREVIOUS_PILOT_FINGERPRINT);
      assert.equal(result.run.beta_revision_fingerprint, paid ? PREVIOUS_PILOT_FINGERPRINT : undefined);
      assert.equal(result.run.health_score, 48);
      assert.equal(result.run.pages_crawled, 150);
      assert.equal(result.fixList.total_fixes, 3);
      for (const field of ["critical_count", "high_count", "medium_count", "low_count"]) {
        assert.equal(result.fixList[field], rows.fixList[field], field);
      }
      const expectedItems = paid ? rows.fixItems : preview.fixItems;
      assert.equal(expectedItems.length, paid ? 3 : 2);
      assert.deepEqual(result.fixItems.map(item => item.fix_id), expectedItems.map(item => item.fix_id));
      for (const [index, item] of result.fixItems.entries()) {
        assert.equal(item.recommended_value, expectedItems[index].recommended_value);
        if (paid) assert.deepEqual(item.affected_pages, expectedItems[index].affected_pages);
        else {
          assert.equal(item.preview_example_page, expectedItems[index].preview_example_page);
          assert.equal(Object.hasOwn(item, "affected_pages"), false);
          assert.equal(Object.hasOwn(item, "project_id"), false);
        }
      }
    });
  }

  await t.test("a signed report with no recorded cap reopens with no inferred tier", async () => {
    const saved = await sealedRows(PREVIOUS_PILOT_FINGERPRINT, true, undefined, { savedCap: null });
    assert.equal(saved.run.authority_proof, "87173132d5b98fe79ca51f37d4968dc81fec5a727ce169ba29e5ec0397074669");
    assert.equal(Object.hasOwn(saved.run, "page_cap"), false);
    const { attempts, routes, result } = await read(saved);
    assert.deepEqual(routes, [v8, v9]);
    assert.deepEqual(attempts, [[503, "result_release_mismatch"], [200, undefined]]);
    assert.equal(result.ok, true, result.kind);
    assert.equal(result.authority_verified, true);
    assert.equal(result.run.id, saved.run.id);
    assert.equal(result.run.health_score, saved.run.health_score);
    assert.equal(Object.hasOwn(result.run, "page_cap"), false);
    assert.notEqual(result.run.scan_mode, "standard_500");
  });

  await t.test("the pilot reads a historical 500-page allowance and the original 150 checked pages", async () => {
    const saved = await sealedRows(PREVIOUS_PILOT_FINGERPRINT, true, undefined, { savedCap: 500 });
    assert.equal(saved.run.authority_proof, "5ef27e35c886cb15fc1dab395b0908c275e071953b83d104285e116b55f9ce44");
    const { routes, result } = await read(saved, { generation: "PUBLISHED_PILOT" });
    assert.deepEqual(routes, [v9]);
    assert.equal(result.ok, true, result.kind);
    assert.equal(result.authority_verified, true);
    assert.equal(result.run.scan_mode, "standard_500");
    assert.equal(result.run.page_cap, 500);
    assert.equal(result.run.pages_crawled, 150);
    assert.equal(result.fixList.total_fixes, saved.fixList.total_fixes);
    assert.equal(result.run.health_score, saved.run.health_score);
  });

  for (const [label, options, mutate, expectedRoutes, expectedStatus, code, kind] of [
    ["another owner", { callerUserId: "other_user" }, () => {}, [v8], 404, "scan_not_found", "not_found"],
    ["altered finding", {}, saved => { saved.fixItems[0].recommended_value = "Unsigned replacement"; },
      [v8, v9], 409, "result_authority_invalid", "authority_invalid"],
    ["altered preview score", { paid: false }, saved => {
      const changed = JSON.parse(saved.run.customer_preview_payload);
      changed.run.health_score = 99;
      saved.run.customer_preview_payload = serializeStagedPreviewPayload(changed);
    }, [v8, v9], 409, "result_preview_invalid", "authority_invalid"],
  ]) {
    await t.test(`rejects ${label} without returning saved findings`, async () => {
      const saved = structuredClone(rows);
      mutate(saved);
      const { body, status, routes, result } = await read(saved, options);
      assert.deepEqual(routes, expectedRoutes);
      assert.equal(status, expectedStatus);
      assert.equal(body.error_code, code);
      assert.equal(body.fixItems, undefined);
      assert.equal(result.ok, false);
      assert.equal(result.kind, kind);
      assert.equal(result.fixItems, undefined);
    });
  }

  await t.test("limited report preserves its original integrity boundary", () => checkHistoricalLimitedReopen(read));
});
