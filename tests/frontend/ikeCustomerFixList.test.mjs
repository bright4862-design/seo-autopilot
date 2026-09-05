import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { buildRepairCards, mergeCustomerActions, whereLine } from "../../src/lib/repairCardModel.js";
import { applyCustomerVocabulary, customerCopyForFix } from "../../src/lib/fixVocabulary.js";

// The exact 14 persisted FixItems from Ike scan 6a9548bd0d7384cc66988ae4.
// Rules, families and affected counts are the real persisted values, so this
// stops the release being judged against a modelled result.
const FIXTURE = JSON.parse(fs.readFileSync("tests/fixtures/ike-persisted-fixlist.json", "utf8"));
const DOMAIN = "https://www.ikessandwich.com";
const PATHS = {
  legal_info: "/legal/", standard: "/menu/", unknown: "/?ref=", guide_article: "/guides/",
  contact: "/contact/", location_landing: "/locations/", mixed: "/p/",
};
const CATEGORY = {
  missing_meta_description: "meta_description", image_alt_text: "image_alt_text",
  canonical_missing: "canonical", missing_h1: "thin_content", sitemap_redirect: "web_dev",
  internal_link_redirect: "internal_link", redirect_destination_noindex: "indexability",
};

function persistedCards() {
  return FIXTURE.cards.map((card) => {
    const base = PATHS[card.page_template_family] || "/p/";
    const pages = Array.from({ length: card.page_count }, (_, i) => `${DOMAIN}${base}${card.fix_id.slice(-4)}-${i}`);
    return {
      ...card,
      id: card.fix_id,
      category: CATEGORY[card.rule] || "web_dev",
      affected_pages: pages,
      affectedPages: pages,
      pageCount: card.page_count,
      templateFamily: card.page_template_family,
      who_can_do_this: "your_web_person",
    };
  });
}

test("the fixture is the reported persisted shape, not a model of it", () => {
  assert.equal(FIXTURE.cards.length, 14);
  const perRule = {};
  const affectedPerRule = {};
  for (const card of FIXTURE.cards) {
    perRule[card.rule] = (perRule[card.rule] || 0) + 1;
    affectedPerRule[card.rule] = (affectedPerRule[card.rule] || 0) + card.page_count;
  }
  assert.deepEqual(perRule, {
    sitemap_redirect: 5, missing_meta_description: 3, image_alt_text: 2,
    missing_h1: 1, internal_link_redirect: 1, canonical_missing: 1, redirect_destination_noindex: 1,
  });
  assert.deepEqual(affectedPerRule, {
    sitemap_redirect: 43, missing_meta_description: 14, image_alt_text: 127,
    missing_h1: 6, internal_link_redirect: 1, canonical_missing: 105, redirect_destination_noindex: 105,
  });
});

test("historical rows without repair fingerprints remain separate", () => {
  const cards = buildRepairCards(persistedCards());
  assert.equal(cards.length, 14, "missing repair identity must not be guessed from rule/type");
  for (const card of cards) {
    assert.equal(card.evidence.mergedFromFixIds.length, 1);
  }
});

test("no historical evidence is lost when unidentified rows stay separate", () => {
  const projected = mergeCustomerActions(persistedCards());
  const totals = {};
  for (const card of projected) totals[card.rule] = (totals[card.rule] || 0) + card.pageCount;
  assert.equal(totals.sitemap_redirect, 43);
  assert.equal(totals.missing_meta_description, 14);
  assert.equal(totals.image_alt_text, 127);
  assert.equal(totals.canonical_missing, 105);
  assert.equal(totals.redirect_destination_noindex, 105);

  // Every affected URL from every persisted row survives.
  const persistedUrls = new Set(persistedCards().flatMap((card) => card.affectedPages));
  const projectedUrls = new Set(projected.flatMap((card) => card.affectedPages));
  assert.equal(projectedUrls.size, persistedUrls.size);
  for (const url of persistedUrls) assert.ok(projectedUrls.has(url), `${url} was dropped`);
});

test("historical family evidence stays attached to its persisted row", () => {
  const cards = buildRepairCards(persistedCards());
  const sitemapRows = cards.filter((card) => card.rule === "sitemap_redirect");
  assert.equal(sitemapRows.length, 5);
  assert.deepEqual(
    sitemapRows.map((card) => card.evidence.familyBreakdown),
    [{ legal_info: 3 }, { standard: 37 }, { unknown: 1 }, { guide_article: 1 }, { contact: 1 }],
  );
  const claimed = sitemapRows.flatMap((card) => card.evidence.mergedFromFixIds);
  assert.equal(new Set(claimed).size, 5);
  assert.ok(claimed.includes("finding_d459094e8269"));
});

test("every card answers the five questions", () => {
  for (const card of buildRepairCards(persistedCards())) {
    assert.ok(card.title, "what is wrong");
    assert.ok(card.whyItMatters, `why it matters missing on: ${card.title}`);
    assert.ok(card.where, `where missing on: ${card.title}`);
    assert.ok(card.whatToChange, `what to change missing on: ${card.title}`);
    assert.ok(card.who, `who missing on: ${card.title}`);
  }
});

test("no card falls back to generic filler", () => {
  // Two of Ike's rules had no customer copy at all and rendered as "Review this
  // website improvement" with "Review the affected page and make the
  // recommended update" -- a card that tells the customer nothing.
  for (const card of buildRepairCards(persistedCards())) {
    assert.doesNotMatch(card.title, /^Review this/i, `generic title: ${card.title}`);
    assert.doesNotMatch(card.whatToChange, /^Review the affected page/i, `generic instruction: ${card.title}`);
    assert.doesNotMatch(card.whatToChange, /^Review this recommendation/i, `generic instruction: ${card.title}`);
  }
});

test("no classifier vocabulary reaches the customer", () => {
  const text = JSON.stringify(buildRepairCards(persistedCards()).map((card) => ({
    title: card.title, whyItMatters: card.whyItMatters, where: card.where,
    whatToChange: card.whatToChange, who: card.who,
  })));
  for (const term of ["legal_info", "location_landing", "guide_article", "your_web_person", "unclassified"]) {
    assert.doesNotMatch(text, new RegExp(term, "i"), `${term} reached the customer`);
  }
  // "mixed" and "unknown" are classifier states, never page types.
  assert.doesNotMatch(text, /\bmixed pages?\b/i);
  assert.doesNotMatch(text, /\bunknown pages?\b/i);
});

test("a proven merged action never claims one family's identity", () => {
  // A shared fingerprint is the evidence that these rows are one action.
  const rows = persistedCards()
    .filter((card) => card.rule === "missing_meta_description")
    .map((card) => ({ ...card, repair_fingerprint: "shared-meta-action" }));
  const [meta] = buildRepairCards(rows);
  assert.match(meta.title, /your pages/, `merged card named one family: ${meta.title}`);
  assert.doesNotMatch(meta.whatToChange, /shared standard template/i);
  assert.doesNotMatch(meta.whatToChange, /shared legal template/i);
  // The classifier's default bucket has no customer-facing name, so it cannot
  // be listed -- but its pages still exist, and the sentence must not read as
  // though the families it *can* name account for all 14.
  assert.match(meta.where, /14 pages/);
  assert.match(meta.where, /legal/);
  assert.match(meta.where, /\bother\b/, `unnamed pages absorbed into a named family: ${meta.where}`);
  assert.doesNotMatch(meta.where, /^14 legal pages/, "a mixed card claimed one family's identity");
});

test("a single-family card still names its family", () => {
  const cards = buildRepairCards(persistedCards());
  const canonical = cards.find((card) => card.technicalLabel === "Canonical URL");
  assert.equal(canonical.title, "Tell search engines which version of your location pages to show");
  assert.match(canonical.where, /105 location pages/);
});

test("Where reports the count once, with what kind of pages", () => {
  // The current cards repeat the count twice and add nothing: "1 affected page
  // found in this scan" then "1 checked page is affected".
  // "standard" is the classifier's default bucket, so it drops out of the
  // sentence rather than being named -- "6 standard pages" told an owner
  // nothing about which pages to open.
  assert.equal(whereLine({ pageCount: 1, page_template_family: "standard", affected_pages: ["/a"] }), "1 page on your site.");
  assert.equal(whereLine({ pageCount: 6, page_template_family: "standard", affected_pages: [] }), "6 pages on your site.");
  // 5 of these 9 are in the unnamed default bucket, so the sentence says so
  // rather than presenting all 9 as legal pages.
  assert.equal(
    whereLine({ pageCount: 9, family_breakdown: { standard: 5, legal_info: 4 }, affected_pages: [] }),
    "9 pages, across legal and other pages.",
  );
  // An opaque classification drops out of the sentence rather than being named.
  assert.equal(whereLine({ pageCount: 4, page_template_family: "mixed", affected_pages: [] }), "4 pages on your site.");
  assert.equal(whereLine({ pageCount: 0, affected_pages: [] }), "");
});

test("owner is always a human label", () => {
  for (const card of buildRepairCards(persistedCards())) {
    assert.doesNotMatch(card.who, /_/, `${card.title} exposed an enum: ${card.who}`);
    assert.ok(["Developer", "SEO manager", "Content team", "You"].includes(card.who), `unexpected role: ${card.who}`);
  }
});

test("genuinely different repairs stay separate", () => {
  // Sitemap redirects and internal-link redirects are different repairs.
  const cards = buildRepairCards(persistedCards());
  const sitemapRows = cards.filter((card) => card.rule === "sitemap_redirect");
  const links = cards.find((card) => card.rule === "internal_link_redirect");
  assert.equal(sitemapRows.length, 5);
  assert.ok(links);
  assert.equal(sitemapRows.reduce((sum, card) => sum + card.evidence.pageCount, 0), 43);
  assert.equal(links.evidence.pageCount, 1);
});

test("merging is order-independent and idempotent", () => {
  const forward = buildRepairCards(persistedCards()).map((card) => card.title).sort();
  const reversed = buildRepairCards(persistedCards().reverse()).map((card) => card.title).sort();
  assert.deepEqual(reversed, forward, "card set must not depend on persisted row order");
  const once = mergeCustomerActions(persistedCards());
  const twice = mergeCustomerActions(once);
  assert.equal(twice.length, once.length);
  assert.deepEqual(twice.map((c) => c.pageCount), once.map((c) => c.pageCount));
});

test("merging never shrinks a total the scan already proved", () => {
  // A persisted card can declare more affected pages than it lists: the review
  // caps the visible list. Rebuilding the count from the merged list would
  // quietly reduce a number the scan established, which is the page-count
  // integrity the release gate depends on.
  const capped = [
    {
      fix_id: "a", rule: "image_alt_text", category: "image_alt_text",
      repair_fingerprint: "shared-image-alt-action",
      page_template_family: "standard", templateFamily: "standard",
      affectedPages: ["https://x.test/1", "https://x.test/2"], affected_pages: ["https://x.test/1", "https://x.test/2"],
      pageCount: 60, page_count: 60,
    },
    {
      fix_id: "b", rule: "image_alt_text", category: "image_alt_text",
      repair_fingerprint: "shared-image-alt-action",
      page_template_family: "location_landing", templateFamily: "location_landing",
      affectedPages: ["https://x.test/3"], affected_pages: ["https://x.test/3"],
      pageCount: 45, page_count: 45,
    },
  ];
  const [merged] = mergeCustomerActions(capped);
  assert.equal(merged.pageCount, 105, "the declared totals must be summed, not the visible URLs counted");
  assert.equal(merged.affectedPages.length, 3, "the visible list stays what was actually listed");

  const [card] = buildRepairCards(capped);
  assert.equal(card.evidence.pageCount, 105);
  assert.match(card.where, /105 pages/);
});

test("every customer action stays traceable to its persisted rows", () => {
  // The evidence panel promises the persisted IDs behind every action. Cards
  // built from one row are the majority here, so traceability that held only
  // for merged cards would be traceability for three cards out of seven.
  const persisted = persistedCards();
  const cards = buildRepairCards(persisted);
  const claimed = new Set(cards.flatMap((card) => card.evidence.mergedFromFixIds));

  for (const card of cards) {
    assert.ok(card.evidence.mergedFromFixIds.length > 0, `${card.title} lists no persisted row`);
  }
  for (const row of persisted) {
    assert.ok(claimed.has(row.fix_id), `${row.fix_id} is not reachable from any card`);
  }
  // Every persisted row is claimed exactly once, so none is double counted.
  const all = cards.flatMap((card) => card.evidence.mergedFromFixIds);
  assert.equal(all.length, persisted.length);
  assert.equal(new Set(all).size, persisted.length);
});

test("a blocked canonical target is not treated as a missing canonical", () => {
  // The generic `rule.includes("canonical")` branch matches this rule, and its
  // copy told the customer to ADD a canonical URL to pages that already have
  // one. The defect is where the existing canonical points, not that it is
  // absent, so this rule must be handled before that branch.
  const canonical = customerCopyForFix({ rule: "canonical_target_noindex", page_count: 4, affected_pages: ["/a"] });
  assert.doesNotMatch(canonical.title, /which version of (these|this|your)/i, "told to set a canonical that already exists");
  assert.doesNotMatch(canonical.recommendation, /^Add the correct preferred-page setting/i);
  assert.match(canonical.recommendation, /allowed in search|remove the block/i);
  // Nor is it a redirect: there may be no redirect involved at all.
  assert.doesNotMatch(canonical.title, /redirect/i);
  assert.doesNotMatch(canonical.recommendation, /redirect/i);

  // The two neighbouring rules keep their own distinct advice.
  const missing = customerCopyForFix({ rule: "canonical_missing", page_count: 4, affected_pages: ["/a"] });
  const redirect = customerCopyForFix({ rule: "redirect_destination_noindex", page_count: 4, affected_pages: ["/a"] });
  assert.match(missing.title, /which version/i);
  assert.match(redirect.title, /redirect/i);
  assert.equal(new Set([canonical.title, missing.title, redirect.title]).size, 3);
});

test("applying vocabulary never erases the customer category", () => {
  // applyCustomerVocabulary copies customerCategory straight through, so a
  // branch that omits it replaces the persisted category with undefined.
  for (const rule of [
    "image_alt_text",
    "redirect_destination_noindex",
    "canonical_target_noindex",
    "redirect_destination_failed",
    "redirect_destination_blocked",
    "missing_meta_description",
    "canonical_missing",
    "missing_h1",
  ]) {
    const applied = applyCustomerVocabulary({ rule, category: "web_dev", page_count: 3, affected_pages: ["/a"] });
    assert.ok(applied.customerCategory, `${rule} produced no customer category`);
    assert.notEqual(applied.customerCategory, undefined, `${rule} erased the category`);
    assert.doesNotMatch(applied.customerCategory, /_/, `${rule} produced an internal token`);
  }
});
