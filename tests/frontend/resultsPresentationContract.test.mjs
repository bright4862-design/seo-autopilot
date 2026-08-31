import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { prepareCustomerFixes } from "../../src/lib/fixRanking.js";
import { applyCustomerVocabulary, customerHealthLabel } from "../../src/lib/fixVocabulary.js";

const fixListSource = readFileSync(new URL("../../src/pages/FixList.jsx", import.meta.url), "utf8");

test("Funbooker-style results rank by severity, then scope, without changing scanner priority", () => {
  const items = [
    { id: "low-page-it", rule: "title_over_pixel_limit", priority: "low", pageScope: "page", affectedPages: ["/it/title"], confidenceScore: 88 },
    { id: "high-meta", rule: "meta_description_unusable", priority: "high", pageScope: "family", affectedPages: Array.from({ length: 34 }, (_, i) => `/standard-${i}`), confidenceScore: 92 },
    { id: "critical-redirect", rule: "redirect_chain", priority: "critical", pageScope: "page", affectedPages: ["/"], confidenceScore: 94 },
    { id: "critical-meta", rule: "meta_description_unusable", priority: "critical", pageScope: "family", affectedPages: Array.from({ length: 46 }, (_, i) => `/activity-${i}`), confidenceScore: 92 },
  ];
  const ranked = prepareCustomerFixes(items);
  assert.deepEqual(ranked.slice(0, 3).map((item) => item.id), ["critical-meta", "critical-redirect", "high-meta"]);
  assert.equal(items[0].priority, "low");
});

test("family-level same-rule coverage suppresses duplicate page cards but never merges different rules", () => {
  const items = [
    { id: "title-family", rule: "title_over_pixel_limit", priority: "low", pageScope: "family", affectedPages: ["/de/a", "/it/a", "/pt/a"] },
    { id: "title-de", rule: "title_over_pixel_limit", priority: "low", pageScope: "page", affectedPages: ["/de/a"] },
    { id: "title-it", rule: "title_over_pixel_limit", priority: "low", pageScope: "page", affectedPages: ["/it/a"] },
    { id: "title-pt", rule: "title_over_pixel_limit", priority: "low", pageScope: "page", affectedPages: ["/pt/a"] },
    { id: "orphan", rule: "potential_orphan_pages", priority: "low", pageScope: "family", affectedPages: ["/de/a", "/it/a", "/pt/a"] },
  ];
  const prepared = prepareCustomerFixes(items);
  assert.deepEqual(new Set(prepared.map((item) => item.id)), new Set(["title-family", "orphan"]));
});

test("same customer action collapses repeated evidence groups without hiding affected pages", () => {
  const items = [
    {
      id: "title-template-1",
      rule: "duplicate_title_template",
      priority: "low",
      pageScope: "family",
      templateFamily: "guide_article",
      recommendation: "Update the shared title template so each page has a distinct title.",
      affectedPages: ["/de/a", "/de/b"],
      currentValue: "Two pages share title A",
    },
    {
      id: "title-template-2",
      rule: "duplicate_title_template",
      priority: "low",
      pageScope: "family",
      templateFamily: "guide_article",
      recommendation: "Update the shared title template so each page has a distinct title.",
      affectedPages: ["/nl/a", "/nl/b"],
      currentValue: "Two pages share title B",
    },
    {
      id: "localized-title",
      rule: "duplicate_title_localized",
      priority: "low",
      pageScope: "family",
      templateFamily: "guide_article",
      recommendation: "Verify localization before changing titles.",
      affectedPages: ["/fr/a", "/be/a"],
    },
  ];

  const prepared = prepareCustomerFixes(items);
  assert.equal(prepared.length, 2);
  const template = prepared.find((item) => item.rule === "duplicate_title_template");
  assert.deepEqual(new Set(template.affectedPages), new Set(["/de/a", "/de/b", "/nl/a", "/nl/b"]));
  assert.equal(template.groupedFindingCount, 2);
  assert.equal(template.pageCount, 4);
  assert.equal(template.currentValue, "");
  assert.deepEqual(new Set(template.memberIds), new Set(["title-template-1", "title-template-2"]));
});

test("rule-specific vocabulary keeps SEO jargon out of primary customer copy", () => {
  const canonical = applyCustomerVocabulary({ rule: "canonical_missing", category: "canonical", pageScope: "family", pageCount: 2, affectedPages: ["/terms", "/privacy"] });
  // The title names the action rather than its effect. "Canonical URL" is kept
  // here deliberately: the release owner asked for this wording, and this card
  // is developer-owned, which is the exception the vocabulary guidance allows.
  // The jargon rule still holds everywhere it is not the name of the thing to
  // add -- see the orphan assertion below.
  assert.equal(canonical.title, "Add canonical URLs to these pages");
  assert.equal(canonical.customerCategory, "Search visibility");
  assert.equal(canonical.technicalLabel, "Canonical URL");

  const orphan = applyCustomerVocabulary({ rule: "potential_orphan_pages", category: "indexability", pageCount: 147, affectedPages: ["/a"] });
  assert.equal(orphan.title, "Check whether these pages need more internal links");
  assert.doesNotMatch(orphan.title, /orphan|indexability/i);
});

test("customer titles say what to change and where", () => {
  const homepageRedirect = applyCustomerVocabulary({
    rule: "redirect_chain",
    page_template_family: "homepage",
    page_count: 1,
    affected_pages: ["https://example.com/"],
  });
  assert.equal(homepageRedirect.title, "Update the homepage redirect to point directly to the final URL");

  const homepageLinks = applyCustomerVocabulary({
    rule: "internal_link_redirect",
    page_template_family: "homepage",
    page_count: 1,
    affected_pages: ["https://example.com/"],
  });
  assert.equal(homepageLinks.title, "Update homepage links to use their final URLs");

  const collectionH1 = applyCustomerVocabulary({
    rule: "missing_h1",
    page_template_family: "collection_page",
    page_count: 15,
    affected_pages: Array.from({ length: 15 }, (_, index) => `/collection-${index}`),
  });
  assert.equal(collectionH1.title, "Add one clear main heading to collection pages");

  const repeatedTitles = applyCustomerVocabulary({
    rule: "duplicate_title_template",
    page_template_family: "collection_page",
    page_count: 4,
    affected_pages: ["/a", "/b", "/c", "/d"],
  });
  assert.equal(repeatedTitles.title, "Give collection pages distinct page titles");

  const orphan = applyCustomerVocabulary({
    rule: "potential_orphan_pages",
    page_count: 8,
    affected_pages: ["/a", "/b"],
  });
  assert.equal(orphan.title, "Check whether these pages need more internal links");
});

test("score 60 uses a customer-friendly health label without changing the numeric score", () => {
  assert.equal(customerHealthLabel(60), "Needs attention");
  assert.equal(customerHealthLabel(86), "Looking good");
});

test("customer result page hides internal debug controls and leads with priorities", () => {
  assert.match(fixListSource, /Your priorities/);
  assert.match(fixListSource, /Technical details/);
  assert.match(fixListSource, /pages found/);
  assert.doesNotMatch(fixListSource, />Scan details</);
  assert.doesNotMatch(fixListSource, />Copy JSON</);
  assert.doesNotMatch(fixListSource, />Clear scans</);
});


test("canonical FixLists render merged implementation-plan cards rather than raw persisted rows", () => {
  assert.match(fixListSource, /buildRepairCards/);
  assert.match(fixListSource, /repairPresentation\.canonical === true \? \(\s*<CustomerRepairList/s);
  assert.match(fixListSource, /Why it matters/);
  assert.match(fixListSource, />Where</);
  assert.match(fixListSource, /What to change/);
  assert.match(fixListSource, /Who:/);
  assert.match(fixListSource, /View affected URLs &amp; evidence/);
  assert.match(fixListSource, /activeCount: displayedRepairCount/);
  assert.match(fixListSource, /repairPresentation\.canonical !== true \? <CmsPicker/);
});
