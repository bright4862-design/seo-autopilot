import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { repairSuggestion } from "../../src/lib/repairSuggestions.js";

const suggestedFixSource = fs.readFileSync(
  new URL("../../src/components/fixlist/SuggestedFix.jsx", import.meta.url),
  "utf8",
);
const fixListSource = fs.readFileSync(new URL("../../src/pages/FixList.jsx", import.meta.url), "utf8");
const presentationSource = fs.readFileSync(
  new URL("../../src/lib/repairPresentation.js", import.meta.url),
  "utf8",
);

test("the repair card renders suggested fix, best approach, effort, and who should fix it", () => {
  assert.match(suggestedFixSource, /Suggested fix/);
  assert.match(suggestedFixSource, /\{suggestion\.suggestedFix\}/);
  assert.match(suggestedFixSource, /Best approach/);
  assert.match(suggestedFixSource, /\{suggestion\.bestApproach\}/);
  assert.match(suggestedFixSource, /suggestion\.fixStrategyLabel/);
  assert.match(suggestedFixSource, /Effort · \$\{suggestion\.effortLabel\}/);
  assert.match(suggestedFixSource, /Usually done by · \$\{suggestion\.recommendedRole\}/);
});

test("suggestion copy lives in the library, never inside a React component", () => {
  const librarySentences = [
    "Add unique search descriptions",
    "Replace redirected internal links",
    "Fix the shared template once",
    "Review this repair manually",
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
  assert.match(suggestedFixSource, /suggestion\.effortLabel \?/);
  assert.match(suggestedFixSource, /suggestion\.recommendedRole \?/);
  assert.match(suggestedFixSource, /suggestion\.bestApproach \?/);
  assert.match(suggestedFixSource, /\.filter\(Boolean\)/);
});

test("FixList renders the suggested fix for canonical and legacy repairs alike", () => {
  assert.match(fixListSource, /import SuggestedFix from "@\/components\/fixlist\/SuggestedFix"/);
  assert.match(fixListSource, /import \{ repairSuggestion \} from "@\/lib\/repairSuggestions"/);
  assert.match(fixListSource, /suppliedSuggestion \|\| repairSuggestion\(item\)/);
  assert.match(fixListSource, /<SuggestedFix\n\s+suggestion=\{suggestion\}/);
  assert.match(fixListSource, /renderRow=\{\(\{ item, model, suggestion \}\) => \(/);
});

test("the presentation seam attaches suggestions without touching persisted repair authority", () => {
  assert.match(presentationSource, /import \{ buildRepairGroupSummaries, repairSuggestion \} from "\.\/repairSuggestions\.js"/);
  assert.match(presentationSource, /return \{ item, model: repairRowModel\(item\), suggestion: repairSuggestion\(item\) \};/);
  // The suggestion is an extra field on the row, never a rewrite of the model.
  assert.doesNotMatch(presentationSource, /model\.title = /);
  assert.doesNotMatch(presentationSource, /model\.reason = /);
  assert.doesNotMatch(presentationSource, /actionPriority: repairSuggestion/);
});

test("the enrichment layer never reaches the scanner, the network, or persistence", () => {
  const layerFiles = [
    "../../src/lib/repairSuggestions.js",
    "../../src/lib/grokRepairBrief.js",
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
