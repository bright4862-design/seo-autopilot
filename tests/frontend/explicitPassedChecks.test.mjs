import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  SUPPORTED_RULE_EVALUATION_CONTRACT,
  buildExplicitPassedChecks,
} from "../../src/lib/passedChecksPresentation.js";

const componentSource = readFileSync(
  new URL("../../src/components/fixlist/ExplicitPassedChecks.jsx", import.meta.url),
  "utf8",
);

test("passed-check component is driven by explicit evaluation contract, not repair collection logic", () => {
  assert.match(componentSource, /buildExplicitPassedChecks/);
  assert.match(componentSource, /if \(claims\.length === 0\) return null/);
  assert.match(componentSource, /Checks that passed/);
  assert.match(componentSource, /Explicitly evaluated in this scan/);
  assert.doesNotMatch(componentSource, /recommendations\.filter/);
  assert.doesNotMatch(componentSource, /priorityBucket/);
});

test("current scan shapes without evaluation ledger produce no passed-check claims", () => {
  const claims = buildExplicitPassedChecks({
    recommendations: [],
    pages_crawled: 150,
  });
  assert.deepEqual(claims, []);
});

test("explicit evaluated applicable pass produces one qualified claim", () => {
  const claims = buildExplicitPassedChecks({
    rule_evaluation_contract_version: SUPPORTED_RULE_EVALUATION_CONTRACT,
    rule_evaluations: [
      {
        rule: "canonical",
        evaluated: true,
        applicable: true,
        passed: true,
      },
    ],
  });

  assert.equal(claims.length, 1);
  assert.equal(claims[0].key, "canonicals");
  assert.match(claims[0].label, /pages we checked/);
});
