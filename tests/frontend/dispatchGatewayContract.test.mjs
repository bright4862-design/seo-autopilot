// Keyless dispatch gateway contract.
//
// With the org policy blocking service-account key creation, the dispatcher's
// only provisionable enqueue route is the Cloud Run dispatch gateway: Base44
// HMAC-signs the {queue_path, task} document with SCAN_EVIDENCE_SIGNING_KEY
// and the gateway creates the Cloud Task using its own attached identity.
//
// The deployed gateway is a validating proxy, not a relay: it rejects any
// document whose queue path, task-name prefix, target URL, method, invoker,
// audience, or dispatchDeadline differs from its own configuration. This
// suite pins the dispatcher to that exact validation surface by re-running
// the gateway's checks against what the dispatcher actually signs and sends,
// so either side drifting breaks a contract test before it breaks a customer
// scan.
import assert from "node:assert/strict";
import { createHmac, webcrypto } from "node:crypto";
import test from "node:test";

if (!globalThis.crypto) globalThis.crypto = webcrypto;

import {
  enqueueScanDrain,
  enqueueScanJob,
} from "../../base44/functions/startStandardScanJob/cloudTasks.js";

const QUEUE = "projects/seo-autopilot-501517/locations/europe-west1/queues/fixlist-standard150";
const WORKER = "https://fixlist-standard150-worker-tpucgyfewa-ew.a.run.app/scan-job";
const WORKER_ORIGIN = "https://fixlist-standard150-worker-tpucgyfewa-ew.a.run.app";
const DRAIN = `${WORKER_ORIGIN}/scan-job-drain`;
const INVOKER = "fixlist-standard150-invoker@seo-autopilot-501517.iam.gserviceaccount.com";
const GATEWAY = "https://fixlist-dispatch-gateway-tpucgyfewa-ew.a.run.app";
const SIGNING_KEY = "test-signing-key";

const baseArgs = {
  queuePath: QUEUE,
  workerUrl: WORKER,
  invokerServiceAccount: INVOKER,
  scanId: "scan_abc123",
  attemptCount: 1,
  payload: { scan_id: "scan_abc123", scan_mode: "standard_150", website_url: "https://example.com" },
};

function withEnv(env, fn) {
  const previous = globalThis.Deno;
  globalThis.Deno = { env: { get: (key) => env[key] ?? "" } };
  return Promise.resolve()
    .then(fn)
    .finally(() => {
      if (previous === undefined) delete globalThis.Deno;
      else globalThis.Deno = previous;
    });
}

function withFetch(impl, fn) {
  const previous = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), init });
    return impl(String(url), init, calls.length);
  };
  return Promise.resolve()
    .then(() => fn(calls))
    .finally(() => {
      globalThis.fetch = previous;
    });
}

const gatewayEnv = {
  SCAN_DISPATCH_GATEWAY_URL: GATEWAY,
  SCAN_EVIDENCE_SIGNING_KEY: SIGNING_KEY,
};

// Mirror of the deployed gateway's /dispatch validation (fixlist-dispatch-
// gateway main.py). Returns the error code the gateway would return, or ""
// when the request would be accepted. Keep in lockstep with the deployment.
function gatewayWouldReject(rawBody, signatureHeader) {
  const expected = createHmac("sha256", SIGNING_KEY).update(rawBody).digest("hex");
  if (!signatureHeader || signatureHeader !== expected) return "invalid_signature";

  let payload;
  try {
    payload = JSON.parse(rawBody);
  } catch {
    return "invalid_json";
  }
  if (payload.queue_path !== QUEUE) return "invalid_queue";
  const task = payload.task;
  if (!task || typeof task !== "object") return "invalid_task";
  if (!String(task.name || "").startsWith(`${QUEUE}/tasks/standard150-`)) return "invalid_task_name";
  const http = task.httpRequest;
  if (!http || typeof http !== "object") return "invalid_http_request";
  if (http.url !== WORKER && http.url !== DRAIN) return "invalid_worker_target";
  if (String(http.httpMethod || "").toUpperCase() !== "POST") return "invalid_method";
  const oidc = http.oidcToken;
  if (!oidc || typeof oidc !== "object") return "missing_oidc";
  if (oidc.serviceAccountEmail !== INVOKER) return "invalid_invoker";
  if (oidc.audience !== WORKER_ORIGIN) return "invalid_audience";
  if (task.dispatchDeadline !== "480s") return "invalid_dispatch_deadline";
  let job;
  try {
    job = JSON.parse(Buffer.from(String(http.body || ""), "base64").toString("utf8"));
  } catch {
    return "invalid_task_body";
  }
  if (!String(job.scan_id || "").trim()) return "missing_scan_id";
  if (job.scan_mode !== undefined && job.scan_mode !== null && job.scan_mode !== "standard_150") {
    return "invalid_scan_mode";
  }
  return "";
}

test("a signing key must exist before any network dispatch is attempted", async () => {
  await withEnv({ SCAN_DISPATCH_GATEWAY_URL: GATEWAY }, () =>
    withFetch(() => {
      throw new Error("must not reach the network");
    }, async (calls) => {
      const result = await enqueueScanJob(baseArgs);
      assert.equal(result.ok, false);
      assert.equal(result.outcomeUnknown, false);
      assert.equal(result.failureCode, "dispatch_gateway_signing_key_missing");
      assert.equal(calls.length, 0);
    }));
});

test("the scan task the dispatcher signs passes the deployed gateway's validation", async () => {
  await withEnv(gatewayEnv, () =>
    withFetch(() => Response.json({ success: true, deduplicated: false }), async (calls) => {
      const result = await enqueueScanJob(baseArgs);
      assert.equal(result.ok, true);
      assert.equal(calls.length, 1);

      const { url, init } = calls[0];
      assert.equal(url, `${GATEWAY}/dispatch`);
      assert.equal(init.method, "POST");
      assert.equal(init.headers["content-type"], "application/json");
      assert.equal(gatewayWouldReject(init.body, init.headers["x-fixlist-signature"]), "");

      // The signed document is exactly {queue_path, task} — nothing else for
      // the gateway to trust or ignore.
      assert.deepEqual(Object.keys(JSON.parse(init.body)).sort(), ["queue_path", "task"]);
      const { task } = JSON.parse(init.body);
      assert.equal(task.name, `${QUEUE}/tasks/standard150-scan_abc123-a1`);
      assert.equal(task.httpRequest.url, WORKER);
    }));
});

test("the drain watchdog task passes the same gateway validation", async () => {
  await withEnv(gatewayEnv, () =>
    withFetch(() => Response.json({ success: true, deduplicated: false }), async (calls) => {
      const result = await enqueueScanDrain({
        ...baseArgs,
        payload: { ...baseArgs.payload, scan_mode: undefined, drain_after: "2026-08-13T00:00:00.000Z" },
      });
      assert.equal(result.ok, true);
      const { init } = calls[0];
      assert.equal(gatewayWouldReject(init.body, init.headers["x-fixlist-signature"]), "");
      const { task } = JSON.parse(init.body);
      assert.equal(task.name, `${QUEUE}/tasks/standard150-drain-scan_abc123-a1`);
      assert.equal(task.httpRequest.url, DRAIN);
      assert.ok(task.scheduleTime, "the watchdog must be delayed, not immediate");
    }));
});

test("gateway responses map to the dispatcher's dedup and retry semantics", async () => {
  await withEnv(gatewayEnv, async () => {
    // 409 — deterministic task name already exists: success, deduplicated.
    await withFetch(() => new Response("conflict", { status: 409 }), async () => {
      const result = await enqueueScanJob(baseArgs);
      assert.equal(result.ok, true);
      assert.equal(result.deduplicated, true);
    });

    // 200 with deduplicated:true from the gateway's own 409 mapping.
    await withFetch(() => Response.json({ success: true, deduplicated: true, taskName: "t" }), async () => {
      const result = await enqueueScanJob(baseArgs);
      assert.equal(result.ok, true);
      assert.equal(result.deduplicated, true);
    });

    // 4xx — the gateway rejected the document: definite failure, safe to
    // terminalize the run; the task was provably never created.
    await withFetch(() => new Response("denied", { status: 403 }), async () => {
      const result = await enqueueScanJob(baseArgs);
      assert.equal(result.ok, false);
      assert.equal(result.outcomeUnknown, false);
      assert.equal(result.failureCode, "dispatch_gateway_http_403");
    });

    // 5xx — the gateway may or may not have reached Cloud Tasks: the outcome
    // is unknown, so the dispatcher must NOT terminalize the run as failed.
    await withFetch(() => new Response("upstream", { status: 502 }), async () => {
      const result = await enqueueScanJob(baseArgs);
      assert.equal(result.ok, false);
      assert.equal(result.outcomeUnknown, true);
    });

    // Network failure — same uncertainty.
    await withFetch(() => {
      throw new Error("connection reset");
    }, async () => {
      const result = await enqueueScanJob(baseArgs);
      assert.equal(result.ok, false);
      assert.equal(result.outcomeUnknown, true);
      assert.equal(result.failureCode, "dispatch_gateway_unreachable");
    });
  });
});

test("the worker URL must match the gateway's configuration byte for byte", async () => {
  // The gateway compares http.url against its own SCAN_WORKER_URL with
  // rstrip("/") applied at startup. The dispatcher sends SCAN_WORKER_URL
  // exactly as Base44 supplies it, so a trailing slash or a bare origin in
  // the Base44 secret produces invalid_worker_target at the gateway — a
  // loud, definite 400, never a silently mistargeted task.
  await withEnv(gatewayEnv, () =>
    withFetch(() => Response.json({ success: true }), async (calls) => {
      await enqueueScanJob({ ...baseArgs, workerUrl: `${WORKER}/` });
      const { init } = calls[0];
      assert.equal(gatewayWouldReject(init.body, init.headers["x-fixlist-signature"]), "invalid_worker_target");
    }));
});

test("without a gateway URL the key-based route is selected and fails closed", async () => {
  await withEnv({}, () =>
    withFetch(() => {
      throw new Error("must not reach the network");
    }, async (calls) => {
      const result = await enqueueScanJob(baseArgs);
      assert.equal(result.ok, false);
      assert.equal(result.failureCode, "tasks_credentials_not_configured");
      assert.equal(calls.length, 0);
    }));
});
