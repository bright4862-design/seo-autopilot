import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const ramp = readFileSync("scripts/set-standard150-scan-concurrency.sh", "utf8");

test("scan queue ramp is bounded, confirmation-gated, and does not mutate worker configuration", () => {
  assert.match(ramp, /1\|3\|5\|10/);
  assert.match(ramp, /SET-SCAN-CONCURRENCY-\$\{TARGET\}/);
  assert.match(ramp, /containerConcurrency/);
  assert.match(ramp, /must remain 1/);
  assert.match(ramp, /--max-concurrent-dispatches="\$TARGET"/);
  assert.match(ramp, /--max-dispatches-per-second="\$TARGET"/);
  assert.doesNotMatch(ramp, /gcloud run (?:deploy|services update|services replace|revisions)/);
  assert.doesNotMatch(ramp, /update-traffic|--concurrency|--max-instances/);
  assert.doesNotMatch(ramp, /\| python3 -[^\n]*<</);
});
