import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { buildRepairCards, mergeCustomerActions, whereLine } from "../../src/lib/repairCardModel.js";

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

test("fourteen persisted rows become seven customer actions", () => {
  const cards = buildRepairCards(persistedCards());
  assert.equal(cards.length, 7, cards.map((c) => c.title).join(" | "));
  const titles = cards.map((c) => c.title);
  assert.equal(new Set(titles).size, 7, "no two customer actions may share a title");
});

test("no evidence is lost when rows merge", () => {
  const merged = mergeCustomerActions(persistedCards());
  const totals = Object.fromEntries(merged.map((card) => [card.rule, card.pageCount]));
  assert.equal(totals.sitemap_redirect, 43);
  assert.equal(totals.missing_meta_description, 14);
  assert.equal(totals.image_alt_text, 127);
  assert.equal(totals.canonical_missing, 105);
  assert.equal(totals.redirect_destination_noindex, 105);

  // Every affected URL from every persisted row survives.
  const persistedUrls = new Set(persistedCards().flatMap((card) => card.affectedPages));
  const mergedUrls = new Set(merged.flatMap((card) => card.affectedPages));
  assert.equal(mergedUrls.size, persistedUrls.size);
  for (const url of persistedUrls) assert.ok(mergedUrls.has(url), `${url} was dropped`);
});

test("the family breakdown survives as evidence inside the merged card", () => {
  const cards = buildRepairCards(persistedCards());
  const sitemap = cards.find((card) => card.title.includes("sitemap"));
  assert.deepEqual(sitemap.evidence.familyBreakdown, {
    legal_info: 3, standard: 37, unknown: 1, guide_article: 1, contact: 1,
  });
  assert.equal(sitemap.evidence.mergedFromFixIds.length, 5);
  // The persisted rows remain traceable from the customer card.
  assert.ok(sitemap.evidence.mergedFromFixIds.includes("finding_d459094e8269"));
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

test("a merged card never claims one family's identity", () => {
  // Left carrying the lead row's family, the merged meta-description card would
  // be titled after "standard" and instruct "fix the shared standard template
  // once" for pages spanning three families -- a shared template the evidence
  // does not support.
  const cards = buildRepairCards(persistedCards());
  const meta = cards.find((card) => card.title.includes("search descriptions"));
  assert.match(meta.title, /your pages/, `merged card named one family: ${meta.title}`);
  assert.doesNotMatch(meta.whatToChange, /shared standard template/i);
  assert.doesNotMatch(meta.whatToChange, /shared legal template/i);
  // But it still reports the spread honestly in Where.
  assert.match(meta.where, /14 pages/);
  assert.match(meta.where, /standard/);
  assert.match(meta.where, /legal/);
});

test("a single-family card still names its family", () => {
  const cards = buildRepairCards(persistedCards());
  const canonical = cards.find((card) => card.title.includes("canonical"));
  assert.equal(canonical.title, "Add canonical URLs to your location pages");
  assert.match(canonical.where, /105 location pages/);
});

test("Where reports the count once, with what kind of pages", () => {
  // The current cards repeat the count twice and add nothing: "1 affected page
  // found in this scan" then "1 checked page is affected".
  assert.equal(whereLine({ pageCount: 1, page_template_family: "standard", affected_pages: ["/a"] }), "1 standard page.");
  assert.equal(whereLine({ pageCount: 6, page_template_family: "standard", affected_pages: [] }), "6 standard pages.");
  assert.equal(
    whereLine({ pageCount: 9, family_breakdown: { standard: 5, legal_info: 4 }, affected_pages: [] }),
    "9 pages, across standard and legal pages.",
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
  // Sitemap redirects and internal-link redirects are the same symptom in
  // different places, and must remain two actions.
  const cards = buildRepairCards(persistedCards());
  assert.ok(cards.some((card) => card.title.includes("sitemap")));
  assert.ok(cards.some((card) => /internal|links/i.test(card.title)));
  const sitemap = cards.find((card) => card.title.includes("sitemap"));
  const links = cards.find((card) => /links/i.test(card.title));
  assert.notEqual(sitemap.title, links.title);
  assert.equal(sitemap.evidence.pageCount, 43);
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
      page_template_family: "standard", templateFamily: "standard",
      affectedPages: ["https://x.test/1", "https://x.test/2"], affected_pages: ["https://x.test/1", "https://x.test/2"],
      pageCount: 60, page_count: 60,
    },
    {
      fix_id: "b", rule: "image_alt_text", category: "image_alt_text",
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
