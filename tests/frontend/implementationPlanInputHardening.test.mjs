import assert from "node:assert/strict";
import test from "node:test";

import {
  IMPLEMENTATION_DEPENDENCY_TABLE_VERSION,
  buildImplementationPlan,
} from "../../src/lib/implementationPlan.js";

const TRUSTED_SCAN_ID = "scan:implementation-plan-input-hardening";

function verifiedRoot(rootCauseId, overrides = {}) {
  return {
    version: "root_cause_evidence_v1_verified",
    state: "verified",
    root_cause_id: rootCauseId,
    evidence_refs: [`observation:${rootCauseId}`],
    ...overrides,
  };
}

function dependencyPair(rootCauseEvidence = verifiedRoot("root:shared")) {
  return [
    {
      fix_id: "sitemap",
      rule: "sitemap_redirect",
      action_priority: "fix_first",
      root_cause_evidence: rootCauseEvidence,
    },
    {
      fix_id: "redirect",
      rule: "redirect_chain",
      action_priority: "important",
      root_cause_evidence: rootCauseEvidence,
    },
  ];
}

test("array-shaped repair rule identifiers cannot instantiate dependency ordering", () => {
  const input = dependencyPair();
  input[0].rule = ["sitemap_redirect"];
  input[1].rule = ["redirect_chain"];

  const result = buildImplementationPlan(input, { trustedScanId: TRUSTED_SCAN_ID });
  assert.deepEqual(result.orderedRepairIds, ["sitemap", "redirect"]);
  assert.deepEqual(result.appliedDependencies, []);
});

test("array-shaped verified state cannot grant root-cause authority", () => {
  const result = buildImplementationPlan(
    dependencyPair(verifiedRoot("root:shared", { state: ["verified"] })),
    { trustedScanId: TRUSTED_SCAN_ID },
  );

  assert.deepEqual(result.orderedRepairIds, ["sitemap", "redirect"]);
  assert.deepEqual(result.appliedDependencies, []);
  assert.equal(result.groups.length, 2);
});

test("array-shaped surface and remediation identifiers cannot create a shared group", () => {
  const input = [
    {
      fix_id: "heading-a",
      rule: "missing_h1",
      action_priority: "important",
      repair_surface: ["cms_field"],
      remediation_family: ["heading_template"],
    },
    {
      fix_id: "heading-b",
      rule: "missing_h1",
      action_priority: "important",
      repair_surface: ["cms_field"],
      remediation_family: ["heading_template"],
    },
  ];

  const result = buildImplementationPlan(input, { trustedScanId: TRUSTED_SCAN_ID });
  assert.equal(result.groups.length, 2);
  assert.notEqual(result.groups[0].key, result.groups[1].key);
});

test("array-shaped dependency edge metadata cannot become an explicit versioned edge", () => {
  const dependencyTableVersion = "test_dependencies_v1";
  const dependencyEdges = [{
    tableVersion: [dependencyTableVersion],
    id: ["redirect_before_sitemap"],
    beforeRule: ["redirect_chain"],
    afterRule: ["sitemap_redirect"],
    requires: ["verified_shared_root_cause"],
    rationale: ["test"],
  }];

  const result = buildImplementationPlan(dependencyPair(), {
    trustedScanId: TRUSTED_SCAN_ID,
    dependencyEdges,
    dependencyTableVersion,
  });

  assert.deepEqual(result.orderedRepairIds, ["sitemap", "redirect"]);
  assert.deepEqual(result.appliedDependencies, []);
});

test("array-shaped dependency table version fails closed instead of selecting the production table", () => {
  const result = buildImplementationPlan(dependencyPair(), {
    trustedScanId: TRUSTED_SCAN_ID,
    dependencyTableVersion: [IMPLEMENTATION_DEPENDENCY_TABLE_VERSION],
  });

  assert.equal(result.dependencyTableVersion, "");
  assert.deepEqual(result.orderedRepairIds, ["sitemap", "redirect"]);
  assert.deepEqual(result.appliedDependencies, []);
});

test("mixed-type evidence refs cannot grant root-cause authority", () => {
  const root = verifiedRoot("root:mixed-refs", {
    evidence_refs: ["observation:root:mixed-refs", { source: "debug" }],
  });

  const result = buildImplementationPlan(dependencyPair(root), {
    trustedScanId: TRUSTED_SCAN_ID,
  });

  assert.deepEqual(result.orderedRepairIds, ["sitemap", "redirect"]);
  assert.deepEqual(result.appliedDependencies, []);
  assert.equal(result.groups.length, 2);
});

test("blank evidence refs cannot grant root-cause authority", () => {
  const root = verifiedRoot("root:blank-ref", {
    evidence_refs: ["observation:root:blank-ref", "   "],
  });

  const result = buildImplementationPlan(dependencyPair(root), {
    trustedScanId: TRUSTED_SCAN_ID,
  });

  assert.deepEqual(result.orderedRepairIds, ["sitemap", "redirect"]);
  assert.deepEqual(result.appliedDependencies, []);
  assert.equal(result.groups.length, 2);
});
