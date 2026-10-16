import assert from "node:assert/strict";
import test from "node:test";

import {
  BLUEPRINT_30_SITE_GATE_VERSION,
  evaluateBlueprint30SiteGate,
  loadBlueprint30SiteRoster,
} from "../../scripts/assertBlueprint30SiteGate.mjs";

const BASELINE_SHA = "1".repeat(40);
const CANDIDATE_SHA = "3".repeat(40);
const HEX64 = "2".repeat(64);
const FINGERPRINT = "0123456789abcdef";

function artifact(label, kind) {
  const baseline = kind === "baseline";
  return {
    provenance: "captured",
    artifact_sha256: HEX64,
    source_sha: baseline ? BASELINE_SHA : CANDIDATE_SHA,
    release_fingerprint: FINGERPRINT,
    captured_at: baseline ? "2026-09-19T18:00:00Z" : "2026-09-19T18:30:00Z",
    scan_mode: "standard_150",
    scope: "/",
    policy_id: "standard150-production-policy-v1",
    evidence_bundle_id: `${label}-bundle`,
  };
}

function pair(row, { newArtifacts = [] } = {}) {
  return {
    site_id: row.site,
    url: row.url,
    stratum: row.stratum,
    baseline: artifact(`${row.site}-baseline`, "baseline"),
    candidate: artifact(`${row.site}-candidate`, "candidate"),
    difference_summary: { new_artifact_ids: newArtifacts },
    adjudications: [],
  };
}

function record(overrides = {}) {
  const roster = loadBlueprint30SiteRoster();
  return {
    version: BLUEPRINT_30_SITE_GATE_VERSION,
    roster_sha256: roster.sha256,
    provenance: "captured_baseline_candidate",
    generated_at: "2026-09-19T19:00:00Z",
    pairs: roster.rows.map((row) => pair(row)),
    ...overrides,
  };
}

test("the tracked renderer roster alone can never satisfy the full gate", () => {
  const roster = loadBlueprint30SiteRoster();
  assert.equal(roster.rows.length, 30);
  const result = evaluateBlueprint30SiteGate({
    version: BLUEPRINT_30_SITE_GATE_VERSION,
    roster_sha256: roster.sha256,
    provenance: "historical_summary",
    generated_at: "2026-09-19T19:00:00Z",
    pairs: [],
  });
  assert.equal(result.status, "not_assessed");
  assert.equal(result.pass, false);
  assert.ok(result.blockers.some((value) => value.includes("provenance")));
  assert.ok(result.blockers.some((value) => value.includes("30 paired sites")));
});

test("test-fixture pairs are explicitly not assessed even when all 30 captured shapes are otherwise valid", () => {
  const result = evaluateBlueprint30SiteGate(record({ test_fixture: true }));
  assert.equal(result.status, "not_assessed");
  assert.equal(result.pass, false);
  assert.equal(result.site_count, 30);
  assert.deepEqual(result.failures, [], "the synthetic structural fixture should be valid apart from its non-live provenance blocker");
  assert.ok(result.blockers.some((value) => value.includes("test fixtures")));
});

test("a partial captured cohort remains not assessed instead of becoming a small-sample pass", () => {
  const full = record();
  const result = evaluateBlueprint30SiteGate({ ...full, pairs: full.pairs.slice(0, 29) });
  assert.equal(result.status, "not_assessed");
  assert.equal(result.pass, false);
  assert.equal(result.site_count, 29);
});

test("baseline and candidate must be distinct ordered captures under the same scope/policy", () => {
  const full = record();
  const pair0 = full.pairs[0];
  pair0.candidate.source_sha = pair0.baseline.source_sha;
  pair0.candidate.evidence_bundle_id = pair0.baseline.evidence_bundle_id;
  pair0.candidate.captured_at = "2026-09-19T17:59:59Z";
  pair0.candidate.scope = "/different";
  pair0.candidate.policy_id = "different-policy";
  const result = evaluateBlueprint30SiteGate(full);
  assert.equal(result.status, "failed");
  for (const fragment of ["source SHA is identical", "evidence bundle id is identical", "predates baseline", "scope differs", "policy differs"]) {
    assert.ok(result.failures.some((value) => value.includes(fragment)), fragment);
  }
});

test("every new candidate artifact requires explicit evidence-backed adjudication", () => {
  const full = record();
  full.pairs[0] = pair(loadBlueprint30SiteRoster().rows[0], { newArtifacts: ["repair:new-rule"] });
  const result = evaluateBlueprint30SiteGate(full);
  assert.equal(result.status, "failed");
  assert.equal(result.pass, false);
  assert.ok(result.failures.some((value) => value.includes("has no adjudication")));
});

test("unresolved or regression adjudications fail the gate", () => {
  const full = record();
  const first = loadBlueprint30SiteRoster().rows[0];
  full.pairs[0] = {
    ...pair(first, { newArtifacts: ["repair:new-rule"] }),
    adjudications: [{
      artifact_id: "repair:new-rule",
      outcome: "unresolved",
      evidence_reference: "capture://example/repair-new-rule",
      reviewed_by: "independent-reviewer",
      reviewed_at: "2026-09-19T19:10:00Z",
    }],
  };
  const result = evaluateBlueprint30SiteGate(full);
  assert.equal(result.status, "failed");
  assert.ok(result.failures.some((value) => value.includes("adjudication is unresolved")));
});
