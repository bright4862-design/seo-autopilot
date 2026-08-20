import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { zeroRepairPresentation } from "../../src/lib/zeroRepairPresentation.js";

function authoritativeScan(overrides = {}) {
  return {
    status: "complete",
    release_gate_eligible: true,
    is_authoritative: true,
    score_is_provisional: false,
    evidence_quality_blocking: false,
    ...overrides,
  };
}

test("empty repair array alone never becomes a positive audit claim", () => {
  const model = zeroRepairPresentation(authoritativeScan(), 0);
  assert.equal(model.state, "empty_without_pass_evidence");
  assert.equal(model.positiveClaimAllowed, false);
  assert.match(model.detail, /does not treat an empty repair list as proof/i);
});

test("explicit authoritative no-findings evidence permits sample-qualified copy", () => {
  const model = zeroRepairPresentation(authoritativeScan({
    no_high_confidence_findings: true,
  }), 0);

  assert.equal(model.state, "explicit_no_high_confidence_findings");
  assert.equal(model.positiveClaimAllowed, true);
  assert.match(model.title, /pages checked/i);
  assert.doesNotMatch(model.title, /site is clean|all checks passed|perfect/i);
});

test("review confidence state is accepted only on an authoritative completed result", () => {
  const explicit = zeroRepairPresentation(authoritativeScan({
    review_confidence_state: "no_high_confidence_findings",
  }), 0);
  assert.equal(explicit.positiveClaimAllowed, true);

  const incomplete = zeroRepairPresentation({
    status: "reviewing",
    review_confidence_state: "no_high_confidence_findings",
    release_gate_eligible: false,
    is_authoritative: false,
  }, 0);
  assert.equal(incomplete.positiveClaimAllowed, false);
});

test("provisional or evidence-blocked results cannot make positive zero-repair claims", () => {
  assert.equal(zeroRepairPresentation(authoritativeScan({
    no_high_confidence_findings: true,
    score_is_provisional: true,
  }), 0).positiveClaimAllowed, false);

  assert.equal(zeroRepairPresentation(authoritativeScan({
    no_high_confidence_findings: true,
    evidence_quality_blocking: true,
  }), 0).positiveClaimAllowed, false);
});

test("component is presentation-only and consumes the shared zero-repair model", () => {
  const source = fs.readFileSync(
    new URL("../../src/components/fixlist/ZeroRepairState.jsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /zeroRepairPresentation/);
  assert.doesNotMatch(source, /fetch\(/);
  assert.doesNotMatch(source, /base44/);
  assert.doesNotMatch(source, /recommendations\.length === 0/);
});
