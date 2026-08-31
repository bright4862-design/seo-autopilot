import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { customerCopyForFix } from "../../src/lib/fixVocabulary.js";
import { repairSuggestion } from "../../src/lib/repairSuggestions.js";

// Copy defects seen on Ike's persisted FixList. These are not cosmetic: an
// internal enum, or "this unknown page", reads as a defect in the report itself
// and undermines the evidence presented around it. Asserted through the same
// public entry points the cards render from.

function fix(overrides = {}) {
  return {
    rule: "missing_meta_description",
    category: "meta_description",
    page_url: "https://ikessandwich.com/contact",
    affected_pages: ["https://ikessandwich.com/contact"],
    page_count: 1,
    ...overrides,
  };
}

function allCopy(item) {
  return JSON.stringify(customerCopyForFix(item));
}

test("a classifier state never reaches the customer as a page type", () => {
  for (const state of ["unknown", "mixed", "unclassified", "other", "none", ""]) {
    const copy = allCopy(fix({ page_template_family: state }));
    assert.doesNotMatch(copy, /unknown|unclassified/i, `${state || "(empty)"} leaked into copy`);
    // Guaranteed by the `family !== "pages"` branch in customerCopyForFix, not
    // by the singulariser; pinned here because it is the customer-visible
    // property, whichever layer keeps it true.
    assert.doesNotMatch(copy, /this pages\b/, "copy must stay grammatical");
    assert.doesNotMatch(copy, /\bmixed pages?\b/i);
  }
});

test("the neutral wording is grammatical and still says what to do", () => {
  const copy = customerCopyForFix(fix({ page_template_family: "unknown" }));
  const text = JSON.stringify(copy);
  assert.match(text, /search description/i, "the instruction must survive the neutral wording");
  assert.match(text, /this page\b/, "expected 'this page', the wording asked for");
});

test("a real page family is still named", () => {
  // Collapsing genuine classification would lose information the customer uses
  // to find the template, so only uninformative states fall back.
  assert.match(allCopy(fix({ page_template_family: "legal_info" })), /legal page/i);
  assert.match(allCopy(fix({ page_template_family: "location_landing" })), /location landing page/i);
  // "homepage" already ends in "page" and must not be mangled.
  assert.doesNotMatch(allCopy(fix({ page_template_family: "homepage" })), /homepag\b/);
});

test("the scanner's owner enum never reaches a card", () => {
  const suggestion = repairSuggestion(fix({ who_can_do_this: "your_web_person" }));
  assert.notEqual(suggestion.role, "your_web_person");
  assert.equal(suggestion.role, "Developer");
  assert.doesNotMatch(JSON.stringify(suggestion), /your_web_person/);
});

test("human role text the scanner publishes still wins over the library", () => {
  // This layer must not overwrite evidence: a real role string is honoured.
  assert.equal(repairSuggestion(fix({ who_can_do_this: "Store manager" })).role, "Store manager");
  assert.equal(repairSuggestion(fix({ who_can_do_this: "web developer" })).role, "Developer");
  assert.equal(repairSuggestion(fix({ who_can_do_this: "you" })).role, "You");
});

test("an unmapped internal token falls back rather than printing itself", () => {
  const suggestion = repairSuggestion(fix({ who_can_do_this: "some_future_bucket" }));
  assert.doesNotMatch(String(suggestion.role || ""), /some_future_bucket/);
  assert.doesNotMatch(String(suggestion.role || ""), /_/, "no snake_case may reach a card");
});

test("every owner value the scanner can emit has a customer-facing form", () => {
  const scanner = fs.readFileSync("scanner-api/app/scanner.py", "utf8");
  const emitted = [...scanner.matchAll(/"who_can_do_this":\s*"([a-z_]+)"/g)].map((m) => m[1]);
  assert.ok(emitted.length > 0, "the scan for emitted owner values is broken");
  for (const value of new Set(emitted)) {
    const role = String(repairSuggestion(fix({ who_can_do_this: value })).role || "");
    assert.notEqual(role, value, `${value} would reach a card verbatim`);
    assert.doesNotMatch(role, /_/, `${value} produced a snake_case role`);
  }
});
