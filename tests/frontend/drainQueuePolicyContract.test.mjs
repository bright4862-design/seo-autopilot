import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const policy = readFileSync("scripts/set-standard150-drain-policy.sh", "utf8");
const preflight = readFileSync("scripts/deployment_preflight.sh", "utf8");
const postDeploy = readFileSync("scripts/post_deploy_verify.sh", "utf8");

test("drain queue has an independent bounded retry envelope", () => {
  assert.match(policy, /CLOUD_TASKS_DRAIN_QUEUE:-fixlist-standard150-drain/);
  assert.match(policy, /SET-DRAIN-QUEUE-SAFE-BETA/);
  assert.match(policy, /MAX_CONCURRENT=5/);
  assert.match(policy, /MAX_RATE=5/);
  assert.match(policy, /MAX_ATTEMPTS=100/);
  assert.match(policy, /MAX_RETRY_DURATION="14400s"/);
  assert.match(policy, /MIN_BACKOFF="30s"/);
  assert.match(policy, /MAX_BACKOFF="180s"/);
  assert.match(policy, /MAX_DOUBLINGS=3/);
  assert.doesNotMatch(policy, /gcloud run|update-traffic|base44/);
  assert.doesNotMatch(policy, /\| python3 -[^\n]*<</);
});

test("release verification pins both live Cloud Tasks queues", () => {
  assert.match(preflight, /Queue policy source contract/);
  assert.match(preflight, /scan retry min backoff 10s/);
  assert.match(preflight, /drain retry duration 14400s/);
  assert.match(postDeploy, /EXPECTED_SCAN_QUEUE_CONCURRENCY/);
  assert.match(postDeploy, /scan queue matches beta concurrency\/retry contract/);
  assert.match(postDeploy, /drain queue matches independent watchdog contract/);
  assert.match(postDeploy, /maxConcurrentDispatches/);
  assert.match(postDeploy, /maxRetryDuration/);
});
