// Keyless dispatch gateway contract.
//
// Base44 cannot depend on a long-lived Google service-account key. The durable
// dispatcher signs the exact {queue_path, task} document with a short-lived
// timestamped HMAC derived from SCAN_EVIDENCE_SIGNING_KEY; the public Cloud Run
// gateway validates that envelope and creates only the allowlisted Cloud Task
// with its attached Google identity.
import assert from "node:assert/strict";
import { createHmac, webcrypto } from "node:crypto";
import { readFileSync } from "node:fs";
import test from "node:test";

if (!globalThis.crypto) globalThis.crypto = webcrypto;

import {
  enqueueScanDrain,
  enqueueScanJob,
} from "../../base44/functions/startStandardScanJob/cloudTasks.js";

const QUEUE = "projects/seo-autopilot-501517/locations/europe-west1/queues/fixlist-standard150";
const DRAIN_QUEUE = "projects/seo-autopilot-501517/locations/europe-west1/queues/fixlist-standard150-drain";
const WORKER = "https://fixlist-standard150-worker-tpucgyfewa-ew.a.run.app/scan-job";
const WORKER_ORIGIN = "https://fixlist-standard150-worker-tpucgyfewa-ew.a.run.app";
const DRAIN = `${WORKER_ORIGIN}/scan-job-drain`;
const INVOKER = "fixlist-standard150-invoker@seo-autopilot-501517.iam.gserviceaccount.com";
const GATEWAY = "https://fixlist-dispatch-gateway-tpucgyfewa-ew.a.run.app";
const SIGNING_KEY = "test-signing-key";
const SIGNING_DOMAIN = "fixlist-dispatch-gateway-v1";

const baseArgs = {
  queuePath: QUEUE,
  workerUrl: WORKER,
  invokerServiceAccount: INVOKER,
  scanId: "scan_abc123",
  attemptCount: 1,
  payload: {
    scan_id: "scan_abc123",
    scan_mode: "standard_150",
    respect_robots_txt: true,
    website_url: "https://example.com",
  },
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

function expectedSignature(timestamp, rawBody) {
  const derived = createHmac("sha256", SIGNING_KEY)
    .update(SIGNING_DOMAIN)
    .digest();
  return createHmac("sha256", derived)
    .update(`${timestamp}\n${rawBody}`)
    .digest("hex");
}

// Mirror the canonical dispatch-gateway/main.py validation. Returning an error
// code here means the real gateway would reject the dispatcher request.
function gatewayWouldReject(rawBody, signatureHeader, timestampHeader, nowSeconds = Math.trunc(Date.now() / 1000)) {
  if (!/^\d+$/.test(String(timestampHeader || ""))) return "invalid_timestamp";
  const requestSeconds = Number(timestampHeader);
  if (Math.abs(nowSeconds - requestSeconds) > 300) return "stale_request";

  const expected = expectedSignature(timestampHeader, rawBody);
  if (!signatureHeader || signatureHeader !== expected) return "invalid_signature";

  let payload;
  try {
    payload = JSON.parse(rawBody);
  } catch {
    return "invalid_json";
  }
  if (payload.queue_path !== QUEUE && payload.queue_path !== DRAIN_QUEUE) return "invalid_queue";

  const task = payload.task;
  if (!task || typeof task !== "object") return "invalid_task";
  const prefix = `${payload.queue_path}/tasks/`;
  const name = String(task.name || "");
  if (!name.startsWith(prefix)) return "invalid_task_name";
  const match = /^standard150-(?:(drain)-)?([A-Za-z0-9_-]+)-a([1-9][0-9]*)$/.exec(name.slice(prefix.length));
  if (!match) return "invalid_task_name";
  const isDrain = Boolean(match[1]);
  const nameScanId = match[2];
  const expectedQueue = isDrain ? DRAIN_QUEUE : QUEUE;
  if (payload.queue_path !== expectedQueue) return "invalid_queue";

  if (task.dispatchDeadline !== "480s") return "invalid_dispatch_deadline";

  const http = task.httpRequest;
  if (!http || typeof http !== "object") return "invalid_http_request";
  if (String(http.httpMethod || "").toUpperCase() !== "POST") return "invalid_method";
  const expectedTarget = isDrain ? DRAIN : WORKER;
  if ((http.url !== WORKER && http.url !== DRAIN) || http.url !== expectedTarget) {
    return "invalid_worker_target";
  }

  const oidc = http.oidcToken;
  if (!oidc || typeof oidc !== "object") return "missing_oidc";
  if (oidc.serviceAccountEmail !== INVOKER) return "invalid_invoker";
  if (oidc.audience !== WORKER_ORIGIN) return "invalid_audience";

  let job;
  try {
    job = JSON.parse(Buffer.from(String(http.body || ""), "base64").toString("utf8"));
  } catch {
    return "invalid_task_body";
  }
  const scanId = String(job.scan_id || "").replace(/[^A-Za-z0-9_-]/g, "");
  if (!scanId || scanId !== nameScanId) return "scan_identity_mismatch";

  if (isDrain) {
    if (!task.scheduleTime) return "missing_drain_schedule";
    if (!String(job.drain_after || "").trim()) return "missing_drain_after";
  } else {
    if (task.scheduleTime) return "unexpected_scan_schedule";
    if (job.scan_mode !== "standard_150") return "invalid_scan_mode";
    if (job.respect_robots_txt !== true) return "invalid_robots_policy";
  }

  return "";
}

function rejectionForCall(call) {
  return gatewayWouldReject(
    call.init.body,
    call.init.headers["x-fixlist-signature"],
    call.init.headers["x-fixlist-timestamp"],
  );
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

test("the scan task the dispatcher signs passes the canonical gateway validation", async () => {
  await withEnv(gatewayEnv, () =>
    withFetch(() => Response.json({ success: true, deduplicated: false }), async (calls) => {
      const result = await enqueueScanJob(baseArgs);
      assert.equal(result.ok, true);
      assert.equal(calls.length, 1);

      const call = calls[0];
      assert.equal(call.url, `${GATEWAY}/dispatch`);
      assert.equal(call.init.method, "POST");
      assert.equal(call.init.headers["content-type"], "application/json");
      assert.match(call.init.headers["x-fixlist-timestamp"], /^\d{10}$/);
      assert.match(call.init.headers["x-fixlist-signature"], /^[0-9a-f]{64}$/);
      assert.equal(rejectionForCall(call), "");

      assert.deepEqual(Object.keys(JSON.parse(call.init.body)).sort(), ["queue_path", "task"]);
      const { task } = JSON.parse(call.init.body);
      assert.equal(task.name, `${QUEUE}/tasks/standard150-scan_abc123-a1`);
      assert.equal(task.httpRequest.url, WORKER);
    }));
});

test("the drain watchdog task passes the same canonical gateway validation", async () => {
  await withEnv(gatewayEnv, () =>
    withFetch(() => Response.json({ success: true, deduplicated: false }), async (calls) => {
      const result = await enqueueScanDrain({
        ...baseArgs,
        queuePath: DRAIN_QUEUE,
        payload: {
          scan_id: "scan_abc123",
          website_url: "https://example.com",
          drain_after: "2026-08-13T00:00:00.000Z",
        },
      });
      assert.equal(result.ok, true);
      assert.equal(rejectionForCall(calls[0]), "");
      const { task } = JSON.parse(calls[0].init.body);
      assert.equal(task.name, `${DRAIN_QUEUE}/tasks/standard150-drain-scan_abc123-a1`);
      assert.equal(task.httpRequest.url, DRAIN);
      assert.ok(task.scheduleTime, "the watchdog must be delayed, not immediate");
    }));
});

test("timestamp and signature are bound to the exact request body", async () => {
  await withEnv(gatewayEnv, () =>
    withFetch(() => Response.json({ success: true }), async (calls) => {
      await enqueueScanJob(baseArgs);
      const call = calls[0];
      const timestamp = call.init.headers["x-fixlist-timestamp"];
      const signature = call.init.headers["x-fixlist-signature"];
      assert.equal(signature, expectedSignature(timestamp, call.init.body));
      assert.equal(gatewayWouldReject(call.init.body, signature, String(Number(timestamp) - 301), Number(timestamp)), "stale_request");
      assert.equal(gatewayWouldReject(`${call.init.body} `, signature, timestamp, Number(timestamp)), "invalid_signature");
    }));
});

test("gateway responses map to the dispatcher's dedup and retry semantics", async () => {
  await withEnv(gatewayEnv, async () => {
    await withFetch(() => new Response("conflict", { status: 409 }), async () => {
      const result = await enqueueScanJob(baseArgs);
      assert.equal(result.ok, true);
      assert.equal(result.deduplicated, true);
    });

    await withFetch(() => Response.json({ success: true, deduplicated: true, taskName: "t" }), async () => {
      const result = await enqueueScanJob(baseArgs);
      assert.equal(result.ok, true);
      assert.equal(result.deduplicated, true);
    });

    await withFetch(() => new Response("denied", { status: 403 }), async () => {
      const result = await enqueueScanJob(baseArgs);
      assert.equal(result.ok, false);
      assert.equal(result.outcomeUnknown, false);
      assert.equal(result.failureCode, "dispatch_gateway_http_403");
    });

    await withFetch(() => new Response("upstream", { status: 503 }), async () => {
      const result = await enqueueScanJob(baseArgs);
      assert.equal(result.ok, false);
      assert.equal(result.outcomeUnknown, true);
    });

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

test("the worker URL must match the gateway configuration byte for byte", async () => {
  await withEnv(gatewayEnv, () =>
    withFetch(() => Response.json({ success: true }), async (calls) => {
      await enqueueScanJob({ ...baseArgs, workerUrl: `${WORKER}/` });
      assert.equal(rejectionForCall(calls[0]), "invalid_worker_target");
    }));
});

test("the canonical gateway source enforces the validation this suite mirrors", () => {
  const source = readFileSync(new URL("../../dispatch-gateway/main.py", import.meta.url), "utf8");

  for (const pinned of [
    'request.headers.get("x-fixlist-timestamp", "")',
    'request.headers.get("x-fixlist-signature", "")',
    'b"fixlist-dispatch-gateway-v1"',
    "MAX_CLOCK_SKEW_SECONDS",
    "hmac.compare_digest(supplied, expected)",
    'queue_path not in {QUEUE_PATH, DRAIN_QUEUE_PATH}',
    'expected_queue = DRAIN_QUEUE_PATH if is_drain else QUEUE_PATH',
    'queue_path != expected_queue',
    "TASK_RE.fullmatch(short_name)",
    "scan_id != name_scan_id",
    "target != expected_target",
    'oidc.get("serviceAccountEmail") != INVOKER_SA',
    'oidc.get("audience") != WORKER_ORIGIN',
    'task.get("dispatchDeadline") != "480s"',
    'job.get("scan_mode") != "standard_150"',
    'job.get("respect_robots_txt") is not True',
    'not task.get("scheduleTime")',
    'task.get("scheduleTime")',
    "upstream.status_code == 409",
  ]) {
    assert.ok(source.includes(pinned), `gateway source lost its pinned check: ${pinned}`);
  }

  assert.doesNotMatch(source, /GCP_SERVICE_ACCOUNT_KEY|private_key/);
  assert.match(source, /google\.auth\.default\(/);

  const deploy = readFileSync(new URL("../../scripts/deploy_dispatch_gateway.sh", import.meta.url), "utf8");
  assert.match(deploy, /--source="\$SOURCE_DIR"/);
  assert.match(deploy, /SCAN_DRAIN_QUEUE_PATH=\$DRAIN_QUEUE_PATH/);
  assert.match(deploy, /--set-secrets="SCAN_EVIDENCE_SIGNING_KEY=/);
  assert.match(deploy, /--no-invoker-iam-check/);
  assert.match(deploy, /confirmation must equal exact source SHA/);
  assert.doesNotMatch(deploy, /--set-env-vars="[^"]*SCAN_EVIDENCE_SIGNING_KEY/);
  assert.doesNotMatch(deploy, /keys create|iam service-accounts keys/);
});

test("without a gateway URL the legacy key route fails closed", async () => {
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
