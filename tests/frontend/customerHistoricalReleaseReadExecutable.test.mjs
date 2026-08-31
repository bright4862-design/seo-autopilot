import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

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

const entrySource = readFileSync("base44/functions/getCustomerScanResult/entry.ts", "utf8");
const SECRET = "historical-reader-test-secret-never-deployed";
const HISTORICAL_FINGERPRINT = "5d94e93c54a9efb6";
const UNKNOWN_FINGERPRINT = "aaaaaaaaaaaaaaaa";
let handlerInvocationSequence = 0;

async function importHandler(harnessName) {
  const javascript = ts.transpileModule(entrySource, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  }).outputText.replace(/^import[\s\S]*?;\s*$/gm, "");
  const prelude = `const {
    createClientFromRequest,
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
  } = globalThis.${harnessName};`;
  await import(`data:text/javascript;base64,${Buffer.from(`${prelude}\n${javascript}\n// harness:${harnessName}`).toString("base64")}`);
}

async function sealedRows(fingerprint) {
  const snapshot = buildAuthoritySnapshot({
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
      crawl_timing: { queue_exhausted: false, sitemap_fetch_count: 1 },
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
      recommendations: [],
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
  const proof = await createAuthoritySeal(snapshot, SECRET);
  const rows = authorityRowsFromSnapshot(snapshot, {
    fixListId: "fixlist_hist",
    ownerUserId: "user_hist",
    proof,
  });
  return {
    run: { id: "scan_hist", project_id: "project_hist", owner_user_id: "user_hist", ...rows.scanRun },
    fixList: { id: "fixlist_hist", ...rows.fixList },
    fixItems: rows.fixItems,
  };
}

function matches(record, query) {
  return Object.entries(query || {}).every(([key, value]) => record?.[key] === value);
}

async function invokeWithFingerprint(fingerprint) {
  const invocationId = ++handlerInvocationSequence;
  const harnessName = `__customerHistoricalReaderHarness_${invocationId}`;
  const rows = await sealedRows(fingerprint);
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
  };
  const base44 = {
    auth: { me: async () => ({ id: "user_hist", email: "paid@example.com" }) },
    asServiceRole: {
      entities: {
        ScanRun: { get: async (id) => id === rows.run.id ? structuredClone(rows.run) : null },
        BusinessProject: {
          get: async (id) => id === "project_hist"
            ? { id, owner_user_id: "user_hist", website_url: "https://www.funbooker.com/" }
            : null,
        },
        Access: {
          filter: async (query) => matches(access, query) ? [structuredClone(access)] : [],
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
    env: { get: (name) => name === "SCAN_EVIDENCE_SIGNING_KEY" ? SECRET : "" },
    serve: (candidate) => { handler = candidate; },
  };
  globalThis[harnessName] = {
    createClientFromRequest: () => base44,
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
  };

  try {
    await importHandler(harnessName);
    assert.equal(typeof handler, "function");
    return await handler(new Request("https://function.example", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action: "get", scan_id: "scan_hist" }),
    }));
  } finally {
    delete globalThis[harnessName];
    if (priorDeno === undefined) delete globalThis.Deno;
    else globalThis.Deno = priorDeno;
  }
}

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
