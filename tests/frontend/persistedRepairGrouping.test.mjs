import assert from "node:assert/strict";
import test from "node:test";

import { buildCustomerProjection } from "../../base44/functions/getCustomerScanResult/projection.js";
import { buildRepairCards } from "../../src/lib/repairCardModel.js";

const REPAIR_CONTRACT = "repair_contract_v2_shadow_calibrated";

test("persisted grouped action survives customer projection and card rendering", () => {
  const childGroups = [
    {
      fix_id: "child_fr",
      family: "category_listing",
      locale: "fr",
      representative_url: "https://example.com/fr/category/a",
      affected_urls: ["https://example.com/fr/category/a"],
      count: 1,
      priority: "high",
      action_priority: "important",
      evidence_class: "confirmed_problem",
      evidence_status: "confirmed",
      verification_state: "verified",
      repair_verification_state: "open",
    },
    {
      fix_id: "child_de",
      family: "product_detail",
      locale: "de",
      representative_url: "https://example.com/de/product/b",
      affected_urls: ["https://example.com/de/product/b"],
      count: 1,
      priority: "high",
      action_priority: "important",
      evidence_class: "confirmed_problem",
      evidence_status: "confirmed",
      verification_state: "verified",
      repair_verification_state: "open",
    },
  ];

  const projection = buildCustomerProjection({
    run: { id: "scan_1", beta_revision_fingerprint: "candidate" },
    fixList: {
      id: "fixlist_1",
      repair_contract_version: REPAIR_CONTRACT,
      repair_snapshot_contract_version: REPAIR_CONTRACT,
      repair_snapshot_contract_complete: true,
    },
    fixItems: [{
      id: "row_1",
      fix_id: "action_1",
      rule: "missing_meta_description",
      repair_fingerprint: "fingerprint_1",
      repair_identity_stable: true,
      canonical_action_rank: 1,
      affected_pages: [
        "https://example.com/fr/category/a",
        "https://example.com/de/product/b",
      ],
      page_count: 2,
      raw_finding: {
        repair_evidence_groups: childGroups,
      },
    }],
    fullAccess: true,
    authorityVerified: true,
    resultIntegrityVerified: false,
  });

  assert.equal(projection.fixItems.length, 1);
  assert.deepEqual(
    projection.fixItems[0].raw_finding.repair_evidence_groups.map((group) => group.fix_id),
    ["child_fr", "child_de"],
  );

  const cards = buildRepairCards(projection.fixItems);
  assert.equal(cards.length, 1);
  assert.equal(cards[0].evidence.evidenceGroups.length, 2);
  assert.deepEqual(
    cards[0].evidence.evidenceGroups.map((group) => group.locale),
    ["fr", "de"],
  );
  assert.deepEqual(
    cards[0].evidence.evidenceGroups.flatMap((group) => group.affectedPages),
    ["https://example.com/fr/category/a", "https://example.com/de/product/b"],
  );
});

test("historical rows without persisted child groups still render safely", () => {
  const cards = buildRepairCards([{
    id: "legacy_1",
    fix_id: "legacy_1",
    rule: "missing_h1",
    repair_fingerprint: "legacy_fp",
    affected_pages: ["/"],
    page_count: 1,
  }]);

  assert.equal(cards.length, 1);
  assert.equal(cards[0].evidence.evidenceGroups.length, 1);
  assert.equal(cards[0].evidence.evidenceGroups[0].representativePage, "/");
});
