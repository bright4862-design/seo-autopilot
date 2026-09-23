import assert from "node:assert/strict";
import test from "node:test";

import { buildImplementationPlan } from "../../src/lib/implementationPlan.js";

const TRUSTED_SCAN_ID = "scan:dependency-alias-hardening";
const TABLE_VERSION = "test_dependencies_v1";

function verifiedRoot() {
  return {
    version: "root_cause_evidence_v1_verified",
    state: "verified",
    root_cause_id: "root:dependency-alias-hardening",
    evidence_refs: ["observation:dependency-alias-hardening"],
  };
}

function pair() {
  const root = verifiedRoot();
  return [
    {
      fix_id: "sitemap",
      rule: "sitemap_redirect",
      action_priority: "fix_first",
      root_cause_evidence: root,
      scan_id: TRUSTED_SCAN_ID,
    },
    {
      fix_id: "redirect",
      rule: "redirect_chain",
      action_priority: "important",
      root_cause_evidence: root,
      scan_id: TRUSTED_SCAN_ID,
    },
  ];
}

function edge(overrides = {}) {
  return {
    tableVersion: TABLE_VERSION,
    id: "redirect_before_sitemap",
    beforeRule: "redirect_chain",
    afterRule: "sitemap_redirect",
    requires: "verified_shared_root_cause",
    rationale: "test",
    ...overrides,
  };
}

function plan(dependencyEdges) {
  return buildImplementationPlan(pair(), {
    trustedScanId: TRUSTED_SCAN_ID,
    dependencyTableVersion: TABLE_VERSION,
    dependencyEdges,
  });
}

test("conflicting dependency table aliases fail closed", () => {
  const actual = plan([edge({ table_version: "other_dependencies_v1" })]);
  assert.deepEqual(actual.orderedRepairIds, ["sitemap", "redirect"]);
  assert.deepEqual(actual.appliedDependencies, []);
});

test("blank dependency table sibling alias fails closed", () => {
  const actual = plan([edge({ table_version: "   " })]);
  assert.deepEqual(actual.orderedRepairIds, ["sitemap", "redirect"]);
  assert.deepEqual(actual.appliedDependencies, []);
});

test("conflicting dependency rule aliases fail closed", () => {
  const actual = plan([edge({ before_rule: "canonical_missing" })]);
  assert.deepEqual(actual.orderedRepairIds, ["sitemap", "redirect"]);
  assert.deepEqual(actual.appliedDependencies, []);
});

test("matching dependency aliases preserve explicit versioned ordering", () => {
  const actual = plan([edge({
    table_version: TABLE_VERSION,
    before_rule: "REDIRECT_CHAIN",
    after_rule: "SITEMAP_REDIRECT",
  })]);
  assert.deepEqual(actual.orderedRepairIds, ["redirect", "sitemap"]);
  assert.equal(actual.appliedDependencies.length, 1);
  assert.equal(actual.appliedDependencies[0].tableEdgeId, "redirect_before_sitemap");
});
