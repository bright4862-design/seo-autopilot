import assert from "node:assert/strict";
import test from "node:test";

import { buildRepairCards } from "../../src/lib/repairCardModel.js";
import { buildCustomerRepairPlan } from "../../src/lib/customerRepairPlan.js";

const STAGE3_PRIORITY_VERSION = "repair_priority_v3_four_factor_v1";

function stage3Repair({
  id,
  title,
  page,
  actionPriority,
  fingerprint = "shared-stage3-fingerprint",
} = {}) {
  return {
    id,
    fix_id: id,
    rule: `rule_${id}`,
    title,
    action_priority: actionPriority,
    repair_fingerprint: fingerprint,
    affected_pages: [page],
    page_count: 1,
    stage3_priority_factors: {
      version: STAGE3_PRIORITY_VERSION,
      impact: 4,
      reach: 0.5,
      page_value: 0.8,
      confidence: 1,
      priority_factor_score: 1.6,
      reach_affected_indexable: 1,
      reach_observed_indexable_family: 2,
      explanation: ["sealed Stage-3 priority evidence"],
      impact_reason: "observed issue",
      reach_state: "known",
      page_value_state: "known",
      page_value_role: "commercial",
      page_value_source: "sealed",
      confidence_state: "verified",
      score_state: "known",
      technical_base_severity: "high",
      technical_severity_source: "scanner",
    },
    stage3_counts: {
      unique_affected_page_count: 1,
      observation_count: 1,
      known_population_count: 2,
      displayed_sample_count: 1,
      displayed_samples: [page],
      examples_partial: false,
      truncated_sample_count: 0,
    },
  };
}

test("one malformed Stage-3 row degrades only itself without merging valid neighbours", () => {
  const valid = stage3Repair({
    id: "valid",
    title: "Valid Stage-3 repair",
    page: "https://example.com/valid",
    actionPriority: "improve",
  });
  const malformed = stage3Repair({
    id: "malformed",
    title: "Malformed Stage-3 repair",
    page: "https://example.com/malformed",
    actionPriority: "fix_first",
  });
  malformed.stage3_counts = {
    ...malformed.stage3_counts,
    displayed_sample_count: 2,
  };

  const cards = buildRepairCards([valid, malformed]);

  assert.equal(cards.length, 2, "a malformed neighbour must not trigger legacy fingerprint merging for the batch");
  assert.equal(cards[0].title, "Valid Stage-3 repair");
  assert.equal(cards[0].priorityFactors?.version, STAGE3_PRIORITY_VERSION);
  assert.ok(cards[0].stage3Counts);
  assert.equal(cards[1].title, "Malformed Stage-3 repair");
  assert.equal(cards[1].priorityFactors, undefined, "malformed Stage-3 truth must fail closed on that row");
  assert.equal(cards[1].stage3Counts, undefined, "partial Stage-3 fields must not be projected as verified presentation truth");
});

test("mixed Stage-3 presentation preserves authenticated source order and reports row degradation", () => {
  const valid = stage3Repair({
    id: "ranked-first",
    title: "Ranked first by Stage-3",
    page: "https://example.com/first",
    actionPriority: "improve",
  });
  const malformed = stage3Repair({
    id: "ranked-second",
    title: "Ranked second by Stage-3",
    page: "https://example.com/second",
    actionPriority: "fix_first",
  });
  malformed.stage3_priority_factors = {
    ...malformed.stage3_priority_factors,
    confidence: "1",
  };

  const cards = buildRepairCards([valid, malformed]);
  const plan = buildCustomerRepairPlan(cards);

  assert.deepEqual(
    plan.cards.map((card) => card.title),
    ["Ranked first by Stage-3", "Ranked second by Stage-3"],
    "legacy action-band sorting must not reorder valid Stage-3 neighbours when one row degrades",
  );
  assert.equal(plan.presentation_mode, "stage3_per_row_degraded_v1");
  assert.deepEqual(plan.row_coverage, {
    total_rows: 2,
    stage3_complete_rows: 1,
    degraded_rows: 1,
  });
  assert.equal(plan.fixFirstCount, 1);
});

test("healthy Stage-3 and purely historical batches retain their existing presentation contracts", () => {
  const first = stage3Repair({
    id: "healthy-first",
    title: "Healthy first",
    page: "https://example.com/healthy-first",
    actionPriority: "improve",
    fingerprint: "healthy-first-fingerprint",
  });
  const second = stage3Repair({
    id: "healthy-second",
    title: "Healthy second",
    page: "https://example.com/healthy-second",
    actionPriority: "fix_first",
    fingerprint: "healthy-second-fingerprint",
  });
  const healthyPlan = buildCustomerRepairPlan(buildRepairCards([first, second]));
  assert.deepEqual(healthyPlan.cards.map((card) => card.title), ["Healthy first", "Healthy second"]);
  assert.equal(healthyPlan.presentation_mode, undefined, "healthy Stage-3 plan shape stays unchanged");
  assert.equal(healthyPlan.row_coverage, undefined, "healthy Stage-3 plan does not gain new telemetry fields");

  const historical = [
    {
      id: "legacy-a",
      fix_id: "legacy-a",
      title: "Legacy A",
      rule: "legacy_a",
      repair_fingerprint: "legacy-shared",
      affected_pages: ["/a"],
      page_count: 1,
    },
    {
      id: "legacy-b",
      fix_id: "legacy-b",
      title: "Legacy B",
      rule: "legacy_b",
      repair_fingerprint: "legacy-shared",
      affected_pages: ["/b"],
      page_count: 1,
    },
  ];
  const historicalCards = buildRepairCards(historical);
  assert.equal(historicalCards.length, 1, "pure historical batches keep legacy fingerprint grouping");
});
