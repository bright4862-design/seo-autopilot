import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const fixListSource = await readFile(new URL("../../src/pages/FixList.jsx", import.meta.url), "utf8");
const scoreRingSource = await readFile(new URL("../../src/components/fixlist/ScoreRing.jsx", import.meta.url), "utf8");

test("insufficient evidence never becomes a zero score in the FixList UI", () => {
  assert.match(fixListSource, /const scoreUnavailable = isHealthScoreUnavailable\(scanRecord\)/);
  assert.match(fixListSource, /<ScoreRing score=\{healthScore\} unavailable=\{scoreUnavailable\} \/>/);
  assert.match(fixListSource, /<ExplicitPassedChecks scan=\{scanRecord\} \/>/);
  assert.doesNotMatch(fixListSource, /buildPassedChecks\(/);
  assert.match(fixListSource, /customerHealthLabel\(healthScore, \{ unavailable: scoreUnavailable, noHighConfidenceFindings \}\)/);
  assert.match(fixListSource, /if \(isHealthScoreUnavailable\(record\)\) return null/);
  assert.doesNotMatch(fixListSource, /Number\(record\?\.health_score \|\|/);
});

test("score ring renders an explicit unavailable state", () => {
  assert.match(scoreRingSource, /unavailable = false/);
  assert.match(scoreRingSource, /const hasScore = !unavailable/);
  assert.match(scoreRingSource, /Site health score unavailable/);
  assert.match(scoreRingSource, /\{hasScore \? displayed : "—"\}/);
});
