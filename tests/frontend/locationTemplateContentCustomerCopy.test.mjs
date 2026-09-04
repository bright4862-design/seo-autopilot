import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { buildRepairCards } from "../../src/lib/repairCardModel.js";
import { applyCustomerVocabulary, customerCopyForFix } from "../../src/lib/fixVocabulary.js";
import { REPAIR_SUGGESTION_FALLBACK, repairSuggestion, repairTypeOf } from "../../src/lib/repairSuggestions.js";

/**
 * The scanner learned to detect broken location-page template content, and the
 * browser did not learn anything. A rule with no entry in the repair tables
 * still renders -- that is what the fallbacks are for -- but it renders as an
 * unrecognized repair: the generic "Website improvement" category, the raw rule
 * name as its technical label, no fix scope, and a "decide whether this is a
 * single-page or template change" placeholder sitting directly under a scanner
 * explanation that already says it is a shared template problem.
 *
 * A real export of centerstreetlending.com carried this finding as the site's
 * top recommendation, categorized "Website improvement", while the rule was
 * still unmapped. The effort line survived the gap, because normalize_fix
 * supplies an estimate for every fix regardless.
 *
 * These prove the two halves agree.
 */

const RULE = "broken_location_template_content";

function scannerFix(overrides = {}) {
  // The fields below are the ones build_location_template_raw_fixes publishes
  // that survive normalization into the browser.
  return {
    id: "loc-1",
    fix_id: "loc-1",
    rule: RULE,
    category: "web_dev",
    priority: "high",
    issue_title: "Fix broken location-page template content",
    title: "Fix broken location-page template content",
    plain_english_explanation:
      "FixList found unresolved location variables and wrong-market geographic copy on 6 location pages. This points to a shared location template or variable-mapping problem, not separate copy edits.",
    why_it_matters:
      "Publishing unresolved placeholders or copy for the wrong market can confuse customers and search engines about which location the page serves, weakening trust and local relevance.",
    recommendation:
      "Fix the shared location template and its geographic variables so each page renders the intended market name, then verify representative location pages before publishing.",
    affected_pages: ["/locations/austin", "/locations/dallas"],
    page_count: 6,
    page_template_family: "location_landing",
    difficulty: "developer",
    requires_developer: true,
    who_can_do_this: "your_web_person",
    // normalize_fix fills these downstream for every fix, so a fixture without
    // them is not the shape the browser actually receives.
    estimated_time: "about 1\u20132 hours",
    time_estimate: "about 1\u20132 hours",
    ...overrides,
  };
}

test("the rule the scanner emits is the rule the browser maps", () => {
  // The contract that actually failed. The scanner shipped this rule name and
  // nothing on the customer side referenced it, so every assertion below would
  // pass against a rule no scan ever produces if the two names drifted.
  const detector = fs.readFileSync(
    new URL("../../scanner-api/app/location_template_content.py", import.meta.url),
    "utf8",
  );
  assert.match(
    detector,
    new RegExp(`"rule":\\s*"${RULE}"`),
    "the scanner no longer emits the rule the customer copy is written for",
  );
  assert.notEqual(repairTypeOf({ rule: RULE }), "", "the browser must recognize the rule the scanner emits");
});

test("a broken location template is a recognized repair, not one to review manually", () => {
  const suggestion = repairSuggestion(scannerFix());

  assert.equal(suggestion.suggestionAvailable, true);
  assert.equal(suggestion.fallback, "");
  assert.notEqual(suggestion.suggestedFix, REPAIR_SUGGESTION_FALLBACK);
  assert.equal(suggestion.suggestedFixSource, "scanner_evidence", "the scanner's own remediation copy is kept");
});

test("the repair is scoped to the template whether or not shared evidence is attached", () => {
  // The scanner raises this only after grouping the evidence into one
  // shared-template root cause. Offering a page-level approach would send the
  // owner to edit one page while the template keeps printing the same defect on
  // every other location page.
  const withEvidence = repairSuggestion(scannerFix({ shared_repair_confirmed: true }));
  const withoutEvidence = repairSuggestion(scannerFix({ affected_pages: ["/locations/austin"], page_count: 1 }));

  assert.equal(withEvidence.fixScope, "template");
  assert.equal(withoutEvidence.fixScope, "template");
  for (const suggestion of [withEvidence, withoutEvidence]) {
    assert.doesNotMatch(
      suggestion.bestApproach,
      /decide whether this is a single-page change/i,
      "the scan already established this is a shared template repair",
    );
  }
});

test("the card carries an effort and an owner the customer can act on", () => {
  const suggestion = repairSuggestion(scannerFix());
  const [card] = buildRepairCards([applyCustomerVocabulary(scannerFix())]);

  // The scanner's own estimate is what the card shows, and it arrives whether
  // or not this rule is mapped -- a real export of centerstreetlending.com
  // carried "about 1-2 hours" on this finding while the rule was still
  // unmapped. What the library adds is the scale beside it: an unmapped repair
  // has no effortLabel, so effortDisplay is the bare estimate with nothing to
  // read it against.
  assert.equal(card.effort, "about 1\u20132 hours");
  assert.equal(suggestion.effortLabel, "Medium");
  assert.equal(suggestion.effortDisplay, "Medium \u00b7 about 1\u20132 hours");
  assert.equal(card.who, "Developer");
  assert.equal(suggestion.roleSource, "scanner_evidence");
});

test("the owner is still a developer when the scanner names nobody", () => {
  // `who_can_do_this` is what makes the card say Developer today, so the
  // library's own role is never consulted for a complete scanner fix and can
  // drift to something wrong unnoticed. A repair to a shared template is not
  // content-team work whichever half of the system answers.
  function unattributed(overrides = {}) {
    const fix = scannerFix(overrides);
    delete fix.who_can_do_this;
    delete fix.requires_developer;
    delete fix.difficulty;
    return fix;
  }

  // Both variants, because which one answers depends on whether the fix
  // carries shared-repair evidence -- and the owner is the same either way.
  for (const fix of [
    unattributed(),
    unattributed({ affected_pages: ["/locations/austin"], page_count: 1 }),
  ]) {
    const suggestion = repairSuggestion(fix);
    assert.equal(suggestion.role, "Developer", `wrong owner for ${suggestion.sharedRepairEvidence ? "shared" : "single"} variant`);
    assert.equal(suggestion.roleSource, "fixlist_library");
  }
});

test("the raw rule name never reaches the customer", () => {
  const copy = customerCopyForFix(scannerFix());
  const [card] = buildRepairCards([applyCustomerVocabulary(scannerFix())]);

  assert.equal(copy.technicalLabel, "Location page template");
  assert.doesNotMatch(copy.technicalLabel, /broken location template content/i);
  for (const value of [card.title, card.customerCategory, card.whyItMatters, card.whatToChange]) {
    assert.doesNotMatch(String(value), /\b\w+_\w+\b/, `internal vocabulary leaked: ${value}`);
  }
});

test("the finding gets a real category instead of the generic fallback", () => {
  const copy = customerCopyForFix(scannerFix());

  assert.equal(copy.customerCategory, "Page content");
  assert.notEqual(copy.customerCategory, "Website improvement", "the generic fallback tells the customer nothing");
});

test("the scanner's own account of what it found is not overwritten", () => {
  // The scanner names which defect it detected -- an unresolved placeholder,
  // another market's copy, or both. The browser cannot reconstruct that:
  // template_content_issue_types is dropped before the fix reaches it. Copy
  // that replaced this text would trade a specific finding for a generic one.
  const fix = scannerFix();
  const copy = customerCopyForFix(fix);

  assert.equal(copy.explanation, fix.plain_english_explanation);
  assert.equal(copy.whyItMatters, fix.why_it_matters);
  assert.equal(copy.recommendation, fix.recommendation);
});

test("the copy still stands up when the scanner publishes no prose", () => {
  const bare = { rule: RULE, category: "web_dev", affected_pages: ["/locations/austin"], page_count: 1 };
  const copy = customerCopyForFix(bare);

  for (const [field, value] of Object.entries(copy)) {
    assert.equal(typeof value, "string", `${field} must be a string`);
    assert.ok(value.length > 0, `${field} must not be empty`);
  }
  assert.doesNotMatch(copy.explanation, /undefined/);
});

test("the title agrees with how many pages are affected", () => {
  const many = customerCopyForFix(scannerFix());
  const one = customerCopyForFix(scannerFix({ affected_pages: ["/locations/austin"], page_count: 1 }));

  assert.match(many.title, /your location pages/);
  assert.match(one.title, /this location page/);
  assert.doesNotMatch(one.title, /pages/);
});
