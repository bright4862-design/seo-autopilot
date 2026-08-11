import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  audienceForWorkerUrl,
  buildCloudDrainTaskRequest,
  buildCloudTaskRequest,
  drainUrlForWorker,
  encodeTaskBody,
  taskNameForDrain,
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

const QUEUE = "projects/seo-autopilot-501517/locations/europe-west1/queues/standard150-scans";
const WORKER = "https://fixlist-standard150-worker-abc-ew.a.run.app/scan-job";
const INVOKER = "fixlist-scan-invoker@seo-autopilot-501517.iam.gserviceaccount.com";

test("the Base44 dispatcher contains no crawl or post-response worker", () => {
  assert.doesNotMatch(dispatcher, /waitUntil|runScanJob|fetchScannerResult/);
  assert.doesNotMatch(dispatcher, /SCANNER_API_URL|SCANNER_API_KEY|SCAN_EVIDENCE_SIGNING_KEY/);
  assert.match(dispatcher, /enqueueScanDrain\(\{/);
  assert.match(dispatcher, /enqueueScanJob\(\{/);
});

test("paid admission is server-side and precedes every enqueue", () => {
  assert.match(dispatcher, /loadPaidEntitlement\(base44, user\)/);
  assert.match(dispatcher, /paid_access_required/);
  assert.match(dispatcher, /paid_access_conflict/);
  assert.ok(dispatcher.indexOf("loadPaidEntitlement(base44, user)") < dispatcher.indexOf("enqueueScanDrain({"));
  assert.ok(dispatcher.indexOf("loadPaidEntitlement(base44, user)") < dispatcher.indexOf("enqueueScanJob({"));
});

test("task identity is deterministic per scan and attempt", () => {
  assert.equal(taskNameForScan(QUEUE, "scan-1", 1), `${QUEUE}/tasks/standard150-scan-1-a1`);
  assert.equal(taskNameForScan(QUEUE, "scan-1", 2), `${QUEUE}/tasks/standard150-scan-1-a2`);
  assert.equal(taskNameForDrain(QUEUE, "scan-1", 2), `${QUEUE}/tasks/standard150-drain-scan-1-a2`);
  assert.equal(taskNameForScan(QUEUE, "../../evil", 1), `${QUEUE}/tasks/standard150-evil-a1`);
});

test("Cloud Task bodies preserve Unicode", () => {
  const payload = { business_name: "Café Noël 東京", website_url: "https://example.com/équipe" };
  const decoded = JSON.parse(Buffer.from(encodeTaskBody(payload), "base64").toString("utf8"));
  assert.deepEqual(decoded, payload);
});

test("worker tasks use OIDC and the 480 second request envelope", () => {
  const request = buildCloudTaskRequest({
    queuePath: QUEUE,
    workerUrl: WORKER,
    invokerServiceAccount: INVOKER,
    scanId: "scan-1",
    attemptCount: 2,
    payload: { scan_id: "scan-1", attempt_count: 2 },
  });
  assert.equal(request.task.dispatchDeadline, "480s");
  assert.equal(request.task.httpRequest.url, WORKER);
  assert.equal(request.task.httpRequest.oidcToken.audience, audienceForWorkerUrl(WORKER));
  assert.equal(request.task.httpRequest.oidcToken.serviceAccountEmail, INVOKER);
});

test("the terminal drain is delayed, private and attempt-bound", () => {
  const now = Date.parse("2026-08-11T12:00:00.000Z");
  const request = buildCloudDrainTaskRequest({
    queuePath: QUEUE,
    workerUrl: WORKER,
    invokerServiceAccount: INVOKER,
    scanId: "scan-1",
    attemptCount: 2,
    payload: { scan_id: "scan-1", attempt_count: 2 },
    nowMs: now,
    delaySeconds: 900,
  });
  assert.equal(request.task.scheduleTime, "2026-08-11T12:15:00.000Z");
  assert.equal(request.task.httpRequest.url, drainUrlForWorker(WORKER));
  assert.equal(request.task.httpRequest.url, "https://fixlist-standard150-worker-abc-ew.a.run.app/scan-job-drain");
  assert.equal(request.task.httpRequest.oidcToken.audience, "https://fixlist-standard150-worker-abc-ew.a.run.app");
  assert.equal(request.task.name, `${QUEUE}/tasks/standard150-drain-scan-1-a2`);
});

test("same-attempt duplicate tasks are accepted idempotently", () => {
  assert.match(tasks, /response\.status === 409/);
  assert.match(tasks, /deduplicated: true/);
});

test("ambiguous immediate enqueue failures stay server-owned", () => {
  assert.match(tasks, /outcomeUnknown: true, failureCode: "tasks_unreachable"/);
  assert.match(tasks, /outcomeUnknown: response\.status >= 500/);
  assert.match(dispatcher, /enqueued\.outcomeUnknown !== true/);
  assert.match(dispatcher, /dispatch_uncertain: dispatchUncertain/);
});

test("definite failures terminalize the exact attempt", () => {
  assert.match(dispatcher, /normalizeAttemptCount\(current\.attempt_count\) !== normalizeAttemptCount\(attemptCount\)/);
  assert.match(dispatcher, /TERMINAL_SCAN_STATUSES\.has/);
  assert.match(dispatcher, /status: "failed"/);
  assert.match(dispatcher, /release_gate_eligible: false/);
});

test("missing durable configuration fails closed after admission", () => {
  assert.match(dispatcher, /failure_code: "durable_worker_not_configured"/);
  assert.match(dispatcher, /SCAN_TASKS_QUEUE_PATH/);
  assert.match(dispatcher, /SCAN_WORKER_URL/);
  assert.match(dispatcher, /TASKS_INVOKER_SERVICE_ACCOUNT/);
  assert.match(dispatcher, /failOwnedScanRun\(\{/);
});

test("the public route remains Standard 150 only", () => {
  assert.match(dispatcher, /Only the Standard 150 scan is available/);
  assert.match(dispatcher, /scan_mode: PUBLIC_SCAN_MODE/);
  assert.match(dispatcher, /respect_robots_txt: true/);
  assert.doesNotMatch(dispatcher, /grok|premium/i);
});
