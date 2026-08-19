import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { repairWorkflowCompletionPresentation } from "../../src/lib/repairWorkflowPresentation.js";

test("all repairs marked done is pending verification, not all clear", () => {
  const model = repairWorkflowCompletionPresentation({
    snapshotCount: 4,
    remainingCount: 0,
    markedDoneCount: 4,
  });

  assert.equal(model.state, "marked_done_pending_verification");
  assert.equal(model.verified, false);
  assert.equal(model.title, "Changes marked done");
  assert.match(model.detail, /later comparable scan/i);
  assert.doesNotMatch(`${model.title} ${model.detail}`, /all clear|verified fixed|everything is fixed/i);
});

test("empty visible list alone cannot claim workflow completion", () => {
  assert.equal(repairWorkflowCompletionPresentation({
    snapshotCount: 4,
    remainingCount: 0,
    markedDoneCount: 2,
  }), null);
});

test("zero-repair scans use the separate zero-repair evidence contract", () => {
  assert.equal(repairWorkflowCompletionPresentation({
    snapshotCount: 0,
    remainingCount: 0,
    markedDoneCount: 0,
  }), null);
});

test("workflow completion component is presentation-only", () => {
  const source = fs.readFileSync(
    new URL("../../src/components/fixlist/RepairWorkflowCompleteState.jsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /repairWorkflowCompletionPresentation/);
  assert.doesNotMatch(source, /fetch\(/);
  assert.doesNotMatch(source, /base44/);
  assert.doesNotMatch(source, /markDone|update\(/);
});
