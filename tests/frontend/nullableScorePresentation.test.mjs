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
  assert.match(scoreRingSource, /\{hasScore \? target : "—"\}/);
});

test("the number is the score, not a number counting up to it", () => {
  // The ring counted from 0 to the score over 900ms, so for most of a second
  // the page showed a number that was not this site's score -- and screen
  // readers were told the real one at the same moment. On a slow render the
  // customer's first sight of their score was a 0 they had to watch climb.
  // The stroke may still animate; the digits may not.
  assert.doesNotMatch(scoreRingSource, /requestAnimationFrame/, "the number is not animated");
  assert.doesNotMatch(scoreRingSource, /setDisplayed/);
  assert.match(scoreRingSource, /strokeDashoffset=\{offset\}/, "the ring stroke still animates");
});

test("the visible number and the label it announces are the same value", () => {
  const label = scoreRingSource.match(/aria-label=\{hasScore \? `Site health score \$\{(\w+)\}`/)?.[1];
  const shown = scoreRingSource.match(/\{hasScore \? (\w+) : "—"\}/)?.[1];
  assert.ok(label && shown, "both the label and the visible value must be readable from source");
  assert.equal(label, shown, `aria-label says ${label} while the page shows ${shown}`);
});

test("the ring holds still when the viewer asked for less motion", () => {
  assert.match(scoreRingSource, /prefers-reduced-motion: reduce/);
  assert.match(scoreRingSource, /transition: reduced \? "none"/);
});
