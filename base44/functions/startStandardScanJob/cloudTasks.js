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

async function hmacBytes(secretBytes, payloadText) {
  const key = await crypto.subtle.importKey(
    "raw",
    secretBytes,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  return new Uint8Array(await crypto.subtle.sign(
    "HMAC",
    key,
    new TextEncoder().encode(payloadText),
  ));
}

async function dispatchSignature(rootSecret, timestamp, payloadText) {
  const encoder = new TextEncoder();
  const derivedKey = await hmacBytes(
    encoder.encode(rootSecret),
    "fixlist-dispatch-gateway-v1",
  );
  const signature = await hmacBytes(
    derivedKey,
    `${timestamp}\n${payloadText}`,
  );
  return Array.from(signature, (byte) => byte.toString(16).padStart(2, "0")).join("");
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

async function createTaskViaGateway({ gatewayUrl, signingKey, queuePath, body, taskName, attemptCount }) {
  const payloadText = JSON.stringify({ queue_path: queuePath, task: body?.task || null });
  const timestamp = String(Math.trunc(Date.now() / 1000));
  let signature = "";
  try {
    signature = await dispatchSignature(signingKey, timestamp, payloadText);
  } catch {
    return { ok: false, outcomeUnknown: false, failureCode: "dispatch_gateway_sign_failed" };
  }

  let response;
  try {
    response = await fetch(`${String(gatewayUrl).replace(/\/+$/, "")}/dispatch`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-fixlist-timestamp": timestamp,
        "x-fixlist-signature": signature,
      },
      body: payloadText,
    });
  } catch {
    return { ok: false, outcomeUnknown: true, failureCode: "dispatch_gateway_unreachable" };
  }

  if (response.status === 409) {
    return { ok: true, deduplicated: true, attemptCount, taskName };
  }
  if (!response.ok) {
    let gatewayError = "";
    try {
      const parsed = await response.clone().json();
      const candidate = String(parsed?.error || "").trim();
      const safeGatewayErrors = new Set([
        "invalid_timestamp",
        "stale_request",
        "invalid_signature",
        "request_too_large",
        "invalid_payload",
        "invalid_queue",
        "invalid_task",
        "invalid_task_name",
        "invalid_dispatch_deadline",
        "invalid_http_request",
        "invalid_method",
        "invalid_worker_target",
        "missing_oidc",
        "invalid_invoker",
        "invalid_audience",
        "invalid_task_body",
        "scan_identity_mismatch",
        "missing_drain_schedule",
        "missing_drain_after",
        "unexpected_scan_schedule",
        "invalid_scan_mode",
        "invalid_robots_policy",
        "adc_auth_failed",
        "cloud_tasks_unreachable",
        "cloud_tasks_rejected",
      ]);
      if (safeGatewayErrors.has(candidate)) gatewayError = candidate;
    } catch { /* preserve status-only fallback */ }
    return {
      ok: false,
      outcomeUnknown: response.status >= 500,
      failureCode: gatewayError
        ? `dispatch_gateway_${gatewayError}`
        : `dispatch_gateway_http_${response.status}`,
    };
  }

  let created = {};
  try { created = await response.json(); } catch { /* deterministic task name */ }
  return {
    ok: true,
    deduplicated: created?.deduplicated === true,
    attemptCount,
    taskName: String(created?.taskName || created?.task_name || taskName),
  };
}

async function createTask({ queuePath, body, taskName, attemptCount }) {
  const gatewayUrl = String(Deno.env.get("SCAN_DISPATCH_GATEWAY_URL") || "").trim();
  const signingKey = String(Deno.env.get("SCAN_EVIDENCE_SIGNING_KEY") || "");
  if (gatewayUrl) {
    if (!signingKey) {
      return { ok: false, outcomeUnknown: false, failureCode: "dispatch_gateway_signing_key_missing" };
    }
    return createTaskViaGateway({ gatewayUrl, signingKey, queuePath, body, taskName, attemptCount });
  }

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
