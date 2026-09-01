import assert from "node:assert/strict";
import test from "node:test";

import {
  buildRepairCards,
  customerEvidenceGroupHeading,
  customerEvidenceGroupRows,
} from "../../src/lib/repairCardModel.js";

const SITE = "https://example.com";

function canonicalRow(groups) {
  return {
    id: "row_1",
    fix_id: "action_1",
    rule: "missing_meta_description",
    repair_fingerprint: "fingerprint_1",
    page_count: 2,
    affected_pages: ["/fr/category/a", "/de/product/b"],
    raw_finding: { repair_evidence_groups: groups },
  };
}

test("persisted evidence groups produce the exact visible child rows", () => {
  const groups = [
    {
      fix_id: "child_fr",
      family: "category_listing",
      locale: "fr",
      representative_url: "/fr/category/a",
      affected_urls: ["/fr/category/a"],
      count: 1,
    },
    {
      fix_id: "child_de",
      family: "product_detail",
      locale: "de",
      representative_url: "/de/product/b",
      affected_urls: ["/de/product/b"],
      count: 1,
    },
  ];
  const card = buildRepairCards([canonicalRow(groups)])[0];

  const rows = customerEvidenceGroupRows(card, SITE);

  assert.equal(rows.length, 2, "header count must equal the child rows customers can see");
  assert.equal(customerEvidenceGroupHeading(rows), "Evidence groups (2)");
  assert.deepEqual(rows.map((row) => row.familyLabel), ["category", "product"]);
  assert.deepEqual(rows.map((row) => row.locale), ["fr", "de"]);
  assert.deepEqual(rows.map((row) => row.representativePage), ["/fr/category/a", "/de/product/b"]);
  assert.deepEqual(rows.map((row) => row.representativeLink.href), [
    "https://example.com/fr/category/a",
    "https://example.com/de/product/b",
  ]);
});

test("a persisted locale is hidden when its affected URLs do not agree", () => {
  const card = buildRepairCards([canonicalRow([{
    fix_id: "mixed",
    family: "standard",
    locale: "fr",
    representative_url: "/fr/page",
    affected_urls: ["/fr/page", "/about"],
    count: 2,
  }])])[0];

  const rows = customerEvidenceGroupRows(card, SITE);

  assert.equal(rows.length, 1);
  assert.equal(rows[0].locale, "");
});

test("one child remains one evidence group without creating another top-level action", () => {
  const cards = buildRepairCards([canonicalRow([{
    fix_id: "only_child",
    family: "homepage",
    locale: "",
    representative_url: "/",
    affected_urls: ["/"],
    count: 1,
  }])]);

  assert.equal(cards.length, 1);
  const rows = customerEvidenceGroupRows(cards[0], SITE);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].familyLabel, "homepage");
  assert.equal(rows[0].representativeLink.label, "Homepage · /");
});

test("persisted evidence groups survive normalized members with raw_finding under original", () => {
  const groups = [{
    fix_id: "persisted_child",
    family: "guide_article",
    locale: "fr",
    representative_url: "/fr/guide",
    affected_urls: ["/fr/guide"],
    count: 1,
  }];
  const normalized = {
    id: "normalized_row",
    fix_id: "normalized_action",
    rule: "missing_meta_description",
    repair_fingerprint: "normalized-fingerprint",
    page_count: 1,
    affected_pages: ["/fr/guide"],
    original: {
      raw_finding: { repair_evidence_groups: groups },
    },
  };

  const card = buildRepairCards([normalized])[0];
  const rows = customerEvidenceGroupRows(card, SITE);

  assert.equal(rows.length, 1);
  assert.equal(rows[0].id, "persisted_child");
  assert.equal(rows[0].familyLabel, "guide");
  assert.equal(rows[0].locale, "fr");
  assert.equal(rows[0].representativeLink.href, "https://example.com/fr/guide");
});
