import { createServiceAccountAccessToken } from "./gcpAuth.js";

export function workspaceCleanupTask({run, queuePath, workerUrl, invokerServiceAccount}) {
  if (!/^projects\/[a-z0-9-]+\/locations\/[a-z0-9-]+\/queues\/[A-Za-z0-9_-]+$/.test(String(queuePath || ""))) throw new Error("workspace_cleanup_not_configured");
  const target = new URL(workerUrl);
  if (target.protocol !== "https:" || target.username || target.password || target.search || target.hash) throw new Error("workspace_cleanup_not_configured");
  target.pathname = "/scan-workspace-delete";
  const scanId = String(run?.id || "");
  const attempt = Number(run?.attempt_count || 1);
  if (!/^[A-Za-z0-9_-]{6,128}$/.test(scanId) || !Number.isInteger(attempt) || attempt < 1 || !invokerServiceAccount) throw new Error("workspace_cleanup_not_configured");
  const payload = {scan_id: scanId, attempt_count: attempt, request_id: run.request_id, idempotency_key: run.idempotency_key || run.request_id, project_id: run.project_id, owner_user_id: run.owner_user_id, website_url: run.website_url, normalized_domain: run.normalized_domain, workspace_cleanup: true};
  const bytes = new TextEncoder().encode(JSON.stringify(payload));
  return {task: {name: `${queuePath}/tasks/standard150-cleanup-${scanId}-a${attempt}`, dispatchDeadline: "480s", httpRequest: {url: target.href, httpMethod: "POST", headers: {"content-type": "application/json"}, body: btoa(String.fromCharCode(...bytes)), oidcToken: {serviceAccountEmail: invokerServiceAccount, audience: target.origin}}}};
}

async function signature(secret, timestamp, text) {
  const encode = value => new TextEncoder().encode(value);
  const hmac = async (bytes, value) => {
    const key = await crypto.subtle.importKey("raw", bytes, {name:"HMAC",hash:"SHA-256"}, false, ["sign"]);
    return new Uint8Array(await crypto.subtle.sign("HMAC", key, encode(value)));
  };
  const derived = await hmac(encode(secret), "fixlist-dispatch-gateway-v1");
  return Array.from(await hmac(derived, `${timestamp}\n${text}`), byte => byte.toString(16).padStart(2,"0")).join("");
}

export async function ensureWorkspaceCleanup(run, {env = name => Deno.env.get(name), fetchImpl = fetch, tokenImpl = createServiceAccountAccessToken} = {}) {
  if (run?.pipeline_mode !== "staged" || run?.workspace_cleanup_state === "complete") return {complete: true};
  const queuePath = String(env("SCAN_DRAIN_QUEUE_PATH") || "");
  const body = workspaceCleanupTask({run, queuePath, workerUrl: env("SCAN_WORKER_URL"), invokerServiceAccount: env("TASKS_INVOKER_SERVICE_ACCOUNT")});
  const gateway = String(env("SCAN_DISPATCH_GATEWAY_URL") || "");
  const signingKey = String(env("SCAN_EVIDENCE_SIGNING_KEY") || "");
  let response;
  if (gateway && signingKey) {
    const url = new URL(gateway);
    if (url.protocol !== "https:" || url.username || url.password || url.search || url.hash) throw new Error("workspace_cleanup_not_configured");
    const text = JSON.stringify({queue_path: queuePath, task: body.task});
    const timestamp = String(Math.trunc(Date.now()/1000));
    response = await fetchImpl(`${url.href.replace(/\/+$/, "")}/dispatch`, {method:"POST", headers:{"content-type":"application/json","x-fixlist-timestamp":timestamp,"x-fixlist-signature":await signature(signingKey,timestamp,text)},body:text});
  } else {
    const key = String(env("GCP_SERVICE_ACCOUNT_KEY") || "");
    if (!key) throw new Error("workspace_cleanup_not_configured");
    const token = await tokenImpl(key);
    response = await fetchImpl(`https://cloudtasks.googleapis.com/v2/${queuePath}/tasks`, {method:"POST",headers:{authorization:`Bearer ${token}`,"content-type":"application/json"},body:JSON.stringify(body)});
  }
  if (!response.ok && response.status !== 409) throw new Error("workspace_cleanup_enqueue_failed");
  return {complete: false};
}
