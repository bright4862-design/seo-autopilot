import assert from "node:assert/strict";
import test from "node:test";

import {
  IMPLEMENTATION_DEPENDENCY_EDGES,
  IMPLEMENTATION_DEPENDENCY_TABLE_VERSION,
  IMPLEMENTATION_PLAN_VERSION,
  buildImplementationPlan,
} from "../../src/lib/implementationPlan.js";

function verifiedRoot(rootCauseId, repairSurfaceId = "") {
  return {
    version: "root_cause_evidence_v1_verified",
    state: "verified",
    root_cause_id: rootCauseId,
    repair_surface_id: repairSurfaceId,
  };
}

const GOLDEN_INPUT = Object.freeze([
  Object.freeze({
    fix_id: "canonical-1",
    rule: "canonical_missing",
    action_priority: "fix_first",
    repair_surface: "document_head",
    remediation_family: "canonical_tag",
    page_template_family: "product_page",
  }),
  Object.freeze({
    fix_id: "redirect-1",
    rule: "redirect_chain",
    action_priority: "important",
    repair_surface: "redirect_configuration",
    page_template_family: "product_page",
    root_cause_evidence: verifiedRoot("root:final-url"),
  }),
  Object.freeze({
    fix_id: "sitemap-1",
    rule: "sitemap_redirect",
    action_priority: "improve",
    repair_surface: "xml_sitemap",
    page_template_family: "product_page",
    root_cause_evidence: verifiedRoot("root:final-url"),
  }),
  Object.freeze({
    fix_id: "links-1",
    rule: "internal_link_redirect",
    action_priority: "improve",
    repair_surface: "internal_links",
    page_template_family: "product_page",
    root_cause_evidence: verifiedRoot("root:final-url"),
  }),
]);

test("golden implementation plan preserves canonical order unless dependencies require movement", () => {
  const actual = buildImplementationPlan(GOLDEN_INPUT);
  assert.deepEqual(actual, {
    version: IMPLEMENTATION_PLAN_VERSION,
    dependencyTableVersion: IMPLEMENTATION_DEPENDENCY_TABLE_VERSION,
    cycleDetected: false,
    fallbackUsed: false,
    priorityMonotonicOrExplicit: true,
    orderedRepairIds: ["canonical-1", "redirect-1", "sitemap-1", "links-1"],
    appliedDependencies: [
      {
        tableVersion: IMPLEMENTATION_DEPENDENCY_TABLE_VERSION,
        tableEdgeId: "redirect_chain_before_sitemap_redirect",
        beforeFixId: "redirect-1",
        afterFixId: "sitemap-1",
        rationale: "Stabilize the final redirect destination before publishing that destination in the sitemap.",
      },
      {
        tableVersion: IMPLEMENTATION_DEPENDENCY_TABLE_VERSION,
        tableEdgeId: "redirect_chain_before_internal_link_redirect",
        beforeFixId: "redirect-1",
        afterFixId: "links-1",
        rationale: "Stabilize the final redirect destination before replacing internal links with that destination.",
      },
    ],
    groups: [
      {
        key: "surface:document_head\u0000remediation:canonical_tag",
        firstPlanIndex: 0,
        repairIds: ["canonical-1"],
        rules: ["canonical_missing"],
        repairSurface: "document_head",
        remediationFamily: "canonical_tag",
        rootCauseId: "",
        pageFamilies: ["product_page"],
      },
      {
        key: "root_cause:root:final-url",
        firstPlanIndex: 1,
        repairIds: ["redirect-1", "sitemap-1", "links-1"],
        rules: ["redirect_chain", "sitemap_redirect", "internal_link_redirect"],
        repairSurface: "redirect_configuration",
        remediationFamily: "",
        rootCauseId: "root:final-url",
        pageFamilies: ["product_page"],
      },
    ],
  });
});

test("an explicit dependency edge may move a lower priority repair ahead of a higher priority repair", () => {
  const input = [
    { fix_id: "sitemap", rule: "sitemap_redirect", action_priority: "fix_first", root_cause_evidence: verifiedRoot("root:x") },
    { fix_id: "redirect", rule: "redirect_chain", action_priority: "important", root_cause_evidence: verifiedRoot("root:x") },
  ];
  const actual = buildImplementationPlan(input);
  assert.deepEqual(actual.orderedRepairIds, ["redirect", "sitemap"]);
  assert.equal(actual.priorityMonotonicOrExplicit, true);
  assert.equal(actual.appliedDependencies.length, 1);
  assert.equal(actual.appliedDependencies[0].tableVersion, IMPLEMENTATION_DEPENDENCY_TABLE_VERSION);
  assert.equal(actual.appliedDependencies[0].tableEdgeId, "redirect_chain_before_sitemap_redirect");
});

test("without an explicit satisfied dependency, canonical priority order never changes", () => {
  const input = [
    { fix_id: "sitemap", rule: "sitemap_redirect", action_priority: "fix_first" },
    { fix_id: "redirect", rule: "redirect_chain", action_priority: "important" },
    { fix_id: "h1", rule: "missing_h1", action_priority: "improve" },
  ];
  const actual = buildImplementationPlan(input);
  assert.deepEqual(actual.orderedRepairIds, ["sitemap", "redirect", "h1"]);
  assert.deepEqual(actual.appliedDependencies, []);
});

test("unversioned or mismatched dependency edges cannot reorder canonical priority", () => {
  const shared = verifiedRoot("root:version-gate");
  const input = [
    { fix_id: "sitemap", rule: "sitemap_redirect", action_priority: "fix_first", root_cause_evidence: shared },
    { fix_id: "redirect", rule: "redirect_chain", action_priority: "important", root_cause_evidence: shared },
  ];
  const baseEdge = {
    id: "redirect_before_sitemap",
    beforeRule: "redirect_chain",
    afterRule: "sitemap_redirect",
    requires: "verified_shared_root_cause",
    rationale: "test",
  };

  const unversioned = buildImplementationPlan(input, {
    dependencyEdges: [baseEdge],
    dependencyTableVersion: "test_dependencies_v1",
  });
  assert.deepEqual(unversioned.orderedRepairIds, ["sitemap", "redirect"]);
  assert.deepEqual(unversioned.appliedDependencies, []);

  const mismatched = buildImplementationPlan(input, {
    dependencyEdges: [{ ...baseEdge, tableVersion: "other_dependencies_v1" }],
    dependencyTableVersion: "test_dependencies_v1",
  });
  assert.deepEqual(mismatched.orderedRepairIds, ["sitemap", "redirect"]);
  assert.deepEqual(mismatched.appliedDependencies, []);
});

test("page-family similarity alone never creates one implementation group", () => {
  const actual = buildImplementationPlan([
    { fix_id: "a", rule: "missing_h1", action_priority: "important", page_template_family: "product_page" },
    { fix_id: "b", rule: "duplicate_title_template", action_priority: "important", page_template_family: "product_page" },
  ]);
  assert.equal(actual.groups.length, 2);
  assert.deepEqual(actual.groups.map((group) => group.pageFamilies), [["product_page"], ["product_page"]]);
});

test("surface plus remediation family can group evidenced shared implementation work", () => {
  const actual = buildImplementationPlan([
    { fix_id: "a", rule: "missing_h1", action_priority: "important", repair_surface: "cms_field", remediation_family: "heading_template", page_template_family: "product_page" },
    { fix_id: "b", rule: "missing_h1", action_priority: "important", repair_surface: "cms_field", remediation_family: "heading_template", page_template_family: "location_landing" },
  ]);
  assert.equal(actual.groups.length, 1);
  assert.deepEqual(actual.groups[0].repairIds, ["a", "b"]);
  assert.deepEqual(actual.groups[0].pageFamilies, ["product_page", "location_landing"]);
});

test("verified root cause can group different implementation surfaces without inventing a cause from page family", () => {
  const root = verifiedRoot("root:shared");
  const actual = buildImplementationPlan([
    { fix_id: "a", rule: "redirect_chain", action_priority: "important", repair_surface: "redirect_configuration", root_cause_evidence: root },
    { fix_id: "b", rule: "sitemap_redirect", action_priority: "improve", repair_surface: "xml_sitemap", root_cause_evidence: root },
  ]);
  assert.equal(actual.groups.length, 1);
  assert.equal(actual.groups[0].rootCauseId, "root:shared");
});

test("unverified or wrong-version root cause evidence is ignored", () => {
  const actual = buildImplementationPlan([
    { fix_id: "a", rule: "redirect_chain", action_priority: "important", root_cause_evidence: { ...verifiedRoot("root:x"), state: "candidate" } },
    { fix_id: "b", rule: "sitemap_redirect", action_priority: "improve", root_cause_evidence: { ...verifiedRoot("root:x"), version: "future_version" } },
  ]);
  assert.equal(actual.groups.length, 2);
  assert.deepEqual(actual.appliedDependencies, []);
});

test("dependency cycles fail safely to canonical priority order", () => {
  const shared = verifiedRoot("root:cycle");
  const input = [
    { fix_id: "a", rule: "a", action_priority: "fix_first", root_cause_evidence: shared },
    { fix_id: "b", rule: "b", action_priority: "important", root_cause_evidence: shared },
  ];
  const dependencyTableVersion = "test_dependencies_v1";
  const edges = [
    { tableVersion: dependencyTableVersion, id: "a_before_b", beforeRule: "a", afterRule: "b", requires: "verified_shared_root_cause", rationale: "test" },
    { tableVersion: dependencyTableVersion, id: "b_before_a", beforeRule: "b", afterRule: "a", requires: "verified_shared_root_cause", rationale: "test" },
  ];
  const actual = buildImplementationPlan(input, { dependencyEdges: edges, dependencyTableVersion });
  assert.equal(actual.dependencyTableVersion, dependencyTableVersion);
  assert.equal(actual.cycleDetected, true);
  assert.equal(actual.fallbackUsed, true);
  assert.deepEqual(actual.orderedRepairIds, ["a", "b"]);
  assert.deepEqual(actual.appliedDependencies, []);
});

test("implementation planning does not mutate fix IDs, priorities, evidence classes, counts, authority or remediation", () => {
  const input = [{
    fix_id: "fix-immutable",
    rule: "missing_h1",
    action_priority: "important",
    evidence_class: "confirmed_problem",
    page_count: 12,
    authority_sealed: true,
    recommendation: "Scanner remediation",
    repair_surface: "cms_field",
    remediation_family: "heading_template",
  }];
  const before = structuredClone(input);
  buildImplementationPlan(input);
  assert.deepEqual(input, before);
});

test("identical implementation-plan input produces byte-stable output", () => {
  const once = JSON.stringify(buildImplementationPlan(GOLDEN_INPUT));
  const twice = JSON.stringify(buildImplementationPlan(GOLDEN_INPUT));
  assert.equal(once, twice);
});

test("dependency table is small, explicit and versioned", () => {
  assert.equal(IMPLEMENTATION_DEPENDENCY_EDGES.length, 2);
  assert.equal(IMPLEMENTATION_DEPENDENCY_TABLE_VERSION, "implementation_dependencies_v1_final_url_first");
  assert.ok(IMPLEMENTATION_DEPENDENCY_EDGES.every(
    (edge) => edge.tableVersion === IMPLEMENTATION_DEPENDENCY_TABLE_VERSION,
  ));
  assert.deepEqual(
    IMPLEMENTATION_DEPENDENCY_EDGES.map((edge) => edge.id),
    ["redirect_chain_before_sitemap_redirect", "redirect_chain_before_internal_link_redirect"],
  );
});
