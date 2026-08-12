import { createServiceAccountAccessToken } from "./gcpAuth.js";

const TASKS_API = "https://cloudtasks.googleapis.com/v2";
export const WORKER_DISPATCH_DEADLINE = "480s";
export const DRAIN_DELAY_SECONDS = 900;

export function normalizeAttemptCount(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(1, Math.trunc(parsed)) : 1;
}

function safeScanId(scanId) {
  return String(scanId || "").replace(/[^A-Za-z0-9_-]/g, "");
}

export function taskNameForScan(queuePath, scanId, attemptCount) {
  return `${queuePath}/tasks/standard150-${safeScanId(scanId)}-a${normalizeAttemptCount(attemptCount)}`;
}

export function taskNameForDrain(queuePath, scanId, attemptCount) {
  return `${queuePath}/tasks/standard150-drain-${safeScanId(scanId)}-a${normalizeAttemptCount(attemptCount)}`;
}

export function audienceForWorkerUrl(workerUrl) {
  const parsed = new URL(String(workerUrl || ""));
  if (parsed.protocol !== "https:" || !parsed.hostname) throw new Error("Invalid Cloud Run worker URL.");
  return parsed.origin;
}

export function drainUrlForWorker(workerUrl) {
  const parsed = new URL(String(workerUrl || ""));
  if (parsed.protocol !== "https:" || !parsed.hostname) throw new Error("Invalid Cloud Run worker URL.");
  parsed.pathname = "/scan-job-drain";
  parsed.search = "";
  parsed.hash = "";
  return parsed.href;
}

export function encodeTaskBody(payload) {
  const bytes = new TextEncoder().encode(JSON.stringify(payload));
  let binary = "";
  const chunkSize = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return btoa(binary);
}

function httpTask({ name, url, audience, invokerServiceAccount, payload, scheduleTime }) {
  const task = {
    name,
    dispatchDeadline: WORKER_DISPATCH_DEADLINE,
    httpRequest: {
      url,
      httpMethod: "POST",
      headers: { "content-type": "application/json" },
      body: encodeTaskBody(payload),
      oidcToken: { serviceAccountEmail: invokerServiceAccount, audience },
    },
  };
  if (scheduleTime) task.scheduleTime = scheduleTime;
  return { task };
}

export function buildCloudTaskRequest({ queuePath, workerUrl, invokerServiceAccount, scanId, attemptCount, payload }) {
  const attempt = normalizeAttemptCount(attemptCount);
  return httpTask({
    name: taskNameForScan(queuePath, scanId, attempt),
    url: workerUrl,
    audience: audienceForWorkerUrl(workerUrl),
    invokerServiceAccount,
    payload,
  });
}

export function buildCloudDrainTaskRequest({
  queuePath,
  workerUrl,
  invokerServiceAccount,
  scanId,
  attemptCount,
  payload,
  nowMs = Date.now(),
  delaySeconds = DRAIN_DELAY_SECONDS,
}) {
  const attempt = normalizeAttemptCount(attemptCount);
  return httpTask({
    name: taskNameForDrain(queuePath, scanId, attempt),
    url: drainUrlForWorker(workerUrl),
    audience: audienceForWorkerUrl(workerUrl),
    invokerServiceAccount,
    payload,
    scheduleTime: new Date(nowMs + Math.max(1, Number(delaySeconds) || DRAIN_DELAY_SECONDS) * 1000).toISOString(),
  });
}

async function accessToken() {
  const key = String(Deno.env.get("GCP_SERVICE_ACCOUNT_KEY") || "");
  if (!key) return { token: "", failureCode: "tasks_credentials_not_configured" };
  try {
    const token = await createServiceAccountAccessToken(key);
    if (!token) return { token: "", failureCode: "tasks_token_mint_failed" };
    return { token };
  } catch (error) {
    const safeCode = String(error?.message || "").trim();
    return {
      token: "",
      failureCode: /^tasks_[a-z0-9_]+$/.test(safeCode) ? safeCode : "tasks_token_mint_failed",
    };
  }
}

async function createTask({ queuePath, body, taskName, attemptCount }) {
  const { token, failureCode: tokenFailureCode } = await accessToken();
  if (!token) return { ok: false, outcomeUnknown: false, failureCode: tokenFailureCode };

  let response;
  try {
    response = await fetch(`${TASKS_API}/${queuePath}/tasks`, {
      method: "POST",
      headers: { "content-type": "application/json", authorization: `Bearer ${token}` },
      body: JSON.stringify(body),
    });
  } catch {
    return { ok: false, outcomeUnknown: true, failureCode: "tasks_unreachable" };
  }

  if (response.status === 409) {
    return { ok: true, deduplicated: true, attemptCount, taskName };
  }
  if (!response.ok) {
    return {
      ok: false,
      outcomeUnknown: response.status >= 500,
      failureCode: `tasks_http_${response.status}`,
    };
  }

  let created = {};
  try { created = await response.json(); } catch { /* task name is deterministic */ }
  return {
    ok: true,
    deduplicated: false,
    attemptCount,
    taskName: String(created?.name || taskName),
  };
}

export async function enqueueScanJob(args) {
  const attempt = normalizeAttemptCount(args.attemptCount);
  let body;
  try {
    body = buildCloudTaskRequest({ ...args, attemptCount: attempt });
  } catch {
    return { ok: false, outcomeUnknown: false, failureCode: "invalid_worker_url" };
  }
  return createTask({
    queuePath: args.queuePath,
    body,
    taskName: taskNameForScan(args.queuePath, args.scanId, attempt),
    attemptCount: attempt,
  });
}

export async function enqueueScanDrain(args) {
  const attempt = normalizeAttemptCount(args.attemptCount);
  let body;
  try {
    body = buildCloudDrainTaskRequest({ ...args, attemptCount: attempt });
  } catch {
    return { ok: false, outcomeUnknown: false, failureCode: "invalid_worker_url" };
  }
  return createTask({
    queuePath: args.queuePath,
    body,
    taskName: taskNameForDrain(args.queuePath, args.scanId, attempt),
    attemptCount: attempt,
  });
}
