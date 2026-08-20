import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(
  new URL("../../src/components/fixlist/ScanHistoryLineageBadge.jsx", import.meta.url),
  "utf8",
);

test("history badge consumes only the explicit lineage presentation contract", () => {
  assert.match(source, /scanHistoryLineagePresentation/);
  assert.match(source, /\{model\.label\}/);
});

test("history badge is presentation-only and contains no trend language", () => {
  assert.doesNotMatch(source, /fetch\(/);
  assert.doesNotMatch(source, /base44/);
  assert.doesNotMatch(source, /health_score|total_fixes|improved|worsened|fixed|better|worse/i);
});
