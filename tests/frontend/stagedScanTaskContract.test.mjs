import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";
import ts from "typescript";
import * as cloudTasks from "../../base44/functions/startStandardScanJobV9/cloudTasks.js";
import { ensureWorkspaceCleanup, workspaceCleanupTask } from "../../base44/functions/deleteCustomerScanDataV9/workspaceCleanup.js";

const entry = new URL("../../base44/functions/startStandardScanJobV9/entry.ts", import.meta.url);
const source = ts.transpileModule(readFileSync(entry, "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const loadHandler = new Function("exports", "require", "Deno", source);
const loadDependency = createRequire(entry);
const owner = { id: "owner_123", email: "owner@example.com" };
const project = { id: "project_123", owner_user_id: owner.id, website_url: "https://example.com/" };
const run = {
  id: "scan_123", attempt_count: 2, status: "queued", request_id: "request_123", project_id: project.id,
  owner_user_id: owner.id, website_url: project.website_url, respect_robots_txt: true, owner_attested_robots_override: false,
};
const standard = { scan_mode: "standard_150", page_cap: 150, pipeline_mode: "staged" };
const large = { scan_mode: "standard_500", page_cap: 500, pipeline_mode: "staged" };
const monolith = { ...standard, pipeline_mode: "monolith" };
const env = {
  SCAN_TASKS_QUEUE_PATH: "projects/test-project/locations/europe-west1/queues/entry",
  SCAN_DRAIN_QUEUE_PATH: "projects/test-project/locations/europe-west1/queues/drain",
  SCAN_WORKER_URL: "https://worker.example/scan-job",
  TASKS_INVOKER_SERVICE_ACCOUNT: "invoker@test-project.iam.gserviceaccount.com",
};

function taskPayload(task) {
  return JSON.parse(Buffer.from(task.httpRequest.body, "base64").toString("utf8"));
}

function contractFields(payload) {
  return Object.fromEntries(Object.keys(standard).filter(key => Object.hasOwn(payload, key)).map(key => [key, payload[key]]));
}

async function dispatch({ stored, request = {} }) {
  const tasks = [];
  const enqueue = builder => async args => {
    tasks.push(builder(args).task);
    return { ok: true };
  };
  const entities = {
    ScanRun: { get: async () => stored, filter: async () => [] },
    BusinessProject: { get: async () => project },
    Access: { filter: async () => [{
      id: "access_123", owner_user_id: owner.id, user_email: owner.email, has_full_access: true, access_status: "active",
      plan_id: "standard150_lifetime", app_id: "6a498732ec779dfaaeab0e53", grant_source: "manual_grant", granted_at: "2026-01-01T00:00:00.000Z",
    }] },
  };
  const dependencies = {
    "npm:@base44/sdk@0.8.31": { createClientFromRequest: () => ({ auth: { me: async () => owner }, asServiceRole: { entities } }) },
    "base44:runtime": { secrets: { get: name => name === "SCAN_EVIDENCE_SIGNING_KEY" ? "local-test-key" : "" } },
    "./cloudTasks.js": {
      ...cloudTasks,
      enqueueScanJob: enqueue(cloudTasks.buildCloudTaskRequest),
      enqueueScanDrain: enqueue(cloudTasks.buildCloudDrainTaskRequest),
    },
  };
  const handler = {};
  loadHandler(handler, name => dependencies[name] || loadDependency(name), { env: { get: name => env[name] } });
  const response = await handler.default(new Request("https://base44.example/startStandardScanJobV9", {
    method: "POST",
    body: JSON.stringify({ scan_id: run.id, request_id: run.request_id, website_url: run.website_url, ...request }),
  }));
  return { status: response.status, body: await response.json(), tasks };
}

function cleanupTask(stored) {
  return workspaceCleanupTask({ run: stored, queuePath: env.SCAN_DRAIN_QUEUE_PATH, workerUrl: env.SCAN_WORKER_URL,
    invokerServiceAccount: env.TASKS_INVOKER_SERVICE_ACCOUNT }).task;
}

test("V9 sends the same frozen contract to the watchdog and entry for each supported scan", async () => {
  for (const contract of [monolith, standard, large]) {
    const { status, body, tasks } = await dispatch({ stored: { ...run, ...contract }, request: { page_cap: 42, pipeline_mode: "external" } });
    assert.equal(status, 200, JSON.stringify(body));
    assert.equal(tasks.length, 2);
    const [watchdog, entryTask] = tasks;
    assert.equal(watchdog.name, `${env.SCAN_DRAIN_QUEUE_PATH}/tasks/standard150-drain-${run.id}-a2`);
    assert.equal(watchdog.httpRequest.url, "https://worker.example/scan-job-drain");
    assert.equal(watchdog.httpRequest.oidcToken.audience, "https://worker.example");
    assert.deepEqual(contractFields(taskPayload(entryTask)), contract);
    assert.deepEqual(contractFields(taskPayload(watchdog)), contract);
  }
});

test("staged cleanup carries the saved cap while old task bodies retain their historical shape", async () => {
  for (const contract of [standard, large]) {
    const task = cleanupTask({ ...run, ...contract });
    assert.equal(task.name, `${env.SCAN_DRAIN_QUEUE_PATH}/tasks/standard150-cleanup-${run.id}-a2`);
    assert.equal(task.httpRequest.url, "https://worker.example/scan-workspace-delete");
    assert.equal(task.httpRequest.oidcToken.audience, "https://worker.example");
    assert.equal(taskPayload(task).workspace_cleanup, true);
    assert.deepEqual(contractFields(taskPayload(task)), contract);
  }
  for (const absentCap of [{}, { page_cap: null }]) {
    const legacy = { ...run, scan_mode: "standard_150", pipeline_mode: "staged", ...absentCap };
    assert.deepEqual(contractFields(taskPayload(cleanupTask(legacy))), {});
    const { status, body, tasks } = await dispatch({ stored: legacy });
    assert.equal(status, 200, JSON.stringify(body));
    assert.deepEqual(contractFields(taskPayload(tasks[0])), {});
    assert.deepEqual(contractFields(taskPayload(tasks[1])), standard);
  }
});

test("malformed V9 rows cannot queue a partial contract or skip workspace cleanup", async () => {
  const malformed = [
    { ...large, page_cap: null }, { ...large, page_cap: "500" }, { ...large, pipeline_mode: undefined },
    { ...large, pipeline_mode: "monolith" }, { ...standard, scan_mode: undefined }, { ...standard, page_cap: 500 },
  ];
  for (const contract of malformed) {
    const stored = { ...run, ...contract };
    const { status, tasks } = await dispatch({ stored });
    assert.notEqual(status, 200);
    assert.deepEqual(tasks, []);
    await assert.rejects(() => ensureWorkspaceCleanup(stored, { env: name => env[name] }), /scan_page_cap_invalid/);
  }
});
