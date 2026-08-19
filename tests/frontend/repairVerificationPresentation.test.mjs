import assert from "node:assert/strict";
import test from "node:test";

import {
  repairRowModel,
  repairVerificationKind,
  repairVerificationLabel,
} from "../../src/lib/repairPresentation.js";


test("ready-to-verify state asks for a rescan instead of sounding verified", () => {
  const item = { repair_verification_state: "ready_to_verify" };
  assert.equal(repairVerificationLabel(item), "Ready to verify with a rescan");
  assert.equal(repairVerificationKind(item), "pending");
  assert.notEqual(repairVerificationLabel(item), "Verified fixed");
});


test("verified fixed is reserved for the explicit verified state", () => {
  const item = { repair_verification_state: "verified_fixed" };
  const model = repairRowModel(item);
  assert.equal(model.verification, "Verified fixed");
  assert.equal(model.verificationKind, "verified");
});


test("incomparable historical evidence fails closed to Could not compare", () => {
  const item = {
    repair_verification_state: "could_not_verify",
    comparison_contract_state: "incomparable",
  };
  const model = repairRowModel(item);
  assert.equal(model.verification, "Could not compare");
  assert.equal(model.verificationKind, "uncertain");
});


test("still detected and came back remain detection states, not workflow completion", () => {
  assert.equal(repairVerificationKind({ repair_verification_state: "still_detected" }), "detected");
  assert.equal(repairVerificationKind({ repair_verification_state: "came_back" }), "detected");
});
