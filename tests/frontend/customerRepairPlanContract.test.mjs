import assert from "node:assert/strict";
import test from "node:test";

import { buildCustomerRepairPlan } from "../../src/lib/customerRepairPlan.js";
import { buildScanHandoff } from "../../src/lib/scanHandoff.js";

function card(title, actionPriority, whatToChange = "") {
  return {
    title,
    actionPriority,
    priority: "critical",
    customerCategory: "Search visibility",
    whatToChange,
    evidence: { pageCount: 1, affectedPages: [`/${title.toLowerCase().replaceAll(" ", "-")}`] },
  };
}

test("customer repair plan uses server bands and preserves saved tie order", () => {
  const cards = [
    card("Important A", "important", "Do important A"),
    card("Fix first A", "fix_first", "Do fix first A"),
    card("Fix first B", "fix_first", "Do fix first B"),
    card("Review A", "review", "Review A"),
    card("Improve A", "improve", "Improve A"),
  ];

  const plan = buildCustomerRepairPlan(cards, { fallbackNextBestStep: "stale stored sentence" });

  assert.deepEqual(plan.cards.map((item) => item.title), [
    "Fix first A",
    "Fix first B",
    "Important A",
    "Improve A",
    "Review A",
  ]);
  assert.equal(plan.fixFirstCount, 2);
  assert.equal(plan.nextBestStep, "Do fix first A");
});

test("scan handoff derives order, Fix first count, and next step from one customer plan", () => {
  const cards = [
    card("Important A", "important", "Do important A"),
    card("Fix first A", "fix_first", "Do fix first A"),
    card("Fix first B", "fix_first", "Do fix first B"),
  ];

  const handoff = buildScanHandoff({
    scanRecord: { website_url: "https://example.com", created_at: "2026-09-09T00:00:00Z" },
    cards,
    nextBestStep: "stale stored sentence",
  });

  assert.deepEqual(handoff.fixes.map((item) => item.title), ["Fix first A", "Fix first B", "Important A"]);
  assert.equal(handoff.fix_first_count, 2);
  assert.equal(handoff.next_best_step, "Do fix first A");
});
