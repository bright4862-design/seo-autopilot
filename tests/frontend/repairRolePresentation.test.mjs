import assert from "node:assert/strict";
import test from "node:test";

import {
  REPAIR_SUGGESTION_FALLBACK,
  REPAIR_SUGGESTION_LIBRARY_VERSION,
  REPAIR_SUGGESTION_VERSION,
} from "../../src/lib/repairSuggestions.js";
import {
  REPAIR_EXPLANATION_FALLBACK,
  REPAIR_ROLE_EXPLANATION_LIBRARY_VERSION,
  REPAIR_ROLE_EXPLANATION_VERSION,
} from "../../src/lib/repairRoleExplanations.js";
import {
  REPAIR_ROLE_PRESENTATION_VERSION,
  repairRolePresentation,
} from "../../src/lib/repairRolePresentation.js";

test("scanner-authored remediation stays authoritative beside role explanation", () => {
  const repair = {
    fix_id: "fix-canonical",
    rule: "canonical_missing",
    action_priority: "fix_first",
    evidence_class: "confirmed_problem",
    page_count: 7,
    authority_sealed: true,
    recommendation: "Use the scanner-authored canonical remediation.",
  };
  const before = structuredClone(repair);
  const actual = repairRolePresentation(repair, "developer");

  assert.equal(actual.version, REPAIR_ROLE_PRESENTATION_VERSION);
  assert.equal(actual.role, "developer");
  assert.equal(actual.suggestion.suggestedFix, repair.recommendation);
  assert.equal(actual.suggestion.suggestedFixSource, "scanner_evidence");
  assert.equal(actual.explanation.explanationAvailable, true);
  assert.equal(actual.explanation.explanationSource, "fixlist_role_library");
  assert.deepEqual(repair, before);
});

test("library remediation remains deterministic when scanner copy is absent", () => {
  const actual = repairRolePresentation({ rule: "missing_h1" }, "owner");
  assert.equal(actual.suggestion.suggestedFixSource, "fixlist_library");
  assert.equal(actual.suggestion.suggestionAvailable, true);
  assert.equal(actual.explanation.explanationAvailable, true);
});

test("missing viewer role falls back only the explanation and does not alter remediation", () => {
  const repair = { rule: "sitemap_redirect", recommendation: "Remove redirected URLs from the sitemap." };
  const actual = repairRolePresentation(repair, "");

  assert.equal(actual.role, "");
  assert.equal(actual.explanation.explanationAvailable, false);
  assert.equal(actual.explanation.explanation, REPAIR_EXPLANATION_FALLBACK);
  assert.equal(actual.suggestion.suggestedFix, repair.recommendation);
  assert.equal(actual.suggestion.suggestedFixSource, "scanner_evidence");
});

test("unmapped rules preserve the existing manual-review fallback without inventing copy", () => {
  const actual = repairRolePresentation({ rule: "future_unmapped_rule" }, "seo");
  assert.equal(actual.suggestion.suggestionAvailable, false);
  assert.equal(actual.suggestion.suggestedFix, REPAIR_SUGGESTION_FALLBACK);
  assert.equal(actual.suggestion.suggestedFixSource, "manual_review_fallback");
  assert.equal(actual.explanation.explanationAvailable, false);
  assert.equal(actual.explanation.explanation, REPAIR_EXPLANATION_FALLBACK);
});

test("presentation carries both content-version chains needed to reconstruct displayed wording", () => {
  const actual = repairRolePresentation({ rule: "duplicate_title_template" }, "marketing");
  assert.equal(actual.suggestion.version, REPAIR_SUGGESTION_VERSION);
  assert.equal(actual.suggestion.libraryVersion, REPAIR_SUGGESTION_LIBRARY_VERSION);
  assert.equal(actual.explanation.version, REPAIR_ROLE_EXPLANATION_VERSION);
  assert.equal(actual.explanation.libraryVersion, REPAIR_ROLE_EXPLANATION_LIBRARY_VERSION);
});

test("identical role-presentation input is byte-stable", () => {
  const repair = {
    fix_id: "stable-1",
    rule: "internal_link_redirect",
    action_priority: "important",
    repair_surface: "shared_navigation",
    recommendation: "Point the navigation link directly at the final URL.",
  };
  const once = JSON.stringify(repairRolePresentation(repair, "marketing"));
  const twice = JSON.stringify(repairRolePresentation(repair, "marketing"));
  assert.equal(once, twice);
});
