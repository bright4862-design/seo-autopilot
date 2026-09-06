import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { durableScanLimitationKind } from "../../src/lib/durableScanStatePresentation.js";
import { healthScoreExplanation } from "../../src/lib/healthScoreExplanation.js";
import {
  buildRepairCards,
  withRepeatedTitleScopeHints,
} from "../../src/lib/repairCardModel.js";

/**
 * Final review regressions for PR #254.
 *
 * These are deliberately end-of-chain fixtures: each one reproduces a state
 * that can reach the customer from persisted evidence, rather than testing a
 * helper in isolation. Keep them small so a future mutation of the wiring is
 * obvious in the failure.
 */

test("structured limitation evidence wins over legacy failure text", () => {
  assert.equal(
    durableScanLimitationKind({
      status: "limited",
      evidence_quality_state: "access_limited",
      error_code: "worker_heartbeat_timeout",
    }),
    "access_limited",
    "a legacy heartbeat fragment must not overwrite the producer's structured access verdict",
  );

  assert.equal(
    durableScanLimitationKind({
      status: "limited",
      coverage_state: "inventory_unproven",
      error_code: "authority_write_failed",
    }),
    "too_few_usable_pages",
    "a legacy write-failure fragment must not overwrite the producer's structured coverage verdict",
  );
});

test("a current empty score explanation is unavailable, not legacy", () => {
  const view = healthScoreExplanation({
    health_score: 58,
    health_score_explanation: {},
  });

  assert.equal(view.available, false);
  assert.equal(view.legacy, false);
  assert.equal(view.legacyNote, "");
});

function repeatedCanonicalRow(overrides = {}) {
  return {
    fix_id: "fix_default",
    rule: "sitemap_redirect",
    issue_title: "Send visitors straight to the right page",
    priority: "medium",
    category: "internal_link",
    page_count: 0,
    affected_pages: [],
    ...overrides,
  };
}

test("repeated-title fallback uses the persisted canonical evidence classes", () => {
  const cards = withRepeatedTitleScopeHints(buildRepairCards([
    repeatedCanonicalRow({ fix_id: "fix_problem", evidence_class: "confirmed_problem" }),
    repeatedCanonicalRow({ fix_id: "fix_opportunity", evidence_class: "opportunity" }),
  ]));

  assert.equal(cards.length, 2);
  assert.deepEqual(cards.map((card) => card.scopeHint), [
    "Confirmed problem",
    "Review opportunity",
  ]);
});

test("all five live score normalizers are pinned byte-identical", () => {
  const copies = [
    "base44/functions/persistDurableScanAuthorityV2/authoritySnapshot.js",
    "base44/functions/getCustomerScanResultV2/projection.js",
    "base44/functions/grokChat/authoritySnapshot.js",
    "base44/functions/persistDurableScanAuthority/authoritySnapshot.js",
    "base44/functions/getCustomerScanResult/projection.js",
  ].map((file) => {
    const source = fs.readFileSync(new URL(`../../${file}`, import.meta.url), "utf8");
    const from = source.indexOf("function scoreExplanation(value) {");
    assert.ok(from > -1, `${file} has no scoreExplanation`);
    return { file, body: source.slice(from, source.indexOf("\n}", from)) };
  });

  for (const copy of copies.slice(1)) {
    assert.equal(copy.body, copies[0].body, `${copy.file} has drifted from the V2 writer's copy`);
  }
});
