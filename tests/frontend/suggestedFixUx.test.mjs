import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { repairSuggestion } from "../../src/lib/repairSuggestions.js";
import { sectionCustomerRepairs } from "../../src/lib/repairPresentation.js";

const suggestedFixSource = fs.readFileSync(
  new URL("../../src/components/fixlist/SuggestedFix.jsx", import.meta.url),
  "utf8",
);
const fixListSource = fs.readFileSync(new URL("../../src/pages/FixList.jsx", import.meta.url), "utf8");
const presentationSource = fs.readFileSync(
  new URL("../../src/lib/repairPresentation.js", import.meta.url),
  "utf8",
);
const rowSource = fs.readFileSync(
  new URL("../../src/components/fixlist/CanonicalRepairRow.jsx", import.meta.url),
  "utf8",
);
const sectionListSource = fs.readFileSync(
  new URL("../../src/components/fixlist/RepairSectionList.jsx", import.meta.url),
  "utf8",
);

test("the repair card renders suggested fix, best approach, effort, and who should fix it", () => {
  assert.match(suggestedFixSource, /Suggested fix/);
  assert.match(suggestedFixSource, /\{suggestion\.suggestedFix\}/);
  assert.match(suggestedFixSource, /label: "Fix scope", value: suggestion\.fixScopeLabel/);
  assert.match(suggestedFixSource, /label: "Effort", value: suggestion\.effortDisplay/);
  assert.match(suggestedFixSource, /label: "Who should fix", value: suggestion\.role/);
  assert.match(suggestedFixSource, /\{suggestion\.bestApproach\}/);
});

test("suggestion copy lives in the library, never inside a React component", () => {
  const librarySentences = [
    "Add unique search descriptions",
    "Replace redirected internal links",
    "Update the page template to generate unique meta descriptions",
    "Review this issue based on the evidence collected",
  ];
  for (const sentence of librarySentences) {
    assert.ok(
      !suggestedFixSource.includes(sentence),
      `SuggestedFix.jsx hardcodes library copy: ${sentence}`,
    );
    assert.ok(
      !fixListSource.includes(sentence),
      `FixList.jsx hardcodes library copy: ${sentence}`,
    );
  }
  // No rule name may drive suggestion copy from inside the component.
  assert.doesNotMatch(suggestedFixSource, /missing_meta_description|redirect_chain|canonical/);
});

test("an unrecognized repair renders its fallback and is labeled as needing manual review", () => {
  assert.match(suggestedFixSource, /suggestion\.suggestionAvailable \? null : \(/);
  assert.match(suggestedFixSource, /Needs manual review/);

  const suggestion = repairSuggestion({ rule: "unmapped_future_rule" });
  assert.equal(suggestion.suggestionAvailable, false);
  assert.ok(suggestion.suggestedFix.length > 0);
});

test("optional fields are omitted rather than rendered empty", () => {
  assert.match(suggestedFixSource, /\.filter\(\(fact\) => Boolean\(fact\.value\)\)/);
  assert.match(suggestedFixSource, /facts\.length > 0 \?/);
  assert.match(suggestedFixSource, /suggestion\.bestApproach \?/);
});

test("FixList renders the suggested fix for canonical and legacy repairs alike", () => {
  assert.match(fixListSource, /import SuggestedFix from "@\/components\/fixlist\/SuggestedFix"/);
  assert.match(fixListSource, /import \{ repairSuggestion \} from "@\/lib\/repairSuggestions"/);
  assert.match(fixListSource, /suppliedSuggestion \|\| repairSuggestion\(item\)/);
  assert.match(fixListSource, /<SuggestedFix suggestion=\{suggestion\} \/>/);
  assert.match(fixListSource, /renderRow=\{\(\{ item, suggestion \}\) => \(/);
});

test("FixList works with no Grok dependency at all", () => {
  // Grok is deferred: the repair experience must be complete without it, and
  // nothing in the enrichment layer may import or call it.
  const shippingFiles = [
    "../../src/pages/FixList.jsx",
    "../../src/lib/repairSuggestions.js",
    "../../src/lib/repairPresentation.js",
    "../../src/components/fixlist/SuggestedFix.jsx",
    "../../src/components/fixlist/RepairGroupSummary.jsx",
    "../../src/components/fixlist/RepairSectionList.jsx",
  ];

  for (const file of shippingFiles) {
    const source = fs.readFileSync(new URL(file, import.meta.url), "utf8");
    assert.doesNotMatch(source, /grok/i, `${file} must not depend on Grok before launch`);
  }
});

test("the repair card answers what to do without any assistant involved", () => {
  const suggestion = repairSuggestion({
    rule: "internal_link_redirect",
    page_count: 1,
    affected_pages: ["/"],
  });

  assert.ok(suggestion.suggestedFix.length > 0, "what should I do?");
  assert.equal(suggestion.fixScopeLabel, "Sitewide", "page fix or template fix?");
  assert.equal(suggestion.effortLabel, "Low", "how much effort?");
  assert.ok(suggestion.role.length > 0, "who should fix it?");
});

test("the presentation seam attaches suggestions without touching persisted repair authority", () => {
  assert.match(presentationSource, /import \{ buildRepairGroupSummaries, repairSuggestion \} from "\.\/repairSuggestions\.js"/);
  assert.match(presentationSource, /return \{ item, model: repairRowModel\(item\), suggestion: repairSuggestion\(item\) \};/);
  // The suggestion is an extra field on the row, never a rewrite of the model.
  assert.doesNotMatch(presentationSource, /model\.title = /);
  assert.doesNotMatch(presentationSource, /model\.reason = /);
  assert.doesNotMatch(presentationSource, /actionPriority: repairSuggestion/);
});

test("a collapsed repair row answers what to do, at what scope, for what effort", () => {
  // The customer must not have to open a disclosure to learn the action. Only
  // evidence lives one level down.
  assert.match(rowSource, /<SuggestedFix suggestion=\{suggestion\} compact showFix=\{showSuggestedFix\} \/>/);
  assert.match(suggestedFixSource, /if \(compact\) \{/);
  assert.match(suggestedFixSource, /Suggested fix · /);
  assert.match(suggestedFixSource, /facts\.map\(\(fact\) => `\$\{fact\.label\}: \$\{fact\.value\}`\)\.join\(" · "\)/);
});

test("the mobile card keeps title, impact, why, suggested fix, scope, then evidence in that order", () => {
  const order = [
    "model.title",
    "{supporting}",
    "Why this is here",
    "<SuggestedFix",
    "model.verification",
    "Evidence & steps",
  ].map((needle) => rowSource.indexOf(needle));

  assert.ok(order.every((index) => index >= 0), "every card region must be present");
  for (let index = 1; index < order.length; index += 1) {
    assert.ok(order[index] > order[index - 1], `card region ${index} is out of order`);
  }
});

test("a grouped row does not repeat the shared fix its group summary already states", () => {
  assert.match(presentationSource, /groupedUnderSummary: groupedIds\.has\(row\.model\.id\)/);
  assert.match(sectionListSource, /showSuggestedFix=\{!row\.groupedUnderSummary\}/);

  const shared = ["activity_detail", "collection_page"].map((family, index) => ({
    id: `g${index}`,
    rule: "missing_meta_description",
    action_priority: "important",
    page_template_family: family,
    shared_repair_confirmed: true,
    affected_pages: [`/${family}/a`, `/${family}/b`],
    page_count: 2,
  }));
  const [section] = sectionCustomerRepairs(shared);

  assert.equal(section.groups.length, 1);
  assert.ok(section.rows.every((row) => row.groupedUnderSummary === true));
  // Suppression is presentational only: the suggestion itself is still attached.
  assert.ok(section.rows.every((row) => row.suggestion.suggestedFix.length > 0));
});

test("an ungrouped row always states its own suggested fix", () => {
  const [section] = sectionCustomerRepairs([{
    id: "solo",
    rule: "redirect_chain",
    action_priority: "fix_first",
    affected_pages: ["/"],
    page_count: 1,
  }]);

  assert.equal(section.groups.length, 0);
  assert.equal(section.rows[0].groupedUnderSummary, false);
});

test("the enrichment layer never reaches the scanner, the network, or persistence", () => {
  const layerFiles = [
    "../../src/lib/repairSuggestions.js",
    "../../src/components/fixlist/SuggestedFix.jsx",
    "../../src/components/fixlist/RepairGroupSummary.jsx",
  ];

  for (const file of layerFiles) {
    const source = fs.readFileSync(new URL(file, import.meta.url), "utf8");
    for (const forbidden of [/fetch\(/, /base44/, /ScanRun/, /functions\.invoke/, /entities\./]) {
      assert.doesNotMatch(source, forbidden, `${file} must stay a presentation layer`);
    }
  }
});
