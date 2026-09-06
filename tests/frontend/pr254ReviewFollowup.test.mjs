import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

import { healthScoreExplanation } from "../../src/lib/healthScoreExplanation.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "../..");

function extractScoreExplanation(path) {
  const source = readFileSync(resolve(ROOT, path), "utf8");
  const marker = "function scoreExplanation(value) {";
  const start = source.indexOf(marker);
  assert.notEqual(start, -1, `${path} must contain scoreExplanation()`);

  let depth = 0;
  let opened = false;
  for (let index = start; index < source.length; index += 1) {
    const char = source[index];
    if (char === "{") {
      depth += 1;
      opened = true;
    } else if (char === "}") {
      depth -= 1;
      if (opened && depth === 0) return source.slice(start, index + 1);
    }
  }
  assert.fail(`${path} has an unterminated scoreExplanation()`);
}

test("a current row with an intentionally empty score explanation is unavailable, not legacy", () => {
  assert.deepEqual(
    healthScoreExplanation({ health_score: 82, health_score_explanation: {} }),
    {
      available: false,
      legacy: false,
      legacyNote: "",
      finalScore: null,
      totalDeduction: 0,
      deductions: [],
      remainingDeduction: 0,
      ceilingNote: "",
      floorNote: "",
      verificationExcluded: false,
    },
  );
});

test("all five v5 scoreExplanation seal and projection copies stay byte-identical", () => {
  const copies = [
    "base44/functions/persistDurableScanAuthorityV2/authoritySnapshot.js",
    "base44/functions/getCustomerScanResultV2/projection.js",
    "base44/functions/grokChat/authoritySnapshot.js",
    "base44/functions/persistDurableScanAuthority/authoritySnapshot.js",
    "base44/functions/getCustomerScanResult/projection.js",
  ].map(extractScoreExplanation);

  for (const copy of copies.slice(1)) assert.equal(copy, copies[0]);
});
