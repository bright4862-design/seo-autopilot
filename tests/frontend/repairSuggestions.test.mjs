import assert from "node:assert/strict";
import test from "node:test";

import {
  REPAIR_SUGGESTION_FALLBACK,
  REPAIR_SUGGESTION_LIBRARY_VERSION,
  REPAIR_TYPES,
  buildRepairGroupSummaries,
  repairFixScope,
  repairSuggestion,
  repairSuggestionEntry,
  repairTypeOf,
} from "../../src/lib/repairSuggestions.js";

const REQUIRED_REPAIR_TYPES = [
  "missing_title",
  "duplicate_title",
  "missing_meta_description",
  "duplicate_meta_description",
  "missing_h1",
  "multiple_h1",
  "canonical_issue",
  "redirect_chain",
  "broken_internal_link",
  "hard_to_discover_page",
  "sitemap_redirect",
  "noindex_issue",
  "thin_or_duplicate_template",
];

test("every launch repair type has a complete suggestion entry", () => {
  for (const repairType of REQUIRED_REPAIR_TYPES) {
    const entry = repairSuggestionEntry(repairType);
    assert.ok(entry, `missing suggestion entry for ${repairType}`);
    for (const scope of ["page", "template"]) {
      for (const field of ["suggestedFix", "bestApproach", "effort", "effortDetail", "recommendedRole", "fixStrategy"]) {
        assert.ok(
          String(entry[scope][field] || "").trim(),
          `${repairType}.${scope}.${field} is empty`,
        );
      }
    }
  }
});

test("scanner rules map to the repair type a customer acts on", () => {
  const cases = [
    ["missing_title", REPAIR_TYPES.MISSING_TITLE],
    ["duplicate_title_template", REPAIR_TYPES.DUPLICATE_TITLE],
    ["duplicate_title_localized", REPAIR_TYPES.DUPLICATE_TITLE],
    ["missing_meta_description", REPAIR_TYPES.MISSING_META_DESCRIPTION],
    ["empty_meta_description", REPAIR_TYPES.MISSING_META_DESCRIPTION],
    ["malformed_meta_description", REPAIR_TYPES.MISSING_META_DESCRIPTION],
    ["meta_description_unusable", REPAIR_TYPES.MISSING_META_DESCRIPTION],
    ["duplicate_meta_description", REPAIR_TYPES.DUPLICATE_META_DESCRIPTION],
    ["missing_h1", REPAIR_TYPES.MISSING_H1],
    ["multiple_h1", REPAIR_TYPES.MULTIPLE_H1],
    ["canonical_missing", REPAIR_TYPES.CANONICAL_ISSUE],
    ["canonical_loop", REPAIR_TYPES.CANONICAL_ISSUE],
    ["redirect_chain", REPAIR_TYPES.REDIRECT_CHAIN],
    ["internal_link_redirect", REPAIR_TYPES.REDIRECT_CHAIN],
    ["broken_page", REPAIR_TYPES.BROKEN_INTERNAL_LINK],
    ["soft_404", REPAIR_TYPES.BROKEN_INTERNAL_LINK],
    ["potential_orphan_pages", REPAIR_TYPES.HARD_TO_DISCOVER_PAGE],
    ["sitemap_redirect", REPAIR_TYPES.SITEMAP_REDIRECT],
    ["noindex_canonical_conflict", REPAIR_TYPES.NOINDEX_ISSUE],
    ["robots_directive_conflict", REPAIR_TYPES.NOINDEX_ISSUE],
    ["thin_content", REPAIR_TYPES.THIN_OR_DUPLICATE_TEMPLATE],
    ["duplicate_content", REPAIR_TYPES.THIN_OR_DUPLICATE_TEMPLATE],
  ];

  for (const [rule, expected] of cases) {
    assert.equal(repairTypeOf({ rule }), expected, `rule ${rule}`);
    assert.equal(repairTypeOf({ original: { rule } }), expected, `persisted rule ${rule}`);
  }
});

test("duplicate rules are never collapsed into their missing-field counterparts", () => {
  assert.equal(repairTypeOf({ rule: "duplicate_meta_description_v3" }), REPAIR_TYPES.DUPLICATE_META_DESCRIPTION);
  assert.equal(repairTypeOf({ rule: "duplicate_title_v9" }), REPAIR_TYPES.DUPLICATE_TITLE);
  assert.notEqual(repairTypeOf({ rule: "duplicate_meta_description" }), REPAIR_TYPES.MISSING_META_DESCRIPTION);
});

test("an unknown scanner rule reports no suggestion instead of an undefined one", () => {
  const suggestion = repairSuggestion({ rule: "some_future_scanner_rule" });

  assert.equal(suggestion.suggestionAvailable, false);
  assert.equal(suggestion.repairType, "");
  assert.equal(suggestion.fallback, REPAIR_SUGGESTION_FALLBACK);
  assert.equal(suggestion.suggestedFix, REPAIR_SUGGESTION_FALLBACK);
  assert.equal(suggestion.suggestedFixSource, "manual_review_fallback");
  // Effort and role are withheld rather than invented for a rule FixList does
  // not recognize.
  assert.equal(suggestion.effortLabel, "");
  assert.equal(suggestion.recommendedRole, "");
});

test("no rendered suggestion field is ever undefined, null, or a non-string", () => {
  const renderedFields = [
    "suggestedFix",
    "bestApproach",
    "fallback",
    "label",
    "groupTitle",
    "fixStrategy",
    "fixStrategyLabel",
    "effort",
    "effortDetail",
    "effortLabel",
    "recommendedRole",
  ];
  const items = [
    {},
    { rule: "" },
    { rule: "totally_unknown" },
    { rule: "missing_meta_description" },
    { rule: "redirect_chain", page_count: 12, page_template_family: "collection_page" },
  ];

  for (const item of items) {
    const suggestion = repairSuggestion(item);
    for (const field of renderedFields) {
      assert.equal(typeof suggestion[field], "string", `${field} is not a string`);
    }
    assert.ok(suggestion.suggestedFix.length > 0, "suggestedFix must never render empty");
  }
});

test("every suggestion carries the library version so wording can be compared over time", () => {
  assert.equal(REPAIR_SUGGESTION_LIBRARY_VERSION, "v1");
  assert.equal(repairSuggestion({ rule: "missing_h1" }).libraryVersion, "v1");
  assert.equal(repairSuggestion({ rule: "unknown" }).libraryVersion, "v1");
});

test("template strategy requires published evidence, not a page count alone", () => {
  assert.equal(repairFixScope({ rule: "missing_h1", page_count: 40 }), "page");
  assert.equal(repairFixScope({ rule: "missing_h1", page_count: 40, page_template_family: "mixed" }), "page");
  assert.equal(repairFixScope({ rule: "missing_h1", page_count: 40, page_template_family: "collection_page" }), "template");
  assert.equal(repairFixScope({ rule: "missing_h1", page_count: 1, shared_repair_confirmed: true }), "template");
  assert.equal(repairFixScope({ rule: "missing_h1", repair_surface: "cms_field" }), "template");
});

test("a single-page repair is not described as a template repair", () => {
  const suggestion = repairSuggestion({
    rule: "missing_meta_description",
    page_count: 1,
    affected_pages: ["/"],
    page_template_family: "homepage",
  });

  assert.equal(suggestion.fixScope, "page");
  assert.equal(suggestion.fixStrategy, "page");
  assert.match(suggestion.suggestedFix, /this page/i);
});

test("a confirmed shared repair is described as one template change", () => {
  const suggestion = repairSuggestion({
    rule: "missing_meta_description",
    page_count: 49,
    page_template_family: "collection_page",
    shared_repair_confirmed: true,
  });

  assert.equal(suggestion.fixScope, "template");
  assert.equal(suggestion.fixStrategy, "template");
  assert.equal(suggestion.fixStrategyLabel, "Fix the template once");
  assert.match(suggestion.suggestedFix, /template/i);
  assert.match(suggestion.bestApproach, /shared templates/i);
});

test("scanner-published remediation, role, and effort outrank the library table", () => {
  const suggestion = repairSuggestion({
    rule: "missing_h1",
    recommendation: "Add the heading block back to the Funbooker activity layout.",
    who_can_do_this: "Front-end developer",
    estimated_time: "45 minutes",
  });

  assert.equal(suggestion.suggestedFix, "Add the heading block back to the Funbooker activity layout.");
  assert.equal(suggestion.suggestedFixSource, "scanner_evidence");
  assert.equal(suggestion.recommendedRole, "Front-end developer");
  assert.equal(suggestion.recommendedRoleSource, "scanner_evidence");
  assert.equal(suggestion.effortDetail, "45 minutes");
  assert.equal(suggestion.effortSource, "scanner_evidence");
  // The library value stays available for comparison but is not what is shown.
  assert.notEqual(suggestion.librarySuggestedFix, suggestion.suggestedFix);
});

test("a scanner needs-developer bucket is honored as the recommended role", () => {
  const suggestion = repairSuggestion({ rule: "missing_meta_description", needsHelp: true });
  assert.equal(suggestion.recommendedRole, "Web developer");
  assert.equal(suggestion.recommendedRoleSource, "scanner_evidence");
});

test("the suggestion layer never mutates the repair it reads", () => {
  const item = Object.freeze({
    rule: "redirect_chain",
    page_count: 3,
    affected_pages: Object.freeze(["/a", "/b", "/c"]),
    page_template_family: "collection_page",
  });
  const before = JSON.stringify(item);

  repairSuggestion(item);
  buildRepairGroupSummaries([{ item }]);

  assert.equal(JSON.stringify(item), before);
});
