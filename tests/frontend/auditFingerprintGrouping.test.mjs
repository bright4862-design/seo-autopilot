import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import {
  buildRepairCards,
  customerActionKey,
  mergeCustomerActions,
  repairFingerprintOf,
} from "../../src/lib/repairCardModel.js";

// The 19 same-fingerprint split groups the 35-site production audit found on
// 10 sites. Each group is one repair the customer performs once; production
// rendered them as separate top-level tasks.
const AUDIT = JSON.parse(
  fs.readFileSync("tests/fixtures/audit-35-site-fingerprint-collisions.json", "utf8"),
);

// affected_pages carries only the URL the audit actually exported for each row.
// The row's own page_count carries what it proved, so a merged count is the sum
// the scan established rather than the length of a partial list.
function personaRows(site) {
  return site.groups.flatMap((group) =>
    group.items.map((item) => ({
      id: item.fix_id,
      fix_id: item.fix_id,
      repair_fingerprint: group.repair_fingerprint,
      title: item.title,
      issue_title: item.title,
      rule: "audit_export_rule_absent",
      page_count: item.affected,
      pageCount: item.affected,
      affected_pages: [item.url],
      affectedPages: [item.url],
    })),
  );
}

test("the fixture is the audit's reported split, not a model of it", () => {
  assert.equal(AUDIT.sites.length, 10, "the audit reported 10 sites with splits");
  const groups = AUDIT.sites.reduce((total, site) => total + site.groups.length, 0);
  assert.equal(groups, 19, "the audit reported 19 same-fingerprint split groups");
  for (const site of AUDIT.sites) {
    for (const group of site.groups) {
      assert.ok(group.items.length >= 2, `${site.name} ${group.repair_fingerprint} is not a split`);
    }
  }
});

test("every same-fingerprint split becomes exactly one customer action", () => {
  for (const site of AUDIT.sites) {
    const cards = mergeCustomerActions(personaRows(site));
    assert.equal(
      cards.length,
      site.groups.length,
      `${site.name}: ${site.groups.length} repairs split into ${cards.length} actions`,
    );
  }
});

test("no two top-level cards on a site share a repair fingerprint", () => {
  for (const site of AUDIT.sites) {
    const fingerprints = mergeCustomerActions(personaRows(site)).map(repairFingerprintOf);
    assert.equal(
      new Set(fingerprints).size,
      fingerprints.length,
      `${site.name} rendered two top-level cards for one fingerprint`,
    );
  }
});

test("distinct fingerprints are never merged, even on the very same URL", () => {
  // Alan reports /coverage/v23720-nc under two fingerprints: a missing search
  // title and a noindex/canonical decision. They are two different repairs on
  // one page and must stay two actions -- merging on the page would lose one.
  const alan = AUDIT.sites.find((site) => site.name === "Alan");
  const searchTitle = alan.groups.find((g) => g.repair_fingerprint === "86a9252fae4b34a522532517");
  const noindex = alan.groups.find((g) => g.repair_fingerprint === "78085ed9cc66bd52a7021a39");
  const shared = "/coverage/v23720-nc";
  assert.ok(searchTitle.items.some((i) => i.url === shared));
  assert.ok(noindex.items.some((i) => i.url === shared));

  const cards = mergeCustomerActions(personaRows(alan));
  assert.equal(cards.length, 5, "Alan's five distinct repairs must stay five actions");
  const touching = cards.filter((card) =>
    (card.affectedPages || []).includes(shared));
  assert.equal(touching.length, 2, "one page with two distinct repairs owes two actions");
});

test("merging loses no affected URL and no proved page count", () => {
  for (const site of AUDIT.sites) {
    const rows = personaRows(site);
    const cards = mergeCustomerActions(rows);
    const rendered = new Set(cards.flatMap((card) => card.affectedPages || []));
    for (const row of rows) {
      for (const page of row.affected_pages) {
        assert.ok(rendered.has(page), `${site.name}: ${page} vanished when its rows merged`);
      }
    }
    for (const group of site.groups) {
      const declared = group.items.reduce((total, item) => total + item.affected, 0);
      const card = cards.find((c) => repairFingerprintOf(c) === group.repair_fingerprint);
      assert.equal(
        card.pageCount,
        declared,
        `${site.name} ${group.repair_fingerprint}: merged count ${card.pageCount} != proved ${declared}`,
      );
    }
  }
});

test("a merged action carries one child evidence group per persisted row", () => {
  for (const site of AUDIT.sites) {
    const cards = buildRepairCards(personaRows(site));
    for (const group of site.groups) {
      const card = cards.find((c) => c.evidence.mergedFromFixIds.includes(group.items[0].fix_id));
      const children = card.evidence.evidenceGroups;
      assert.equal(
        children.length,
        group.items.length,
        `${site.name} ${group.repair_fingerprint}: header claims ${group.items.length}, shows ${children.length}`,
      );
      // The header count a group renders must equal what its children add up to.
      const childTotal = children.reduce((total, child) => total + child.count, 0);
      assert.equal(childTotal, card.evidence.pageCount);
      const childIds = children.map((child) => child.fixId).sort();
      assert.deepEqual(childIds, group.items.map((i) => i.fix_id).sort());
    }
  }
});

test("a locale is stated only when every page in the child agrees", () => {
  const wise = AUDIT.sites.find((site) => site.name === "Wise");
  const cards = buildRepairCards(personaRows(wise));
  const plugTypes = cards.find((card) =>
    card.evidence.mergedFromFixIds.includes("finding_99e410cc7a86"));
  const locales = plugTypes.evidence.evidenceGroups.map((child) => child.locale).sort();
  // One page in three markets: each child is a single locale, and the action is
  // still one edit.
  assert.deepEqual(locales, ["de", "es", "fr"]);

  // A path with no locale segment must not acquire one.
  const berry = AUDIT.sites.find((site) => site.name === "Berry Bros. & Rudd");
  const berryCard = buildRepairCards(personaRows(berry))[0];
  assert.deepEqual(
    berryCard.evidence.evidenceGroups.map((child) => child.locale),
    ["", ""],
    "/collecting-test and /blue-hanger-whisky carry no locale",
  );
});

test("an unmerged action still carries one child evidence group", () => {
  // The per-row evidence contract must hold for every action, not only merged
  // ones: a consumer reconciling children against a count saw nothing at all
  // for a card built from a single persisted row.
  const cards = buildRepairCards([{
    fix_id: "solo_1",
    rule: "missing_h1",
    repair_fingerprint: "aa11",
    page_count: 3,
    affected_pages: ["/a", "/b", "/c"],
  }]);
  assert.equal(cards.length, 1);
  const children = cards[0].evidence.evidenceGroups;
  assert.equal(children.length, 1, "one persisted row owes one child group");
  assert.equal(children[0].fixId, "solo_1");
  assert.equal(children[0].count, 3);
  assert.deepEqual(children[0].affectedPages, ["/a", "/b", "/c"]);
  assert.equal(
    children.reduce((total, child) => total + child.count, 0),
    cards[0].evidence.pageCount,
    "children must reconcile against the card's own count",
  );
});

test("a page with no market prefix is a disagreement, not an absent one", () => {
  // ["/fr/page", "/about"] must not report "fr": /about never carried a market,
  // so claiming one states something the evidence does not support.
  const mixed = buildRepairCards([{
    fix_id: "mixed_1",
    rule: "missing_h1",
    repair_fingerprint: "bb22",
    page_count: 2,
    affected_pages: ["/fr/page", "/about"],
  }]);
  assert.equal(mixed[0].evidence.evidenceGroups[0].locale, "");

  // Agreement across every page is still reported.
  const agreed = buildRepairCards([{
    fix_id: "agreed_1",
    rule: "missing_h1",
    repair_fingerprint: "cc33",
    page_count: 2,
    affected_pages: ["/fr/page", "/fr/other"],
  }]);
  assert.equal(agreed[0].evidence.evidenceGroups[0].locale, "fr");

  // No page carrying a market is not a market either.
  const none = buildRepairCards([{
    fix_id: "none_1",
    rule: "missing_h1",
    repair_fingerprint: "dd44",
    page_count: 2,
    affected_pages: ["/about", "/contact"],
  }]);
  assert.equal(none[0].evidence.evidenceGroups[0].locale, "");
});

test("rows the scan gave no fingerprint keep the rule-based key", () => {
  // An absent identity is not evidence that two repairs are the same one, so
  // the fingerprint branch must not swallow them into a single empty bucket.
  const rows = [
    { fix_id: "a", rule: "missing_h1", page_count: 1, affected_pages: ["/a"] },
    { fix_id: "b", rule: "canonical_missing", page_count: 1, affected_pages: ["/b"] },
  ];
  assert.notEqual(customerActionKey(rows[0]), customerActionKey(rows[1]));
  assert.equal(mergeCustomerActions(rows).length, 2);
});

test("a fingerprint outranks the rule key when the scan recorded one", () => {
  // Same rule, two fingerprints => two repairs. Keying on the rule alone would
  // merge them and under-report the work.
  const rows = [
    { fix_id: "a", rule: "same_rule", repair_fingerprint: "ff11", page_count: 1, affected_pages: ["/a"] },
    { fix_id: "b", rule: "same_rule", repair_fingerprint: "ff22", page_count: 1, affected_pages: ["/b"] },
  ];
  assert.equal(mergeCustomerActions(rows).length, 2);

  // Different rules, one fingerprint => one repair, on the scanner's authority.
  const same = [
    { fix_id: "c", rule: "rule_one", repair_fingerprint: "ff33", page_count: 1, affected_pages: ["/c"] },
    { fix_id: "d", rule: "rule_two", repair_fingerprint: "ff33", page_count: 1, affected_pages: ["/d"] },
  ];
  assert.equal(mergeCustomerActions(same).length, 1);
});
