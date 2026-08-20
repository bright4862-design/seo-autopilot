import assert from "node:assert/strict";
import test from "node:test";

import {
  SUPPORTED_RULE_EVALUATION_CONTRACT,
  buildExplicitPassedChecks,
} from "../../src/lib/passedChecksPresentation.js";

function scanWith(evaluations = [], overrides = {}) {
  return {
    rule_evaluation_contract_version: SUPPORTED_RULE_EVALUATION_CONTRACT,
    rule_evaluations: evaluations,
    ...overrides,
  };
}

test("absence of findings or evaluation evidence never becomes a passed claim", () => {
  assert.deepEqual(buildExplicitPassedChecks({ recommendations: [] }), []);
  assert.deepEqual(buildExplicitPassedChecks({ rule_evaluations: [] }), []);
});

test("unsupported evaluation contracts fail closed", () => {
  const claims = buildExplicitPassedChecks(scanWith([
    { rule: "canonical", evaluated: true, applicable: true, passed: true },
  ], {
    rule_evaluation_contract_version: "rule_evaluation_v99_future",
  }));
  assert.deepEqual(claims, []);
});

test("only evaluated applicable passed rules may produce reassurance", () => {
  const claims = buildExplicitPassedChecks(scanWith([
    { rule: "canonical", evaluated: true, applicable: true, passed: true },
  ]));
  assert.deepEqual(claims.map((claim) => claim.key), ["canonicals"]);
  assert.match(claims[0].label, /Canonical settings look right/);
});

test("skipped canonical evaluation cannot say canonical settings look right", () => {
  const claims = buildExplicitPassedChecks(scanWith([
    { rule: "canonical", evaluated: false, applicable: true, passed: true },
  ]));
  assert.deepEqual(claims, []);
});

test("not-applicable evaluation cannot masquerade as a pass", () => {
  const claims = buildExplicitPassedChecks(scanWith([
    { rule: "meta_description", evaluated: true, applicable: false, passed: true },
  ]));
  assert.deepEqual(claims, []);
});

test("explicit failure suppresses reassurance even when another row reports pass", () => {
  const claims = buildExplicitPassedChecks(scanWith([
    { rule: "indexability", evaluated: true, applicable: true, passed: true },
    { rule: "indexability", evaluated: true, applicable: true, passed: false },
  ]));
  assert.deepEqual(claims, []);
});

test("historical alias rules can support one customer claim without inferring missing aliases", () => {
  const claims = buildExplicitPassedChecks(scanWith([
    { rule: "image_alt_text", evaluated: true, applicable: true, passed: true },
  ]));
  assert.deepEqual(claims.map((claim) => claim.key), ["image_descriptions"]);
  assert.deepEqual(claims[0].evidence.evaluated_rules, ["image_alt_text"]);
});
