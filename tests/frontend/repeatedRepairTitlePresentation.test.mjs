import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import {
  buildRepairCards,
  repairFingerprintOf,
  whereLine,
  withRepeatedTitleScopeHints,
} from "../../src/lib/repairCardModel.js";

/**
 * Two cards with the same headline are not evidence of one repair.
 *
 * The September 6 matrix produced FixLists carrying several cards reading
 * "Send visitors straight to the right page" with nothing on the collapsed
 * card to tell them apart, so the obvious fix is to merge them -- and merging
 * them would be wrong. A redirect in a sitemap and a redirect in a navigation
 * link are different repairs done in different places by different people.
 * `repair_fingerprint` is the backend's own statement of repair identity, and
 * it is the only thing that may collapse two rows.
 *
 * So the cards stay separate, and the disambiguation goes into the metadata
 * line instead: enough scope for a customer to tell two cards apart before
 * opening either.
 */

function redirectRow(overrides = {}) {
  return {
    rule: "sitemap_redirect",
    issue_title: "Send visitors straight to the right page",
    priority: "medium",
    category: "internal_link",
    page_count: 3,
    affected_pages: ["/a", "/b", "/c"],
    ...overrides,
  };
}

test("same title, no shared fingerprint: two cards stay two cards", () => {
  const first = redirectRow({ fix_id: "fix_sitemap_1", affected_pages: ["/shop/a", "/shop/b", "/shop/c"] });
  const second = redirectRow({ fix_id: "fix_sitemap_2", affected_pages: ["/blog/x", "/blog/y", "/blog/z"] });

  assert.equal(repairFingerprintOf(first), "", "this fixture must carry no recorded identity");
  assert.equal(repairFingerprintOf(second), "");
  assert.equal(buildRepairCards([first, second]).length, 2);
});

test("the same recorded fingerprint is still one card", () => {
  // The rule cuts both ways: identity the backend did record is authoritative,
  // and disambiguating instead of merging here would undo P0-GROUPING.
  const rows = [
    redirectRow({ fix_id: "fix_a", repair_fingerprint: "rf_same" }),
    redirectRow({ fix_id: "fix_b", repair_fingerprint: "rf_same" }),
  ];
  assert.equal(buildRepairCards(rows).length, 1);
});

test("repeated titles get a scope hint; unique titles do not", () => {
  const cards = withRepeatedTitleScopeHints(buildRepairCards([
    redirectRow({ fix_id: "a", page_template_family: "product_page" }),
    redirectRow({ fix_id: "b", page_template_family: "guide_article" }),
    redirectRow({ fix_id: "c", rule: "missing_h1", issue_title: "Give every page one clear heading", page_template_family: "homepage" }),
  ]));

  const repeated = cards.filter((card) => card.scopeHint);
  assert.equal(repeated.length, 2, "only the two cards sharing a title need telling apart");
  assert.notEqual(repeated[0].scopeHint, repeated[1].scopeHint, "a hint that repeats disambiguates nothing");

  const unique = cards.find((card) => !card.scopeHint);
  assert.ok(unique, "a card whose title already stands alone gets no hint");
  assert.equal(unique.scopeHint, "");
});

test("the hint comes from persisted evidence, in a fixed order of preference", () => {
  // 1. a recognised single page family
  const [family] = withRepeatedTitleScopeHints(buildRepairCards([
    redirectRow({ fix_id: "a", page_template_family: "product_page" }),
    redirectRow({ fix_id: "b", page_template_family: "guide_article" }),
  ]));
  assert.equal(family.scopeHint, "Product pages");

  // 2. no family, but a recorded scope
  const [scope] = withRepeatedTitleScopeHints(buildRepairCards([
    redirectRow({ fix_id: "a", page_scope: "sitewide" }),
    redirectRow({ fix_id: "b", page_template_family: "guide_article" }),
  ]));
  assert.equal(scope.scopeHint, "Across the site");

  // 3. neither: the count, which is at least a number they can compare
  const [count] = withRepeatedTitleScopeHints(buildRepairCards([
    redirectRow({ fix_id: "a", page_count: 7, affected_pages: ["/1", "/2", "/3", "/4", "/5", "/6", "/7"] }),
    redirectRow({ fix_id: "b", page_template_family: "guide_article" }),
  ]));
  assert.equal(count.scopeHint, "7 specific pages");

  // 4. nothing at all: the evidence class, or no hint rather than an invented one.
  // Both rows carry no pages here, because the customer title itself is written
  // singular or plural from the count -- a zero-page row beside a three-page one
  // does not share a title, and would not be a repeated title to disambiguate.
  const classed = withRepeatedTitleScopeHints(buildRepairCards([
    redirectRow({ fix_id: "a", page_count: 0, affected_pages: [], evidence_class: "verified" }),
    redirectRow({ fix_id: "b", page_count: 0, affected_pages: [], evidence_class: "inferred" }),
  ]));
  assert.equal(classed.length, 2);
  assert.equal(classed[0].scopeHint, "Verified");
  assert.equal(classed[1].scopeHint, "Inferred");
});

test("a hint is never guessed from the URLs themselves", () => {
  // The evidence list is the customer's data, not a classifier input. Reading
  // "/products/" out of a path and calling the card "Product pages" would be a
  // claim the scan never made, and it would be wrong on any site that uses
  // that word for something else.
  const source = fs.readFileSync(new URL("../../src/lib/repairCardModel.js", import.meta.url), "utf8");
  const from = source.indexOf("function scopeHintFor");
  const block = source.slice(from, source.indexOf("\n}", from));
  assert.ok(from > -1, "the hint helper must exist");
  assert.doesNotMatch(block, /affectedPages|affected_pages|includes\("\//, "the hint reads evidence fields, not URLs");
});

test("the persisted action key is untouched by disambiguation", () => {
  // The hint is presentation. If it reached customerActionKey it would start
  // splitting cards that the backend said were one repair.
  const source = fs.readFileSync(new URL("../../src/lib/repairCardModel.js", import.meta.url), "utf8");
  const from = source.indexOf("export function customerActionKey");
  const block = source.slice(from, source.indexOf("\n}", source.indexOf("return `row|", from)));
  assert.doesNotMatch(block, /scopeHint/);
});

// ----------------------------------------------------------- Where wording --

test("a family label already ending in 'page' is not given another one", () => {
  // product_page is what the classifier actually emits; product_detail is its
  // legacy name. The unmapped-key fallback turned the live one into
  // "3 product page pages."
  assert.equal(whereLine({ page_count: 3, family_breakdown: { product_page: 3 } }), "3 product pages.");
  assert.equal(whereLine({ page_count: 1, family_breakdown: { product_page: 1 } }), "1 product page.");
  assert.equal(whereLine({ page_count: 3, family_breakdown: { comparison_page: 3 } }), "3 comparison pages.");
  assert.equal(whereLine({ page_count: 4, family_breakdown: { collection_page: 4 } }), "4 collection pages.");
});

test("the homepage is one page, not one homepage page", () => {
  assert.equal(whereLine({ page_count: 1, family_breakdown: { homepage: 1 } }), "1 homepage.");
  assert.equal(whereLine({ page_count: 2, family_breakdown: { homepage: 2 } }), "2 homepages.");
});

test("every family the classifier can emit has customer wording", () => {
  // The list is app/extract.py classify_template's complete return set, plus
  // the legacy names still held in persisted rows. An unmapped key used to be
  // printed with its underscores swapped for spaces, which is how
  // "internal or auth pages" and "loan program pages" reached the page.
  const emitted = [
    "activity_detail", "archive", "booking_or_checkout", "calculator",
    "collection_page", "comparison_page", "contact", "conversion",
    "guide_article", "homepage", "legal_info", "loan_program",
    "location_landing", "product_page", "route_boundary",
    // legacy names, still in the database
    "product_detail", "category_listing", "guide", "qa",
  ];
  for (const family of emitted) {
    const line = whereLine({ page_count: 4, family_breakdown: { [family]: 4 } });
    assert.notEqual(line, "4 pages on your site.", `${family} has no customer wording and dropped out`);
    assert.doesNotMatch(line, /page pages|pages pages|homepage pages/, `${family}: ${line}`);
    assert.doesNotMatch(line, /_/, `${family} leaked a classifier key: ${line}`);
  }
});

test("an unrecognised family drops out rather than printing its key", () => {
  // Silence is the safe failure here. Printing the key verbatim is what put
  // classifier vocabulary on the customer's page, and a family this build does
  // not know is one it cannot describe.
  const line = whereLine({ page_count: 5, family_breakdown: { some_new_bucket: 5 } });
  assert.equal(line, "5 pages on your site.");
  assert.doesNotMatch(line, /some new bucket|some_new_bucket/);
});

test("mixed families still name each kind without doubling the noun", () => {
  assert.equal(
    whereLine({ page_count: 6, family_breakdown: { product_page: 4, homepage: 2 } }),
    "6 pages, across product and home pages.",
  );
  // And the existing shape for unnamed pages is unchanged.
  assert.equal(
    whereLine({ page_count: 9, family_breakdown: { standard: 5, legal_info: 4 } }),
    "9 pages, across legal and other pages.",
  );
});

// ------------------------------------------------------- the card renders it --

test("an empty Where row is not rendered as a blank label", () => {
  // whereLine returns "" for a card with no page count, and the card printed
  // the heading anyway with nothing under it.
  const page = fs.readFileSync(new URL("../../src/pages/FixList.jsx", import.meta.url), "utf8");
  const from = page.indexOf("function CustomerRepairCard");
  const block = page.slice(from, page.indexOf("View affected URLs", from));

  assert.match(block, /card\.where[\s\S]{0,80}\?/, "the Where row must be conditional");
  assert.match(block, />Where</);
  assert.match(block, /scopeHint/, "the hint belongs on the collapsed card, next to the category");
});

test("the page actually applies the hints it renders", () => {
  // Rendering `card.scopeHint` proves nothing on its own: with the helper left
  // out of the card pipeline the field is permanently "", the row silently
  // renders nothing, and every other test here still passes. A value that
  // asserts a capability nothing wired up is the defect shape this file exists
  // to catch, so the wiring is pinned as well as the helper.
  const page = fs.readFileSync(new URL("../../src/pages/FixList.jsx", import.meta.url), "utf8");
  assert.match(page, /withRepeatedTitleScopeHints\(buildRepairCards\(/,
    "the page builds cards without ever asking which titles repeat");

  // And end to end: two same-titled rows through the page's own composition
  // arrive carrying hints that tell them apart.
  const cards = withRepeatedTitleScopeHints(buildRepairCards([
    redirectRow({ fix_id: "a", page_template_family: "product_page" }),
    redirectRow({ fix_id: "b", page_template_family: "location_landing" }),
  ]));
  assert.equal(cards.length, 2);
  assert.deepEqual(cards.map((card) => card.scopeHint), ["Product pages", "Location pages"]);
});

test("the hint sits in the metadata line and never replaces the title", () => {
  const page = fs.readFileSync(new URL("../../src/pages/FixList.jsx", import.meta.url), "utf8");
  const from = page.indexOf("function CustomerRepairCard");
  const block = page.slice(from, page.indexOf("<dl", from));

  assert.match(block, /\{card\.title\}/, "the title stays exactly as analytics and screen readers see it");
  const titleLine = block.slice(block.indexOf("<h4"), block.indexOf("</h4>"));
  assert.doesNotMatch(titleLine, /scopeHint/, "the hint must not be appended to the repair title");
});
