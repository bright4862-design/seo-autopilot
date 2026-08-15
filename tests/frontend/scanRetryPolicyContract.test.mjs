import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const policy = readFileSync("scripts/set-standard150-retry-policy.sh", "utf8");

test("Standard 150 retry policy is fixed, confirmation-gated, and queue-only", () => {
  assert.match(policy, /SET-SCAN-RETRY-SAFE-BETA/);
  assert.match(policy, /MAX_ATTEMPTS=3/);
  assert.match(policy, /MIN_BACKOFF="10s"/);
  assert.match(policy, /MAX_BACKOFF="300s"/);
  assert.match(policy, /MAX_DOUBLINGS=3/);
  assert.match(policy, /gcloud tasks queues update/);
  assert.match(policy, /--max-attempts="\$MAX_ATTEMPTS"/);
  assert.match(policy, /--min-backoff="\$MIN_BACKOFF"/);
  assert.doesNotMatch(policy, /gcloud run|update-traffic|functions deploy|secrets set|iam-policy-binding/);
});
