import assert from "node:assert/strict";
import test from "node:test";

import { buildImplementationPlan } from "../../src/lib/implementationPlan.js";

function rootEvidence(rootCauseId, overrides = {}) {
  return {
    version: "root_cause_evidence_v1_verified",
    state: "verified",
    root_cause_id: rootCauseId,
    evidence_refs: ["observation:root-cause"],
    ...overrides,
  };
}

function dependencyPair(rootCauseEvidence, extra = {}) {
  return [
    {
      fix_id: "sitemap",
      rule: "sitemap_redirect",
      action_priority: "fix_first",
      root_cause_evidence: rootCauseEvidence,
      ...extra,
    },
    {
      fix_id: "redirect",
      rule: "redirect_chain",
      action_priority: "important",
      root_cause_evidence: rootCauseEvidence,
      ...extra,
    },
  ];
}

test("root-cause dependency cannot reorder without a trusted producer scan identity", () => {
  const result = buildImplementationPlan(dependencyPair(rootEvidence("root:shared")));
  assert.deepEqual(result.orderedRepairIds, ["sitemap", "redirect"]);
  assert.deepEqual(result.appliedDependencies, []);
  assert.equal(result.groups.length, 2);
});

test("root-cause dependency rejects evidence with no contributing evidence refs", () => {
  const input = dependencyPair(rootEvidence("root:shared", { evidence_refs: [] }));
  const result = buildImplementationPlan(input, { trustedScanId: "scan:trusted" });
  assert.deepEqual(result.orderedRepairIds, ["sitemap", "redirect"]);
  assert.deepEqual(result.appliedDependencies, []);
  assert.equal(result.groups.length, 2);
});

test("root-cause dependency rejects a repair-local scan identity mismatch", () => {
  const input = dependencyPair(rootEvidence("root:shared"), {
    scan_id: "scan:other",
    scan_run_id: "scan:other",
  });
  const result = buildImplementationPlan(input, { trustedScanId: "scan:trusted" });
  assert.deepEqual(result.orderedRepairIds, ["sitemap", "redirect"]);
  assert.deepEqual(result.appliedDependencies, []);
  assert.equal(result.groups.length, 2);
});

test("root-cause dependency is allowed only with evidence refs and exact trusted scan binding", () => {
  const input = dependencyPair(rootEvidence("root:shared"), {
    scan_id: "scan:trusted",
    scan_run_id: "scan:trusted",
  });
  const result = buildImplementationPlan(input, { trustedScanId: "scan:trusted" });
  assert.deepEqual(result.orderedRepairIds, ["redirect", "sitemap"]);
  assert.equal(result.appliedDependencies.length, 1);
  assert.equal(result.groups.length, 1);
  assert.equal(result.groups[0].rootCauseId, "root:shared");
});
