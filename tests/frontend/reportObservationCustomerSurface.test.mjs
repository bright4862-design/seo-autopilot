import assert from "node:assert/strict";
import test from "node:test";

import { buildRepairCard } from "../../src/lib/repairCardModel.js";
import { buildScanHandoff } from "../../src/lib/scanHandoff.js";
import { scanCoverageDisclosure } from "../../src/lib/scanCoverageDisclosure.js";

const persisted = {
  id: "canonical-1",
  fix_id: "canonical-1",
  rule: "canonical_missing",
  category: "canonical",
  priority: "high",
  action_priority: "important",
  issue_title: "Add canonical URLs",
  recommended_value: "Add the correct preferred URL setting.",
  page_count: 25,
  affected_pages: ["/products/item-0", "/products/item-1"],
  raw_finding: {
    repair_observation_count: 25,
    repair_observation_samples: [
      { page_url: "/products/item-0", status: 200, issue_type: "canonical_missing", canonical_url: "" },
      { page_url: "/products/item-1", status: 200, issue_type: "canonical_missing", canonical_url: "" },
    ],
  },
};

test("customer repair card carries only persisted observed repair evidence", () => {
  const card = buildRepairCard(persisted);
  assert.equal(card.evidence.repairObservationCount, 25);
  assert.deepEqual(card.evidence.repairObservationSamples, persisted.raw_finding.repair_observation_samples);
  assert.equal(card.evidence.repairObservationSamples[0].canonical_url, "");
});

test("JSON handoff preserves observed repair evidence and truthful integer scan coverage", () => {
  const card = buildRepairCard(persisted);
  const handoff = buildScanHandoff({
    scanRecord: {
      website_url: "https://example.com",
      created_at: "2026-09-09T00:00:00Z",
      scan_coverage: {
        urls_attempted: 31,
        usable_html_pages: 25,
        verified_http_failures: 2,
        access_unverified_pages: 3,
        non_html_resources: 1,
        unique_retained_destinations: 24,
      },
      // Legacy field must not be reinterpreted as attempted coverage.
      usable_html_page_count: 999,
    },
    cards: [card],
  });

  assert.deepEqual(handoff.scan_coverage, {
    urls_attempted: 31,
    usable_html_pages: 25,
    verified_http_failures: 2,
    access_unverified_pages: 3,
    non_html_resources: 1,
    unique_retained_destinations: 24,
  });
  assert.equal(handoff.fixes[0].repair_observation_count, 25);
  assert.deepEqual(handoff.fixes[0].repair_observation_samples, persisted.raw_finding.repair_observation_samples);

  const redirectHandoff = buildScanHandoff({
    scanRecord: { website_url: "https://example.com" },
    cards: [{
      ...card,
      evidence: {
        ...card.evidence,
        redirectEvidence: [{
          requested_url: "https://example.com/old",
          final_url: "https://example.com/final",
          final_status: 0,
          fetch_error: "timed out",
          classification: "redirect_destination_unverified",
        }],
      },
    }],
  });
  assert.equal(redirectHandoff.fixes[0].redirect_evidence[0].verification_state, "needs_verification");
});

test("coverage disclosure rejects strings and legacy inferred fields", () => {
  assert.deepEqual(scanCoverageDisclosure({
    scan_coverage: {
      urls_attempted: "31",
      usable_html_pages: 25,
      verified_http_failures: 2.2,
      access_unverified_pages: -1,
      non_html_resources: 1,
      unique_retained_destinations: 24,
    },
    usable_html_page_count: 999,
  }), {
    usable_html_pages: 25,
    non_html_resources: 1,
    unique_retained_destinations: 24,
  });

  assert.deepEqual(scanCoverageDisclosure({ usable_html_page_count: 999 }), {});
});
