import assert from "node:assert/strict";
import test from "node:test";

import { buildRepairCards } from "../../src/lib/repairCardModel.js";
import { buildScanHandoff } from "../../src/lib/scanHandoff.js";

const SCAN = {
  scan_id: "center-street-contract",
  website_url: "https://example.com",
  created_at: "2026-09-09T20:00:00Z",
};

test("handoff preserves backend action priority separately from technical severity", () => {
  const cards = buildRepairCards([{
    id: "canonical-repair",
    fix_id: "canonical-repair",
    rule: "canonical_missing",
    repair_fingerprint: "canonical|sitewide",
    status: "needs_approval",
    priority: "critical",
    action_priority: "important",
    issue_title: "Add a preferred canonical URL",
    why_it_matters: "Search engines need a preferred URL.",
    recommendation: "Add a self-referencing canonical where appropriate.",
    affected_pages: ["/guide"],
    page_count: 1,
  }]);

  assert.equal(cards.length, 1);
  assert.equal(cards[0].priority, "critical", "technical severity remains the historical contract");
  assert.equal(cards[0].actionPriority, "important", "the card carries the backend-owned action band");

  const [fix] = buildScanHandoff({ scanRecord: SCAN, cards }).fixes;

  assert.equal(fix.priority, "critical", "the handoff must not rewrite technical severity");
  assert.equal(
    fix.action_priority,
    "important",
    "the handoff must expose the canonical action band instead of making the customer infer it from severity",
  );
});
