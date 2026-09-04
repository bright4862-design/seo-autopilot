import assert from "node:assert/strict";
import test from "node:test";

import { buildScanHandoff } from "../../src/lib/scanHandoff.js";

test("a missing health score stays unavailable instead of becoming zero", () => {
  const handoff = buildScanHandoff({
    scanRecord: { website_url: "https://example.com" },
    cards: [],
    healthScore: null,
    scoreUnavailable: false,
  });

  assert.equal(handoff.health_score, null);
  assert.equal(handoff.health_score_available, false);
});
