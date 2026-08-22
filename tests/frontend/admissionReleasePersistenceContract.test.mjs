import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { buildAuthoritySnapshot } from "../../base44/functions/persistDurableScanAuthority/authoritySnapshot.js";
import { persistExactAdmissionRelease } from "../../base44/functions/persistDurableScanAuthority/admissionRelease.js";
import { buildLimitedResultSnapshot } from "../../base44/functions/persistLimitedScanResult/limitedResultIntegrity.js";

const schema = JSON.parse(readFileSync("base44/entities/ScanRun.jsonc", "utf8"));
const completion = readFileSync("base44/functions/persistDurableScanAuthority/index.ts", "utf8");
const releaseHelper = readFileSync("base44/functions/persistDurableScanAuthority/admissionRelease.js", "utf8");
const limitedWriter = readFileSync("base44/functions/persistLimitedScanResult/index.ts", "utf8");

test("ScanRun exposes server-owned durable admission release state without reusing Access provenance", () => {
  const properties = schema.properties;
  assert.deepEqual(properties.admission_release_state.enum, [
    "pending",
    "released",
    "superseded",
    "satisfied_unbound",
  ]);
  for (const field of [
    "admission_barrier_generation",
    "admission_claim_sequence",
    "admission_mode",
    "admission_acceptance_cohort_id",
    "admission_acceptance_release_id",
    "admission_acceptance_source_sha",
    "admission_acceptance_expires_at",
    "admission_cohort_evidence_version",
    "admission_cohort_evidence_proof",
    "admission_release_state",
    "admission_release_reconciled_at",
    "admission_release_last_attempt_at",
    "admission_release_coordinator_request_id",
    "admission_release_outcome",
    "admission_release_failure_code",
  ]) {
    assert.equal(properties[field].rls.write.user_condition.role, "admin", `${field} must be server-owned`);
  }
  assert.match(properties.admission_access_id.description, /entitlement provenance/i);
  assert.doesNotMatch(properties.admission_access_id.description, /lease record/i);
});

test("normal authoritative completion persists only exact coordinator release outcomes", () => {
  assert.match(completion, /persistExactAdmissionRelease/);
  assert.match(releaseHelper, /released["']\s*,\s*["']already_released/);
  assert.match(releaseHelper, /admission_release_state/);
  assert.doesNotMatch(completion, /admission_release_state\s*:\s*["']superseded/);
});

test("limited completion also persists an exact release and never treats HTTP success alone as proof", () => {
  assert.match(limitedWriter, /persistLimitedAdmissionRelease/);
  assert.match(limitedWriter, /barrier_generation/);
  assert.match(limitedWriter, /claim_sequence/);
  assert.match(limitedWriter, /admission_release_state:\s*"pending"/);
  assert.match(limitedWriter, /admission_release_state:\s*"released"/);
  assert.match(limitedWriter, /RELEASE_COMPONENT_VERSIONS\.admission_reconciliation_version/);
});

function releaseRow(overrides = {}) {
  return {
    id: "scan_123456",
    owner_user_id: "owner_123456",
    request_id: "request_123456",
    idempotency_key: "request_123456",
    attempt_count: 2,
    admission_barrier_generation: 4,
    admission_claim_sequence: 23,
    status: "complete",
    admission_access_id: "access_123456",
    admission_release_state: "pending",
    ...overrides,
  };
}

function fakeEntities(initial, { beforeGet } = {}) {
  let row = structuredClone(initial);
  let gets = 0;
  return {
    get row() { return structuredClone(row); },
    ScanRun: {
      async get() {
        gets += 1;
        if (beforeGet) row = beforeGet(structuredClone(row), gets) || row;
        return structuredClone(row);
      },
      async update(_id, fields) {
        row = { ...row, ...structuredClone(fields) };
        return structuredClone(row);
      },
    },
  };
}

test("an exact released generation is fenced, persisted, and verified", async () => {
  const entities = fakeEntities(releaseRow());
  const result = await persistExactAdmissionRelease({
    entities,
    scan: entities.row,
    terminalStatus: "complete",
    release: async () => ({
      ok: true,
      outcome: "released",
      request_id: "request_123456",
      scan_id: "scan_123456",
      barrier_generation: 4,
      claim_sequence: 23,
    }),
    now: () => "2026-08-21T00:01:00.000Z",
  });
  assert.equal(result.ok, true);
  assert.equal(entities.row.admission_release_state, "released");
  assert.equal(entities.row.admission_release_coordinator_request_id, "request_123456");
  assert.equal(entities.row.admission_release_failure_code, "");
});

test("a successful response for another coordinator generation remains pending", async () => {
  const entities = fakeEntities(releaseRow());
  const result = await persistExactAdmissionRelease({
    entities,
    scan: entities.row,
    terminalStatus: "complete",
    release: async () => ({
      ok: true,
      outcome: "released",
      request_id: "request_newer",
      scan_id: "scan_newer",
      barrier_generation: 5,
      claim_sequence: 24,
    }),
    now: () => "2026-08-21T00:01:00.000Z",
  });
  assert.equal(result.ok, false);
  assert.equal(result.failureCode, "admission_release_identity_conflict");
  assert.equal(entities.row.admission_release_state, "pending");
});

test("a release response missing monotonic generation evidence is not accepted", async () => {
  const entities = fakeEntities(releaseRow());
  const result = await persistExactAdmissionRelease({
    entities,
    scan: entities.row,
    terminalStatus: "complete",
    release: async () => ({
      ok: true,
      outcome: "already_released",
      request_id: "request_123456",
      scan_id: "scan_123456",
      barrier_generation: 4,
    }),
    now: () => "2026-08-21T00:01:00.000Z",
  });
  assert.equal(result.ok, false);
  assert.equal(result.failureCode, "admission_release_identity_conflict");
  assert.equal(entities.row.admission_release_state, "pending");
});

test("an upstream body cannot become a durable failure code", async () => {
  const entities = fakeEntities(releaseRow());
  const result = await persistExactAdmissionRelease({
    entities,
    scan: entities.row,
    terminalStatus: "complete",
    release: async () => ({
      ok: false,
      failureCode: "token=secret value\nresponse body",
      outcomeUnknown: true,
    }),
  });
  assert.equal(result.ok, false);
  assert.equal(entities.row.admission_release_state, "pending");
  assert.equal(entities.row.admission_release_failure_code, "admission_release_failed");
  assert.doesNotMatch(entities.row.admission_release_failure_code, /token|secret|[=\s]/);
});

test("a newer attempt appearing after release cannot receive the satisfaction marker", async () => {
  const entities = fakeEntities(releaseRow(), {
    beforeGet(row, gets) {
      return gets === 1 ? { ...row, attempt_count: 3 } : row;
    },
  });
  const result = await persistExactAdmissionRelease({
    entities,
    scan: entities.row,
    terminalStatus: "complete",
    release: async () => ({
      ok: true,
      outcome: "released",
      request_id: "request_123456",
      scan_id: "scan_123456",
      barrier_generation: 4,
      claim_sequence: 23,
    }),
  });
  assert.equal(result.ok, false);
  assert.equal(result.failureCode, "admission_release_scan_changed");
  assert.equal(entities.row.admission_release_state, "pending");
});

test("post-seal admission reconciliation metadata is outside the authority HMAC snapshot", () => {
  const scan = {
    submitted_url: "https://example.com/",
    scanner_version: "python_scanner_v3_bounded_request",
    scanner_build_revision: "authenticated_health_probe_v1",
    pages_found: 12,
    pages_crawled: 12,
  };
  const review = {
    archetype_classifier_version: "archetype_classifier_v9_local_business_hospitality",
    review_version: "python_review_v2_structural_marketplace",
    review_evidence_calibration_version: "review_evidence_calibration_v6_health_score_v2",
    beta_revision_fingerprint: "fingerprint",
    ai_review_backend: "python_review_api",
    release_gate_eligible: true,
    recommendations: [],
  };
  const identity = {
    scan_id: "scan_123456",
    project_id: "project_123456",
    normalized_domain: "example.com",
  };
  const baseline = buildAuthoritySnapshot({ scan, review, identity, userId: "owner_123456", now: "2026-08-21T00:00:00Z" });
  const changed = buildAuthoritySnapshot({
    scan: {
      ...scan,
      admission_release_state: "released",
      admission_release_reconciled_at: "2026-08-21T00:01:00Z",
      admission_release_last_attempt_at: "2026-08-21T00:01:00Z",
      admission_release_coordinator_request_id: "request_123456",
      admission_release_outcome: "already_released",
      admission_release_failure_code: "",
    },
    review,
    identity,
    userId: "owner_123456",
    now: "2026-08-21T00:00:00Z",
  });
  assert.deepEqual(changed, baseline);
});

test("post-seal admission reconciliation metadata is outside the limited-result HMAC snapshot", () => {
  const input = {
    identity: {
      scan_id: "scan_123456",
      project_id: "project_123456",
      owner_user_id: "owner_123456",
      request_id: "request_123456",
      attempt_count: 1,
      normalized_domain: "example.com",
    },
    scan: {
      submitted_url: "https://example.com/",
      scanner_version: "python_scanner_v3_bounded_request",
      beta_revision_fingerprint: "fingerprint",
      pages_found: 100,
      pages_crawled: 5,
    },
    review: {
      scan_status: "limited",
      coverage_state: "limited_coverage",
      coverage_reasons: ["access_limited"],
      recommendations: [{ fix_id: "fix_1", issue_title: "Verify access", priority: "high" }],
    },
    now: "2026-08-21T00:00:00Z",
  };
  const baseline = buildLimitedResultSnapshot(input);
  const changed = buildLimitedResultSnapshot({
    ...input,
    scan: {
      ...input.scan,
      admission_release_state: "released",
      admission_release_reconciled_at: "2026-08-21T00:01:00Z",
      admission_release_coordinator_request_id: "request_123456",
      admission_reconciliation_version: "admission_reconciliation_v1_exact_generation_barrier",
    },
  });
  assert.deepEqual(changed, baseline);
});
