// Contract for the Cloud Tasks dispatcher.
//
// ScanRun 6a748d5f9e8a27963ae678dc logged async_job_accepted and
// worker_scan_start, then produced nothing for 247s: Base44 reaps work started
// after the response returns, so waitUntil() could never carry a crawl. The
// dispatcher must now do nothing but authenticate, verify, enqueue and answer.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  audienceForWorkerUrl,
  taskNameForScan,
} from "../../base44/functions/startStandardScanJob/cloudTasks.js";

const dispatcher = readFileSync(
  new URL("../../base44/functions/startStandardScanJob/entry.ts", import.meta.url),
  "utf8",
);
const tasks = readFileSync(
  new URL("../../base44/functions/startStandardScanJob/cloudTasks.js", import.meta.url),
  "utf8",
);

test("the dispatcher performs no post-response background work", () => {
  // The exact defect: a crawl handed to waitUntil() is reaped mid-flight.
  assert.doesNotMatch(dispatcher, /waitUntil\(\s*runScanJob/);
  assert.match(dispatcher, /enqueueScanJob\(\{/);
});

test("task identity is derived deterministically from the existing scan_id", () => {
  const queue = "projects/seo-autopilot-501517/locations/europe-west1/queues/standard150-scans";
  const first = taskNameForScan(queue, "6a748d5f9e8a27963ae678dc");
  const second = taskNameForScan(queue, "6a748d5f9e8a27963ae678dc");
  assert.equal(first, second, "the same scan must always map to the same task");
  assert.equal(first, `${queue}/tasks/standard150-6a748d5f9e8a27963ae678dc`);
  assert.notEqual(first, taskNameForScan(queue, "6a744c8220780ec729e20724"));
});

test("task names cannot be injected through the scan id", () => {
  const queue = "projects/p/locations/l/queues/q";
  assert.equal(taskNameForScan(queue, "../../evil"), `${queue}/tasks/standard150-evil`);
  assert.equal(taskNameForScan(queue, "a/b?c=d"), `${queue}/tasks/standard150-abcd`);
});

test("a duplicate submission for one ScanRun is deduplicated, not re-run", () => {
  // Cloud Tasks answers 409 ALREADY_EXISTS for a name it already holds.
  assert.match(tasks, /response\.status === 409/);
  assert.match(tasks, /deduplicated: true/);
  assert.match(tasks, /ok: true, deduplicated: true/);
});

test("the worker route and Cloud Run OIDC audience are kept separate", () => {
  const workerUrl = "https://fixlist-worker-abc-ew.a.run.app/scan-job";
  assert.equal(audienceForWorkerUrl(workerUrl), "https://fixlist-worker-abc-ew.a.run.app");
  assert.match(tasks, /url: workerUrl/);
  assert.match(tasks, /audience: workerAudience/);
  assert.throws(() => audienceForWorkerUrl("http://localhost:8080/scan-job"));
});

test("the worker is invoked with OIDC, never anonymously", () => {
  assert.match(tasks, /oidcToken: \{ serviceAccountEmail: invokerServiceAccount, audience: workerAudience \}/);
});

test("a failed enqueue closes the ScanRun truthfully and charges nothing", () => {
  const branch = dispatcher.match(/if \(!enqueued\.ok\) \{[\s\S]*?\n {4}\}/);
  assert.ok(branch, "the enqueue-failure branch is missing");
  assert.match(branch[0], /failOwnedScanRun\(/);
  assert.match(branch[0], /accepted: false/);
  assert.match(branch[0], /Nothing was charged/);
});

test("missing durable-worker configuration fails closed with no fallback", () => {
  assert.match(dispatcher, /failure_code: "durable_worker_not_configured"/);
  assert.match(dispatcher, /SCAN_TASKS_QUEUE_PATH/);
  assert.match(dispatcher, /SCAN_WORKER_URL/);
  assert.match(dispatcher, /TASKS_INVOKER_SERVICE_ACCOUNT/);
});

test("the dispatcher still refuses anything but Standard 150", () => {
  assert.match(dispatcher, /Only the Standard 150 scan is available/);
  assert.match(dispatcher, /scan_mode: PUBLIC_SCAN_MODE/);
  assert.match(dispatcher, /respect_robots_txt: true/);
});

test("the accepted response records the task for evidence", () => {
  assert.match(dispatcher, /task_name: enqueued\.taskName/);
  assert.match(dispatcher, /deduplicated: enqueued\.deduplicated === true/);
});
