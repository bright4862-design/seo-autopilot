import assert from "node:assert/strict";
import test from "node:test";

import {
  EFFORT_LEVELS,
  FIX_SCOPES,
  REPAIR_ROLES,
  REPAIR_SUGGESTION_FALLBACK,
  REPAIR_SUGGESTION_LIBRARY_VERSION,
  REPAIR_TYPES,
  buildRepairGroupSummaries,
  hasSharedRepairEvidence,
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
    for (const variant of ["single", "shared"]) {
      for (const field of ["suggestedFix", "bestApproach", "effort", "role", "fixScope"]) {
        assert.ok(
          String(entry[variant][field] || "").trim(),
          `${repairType}.${variant}.${field} is empty`,
        );
      }
      // The launch vocabulary is deliberately small; the library may not invent
      // a fourth scope, a fourth effort level, or an off-menu role.
      assert.ok(FIX_SCOPES.includes(entry[variant].fixScope), `${repairType}.${variant} scope`);
      assert.ok(EFFORT_LEVELS.includes(entry[variant].effort), `${repairType}.${variant} effort`);
      assert.ok(REPAIR_ROLES.includes(entry[variant].role), `${repairType}.${variant} role`);
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
  assert.equal(suggestion.effort, "");
  assert.equal(suggestion.effortLabel, "");
  assert.equal(suggestion.effortDisplay, "");
  assert.equal(suggestion.fixScope, "");
  assert.equal(suggestion.fixScopeLabel, "");
  assert.equal(suggestion.role, "");
});

test("the unknown-repair fallback is the exact launch copy", () => {
  assert.equal(REPAIR_SUGGESTION_FALLBACK, "Review this issue based on the evidence collected.");
  assert.equal(repairSuggestion({ rule: "nope" }).suggestedFix, REPAIR_SUGGESTION_FALLBACK);
  assert.equal(repairSuggestion({}).suggestedFix, REPAIR_SUGGESTION_FALLBACK);
});

test("no rendered suggestion field is ever undefined, null, or a non-string", () => {
  const renderedFields = [
    "suggestedFix",
    "bestApproach",
    "fallback",
    "label",
    "groupTitle",
    "fixScope",
    "fixScopeLabel",
    "effort",
    "effortLabel",
    "effortDetail",
    "effortDisplay",
    "role",
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

test("shared-repair evidence is required before a template fix is suggested", () => {
  assert.equal(hasSharedRepairEvidence({ rule: "missing_h1", page_count: 40 }), false);
  assert.equal(hasSharedRepairEvidence({ rule: "missing_h1", page_count: 40, page_template_family: "mixed" }), false);
  assert.equal(hasSharedRepairEvidence({ rule: "missing_h1", page_count: 40, page_template_family: "collection_page" }), true);
  assert.equal(hasSharedRepairEvidence({ rule: "missing_h1", page_count: 1, shared_repair_confirmed: true }), true);
  assert.equal(hasSharedRepairEvidence({ rule: "missing_h1", repair_surface: "cms_field" }), true);

  assert.equal(repairFixScope({ rule: "missing_h1", page_count: 40 }), "page");
  assert.equal(repairFixScope({ rule: "missing_h1", page_count: 40, page_template_family: "collection_page" }), "template");
});

test("fix scope reflects where the repair lives, not just how many pages report it", () => {
  // A redirect chain is repaired in link sources and redirect rules, so it is
  // sitewide even when a single page reports it.
  assert.equal(repairFixScope({ rule: "redirect_chain", page_count: 1, affected_pages: ["/"] }), "sitewide");
  assert.equal(repairFixScope({ rule: "sitemap_redirect", page_count: 1 }), "sitewide");
  assert.equal(repairFixScope({ rule: "potential_orphan_pages", page_count: 1 }), "sitewide");
  // A missing description on one page really is a one-page edit.
  assert.equal(repairFixScope({ rule: "missing_meta_description", page_count: 1 }), "page");
});

test("every rendered scope, effort, and role stays inside the launch vocabulary", () => {
  const items = [
    { rule: "missing_meta_description", page_count: 49, page_template_family: "collection_page" },
    { rule: "redirect_chain", page_count: 1 },
    { rule: "thin_content", page_count: 12, shared_repair_confirmed: true },
    { rule: "noindex_page", page_count: 1 },
  ];

  for (const item of items) {
    const suggestion = repairSuggestion(item);
    assert.ok(FIX_SCOPES.includes(suggestion.fixScope));
    assert.ok(EFFORT_LEVELS.includes(suggestion.effort));
    assert.ok(REPAIR_ROLES.includes(suggestion.role));
    assert.ok(["Page", "Template", "Sitewide"].includes(suggestion.fixScopeLabel));
    assert.ok(["Low", "Medium", "High"].includes(suggestion.effortLabel));
  }
});

test("the library never invents an hour estimate; only the scanner may supply one", () => {
  assert.equal(repairSuggestion({ rule: "missing_meta_description" }).effortDetail, "");
  assert.equal(repairSuggestion({ rule: "missing_meta_description" }).effortDisplay, "Low");
  assert.equal(
    repairSuggestion({ rule: "missing_meta_description", estimated_time: "45 minutes" }).effortDisplay,
    "Low · 45 minutes",
  );
});

test("a single-page repair is not described as a template repair", () => {
  const suggestion = repairSuggestion({
    rule: "missing_meta_description",
    page_count: 1,
    affected_pages: ["/"],
    page_template_family: "homepage",
  });

  assert.equal(suggestion.fixScope, "page");
  assert.equal(suggestion.fixScopeLabel, "Page");
  assert.equal(suggestion.sharedRepairEvidence, false);
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
  assert.equal(suggestion.fixScopeLabel, "Template");
  assert.equal(suggestion.sharedRepairEvidence, true);
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
  assert.equal(suggestion.role, "Developer");
  assert.equal(suggestion.roleSource, "scanner_evidence");
  assert.equal(suggestion.effortDetail, "45 minutes");
  // The library value stays available for comparison but is not what is shown.
  assert.notEqual(suggestion.librarySuggestedFix, suggestion.suggestedFix);
});

test("a scanner needs-developer bucket is honored as the recommended role", () => {
  const suggestion = repairSuggestion({ rule: "missing_meta_description", needsHelp: true });
  assert.equal(suggestion.role, "Developer");
  assert.equal(suggestion.roleSource, "scanner_evidence");
});

test("an unrecognized scanner role is passed through rather than overwritten", () => {
  // Scanner text is evidence. Normalization maps known synonyms only.
  const suggestion = repairSuggestion({ rule: "missing_h1", who_can_do_this: "Platform team" });
  assert.equal(suggestion.role, "Platform team");
  assert.equal(suggestion.roleSource, "scanner_evidence");
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
