import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const billingSource = readFileSync("src/pages/Billing.jsx", "utf8");

async function importActivationHelpers() {
  const helperBlock = billingSource.match(
    /export const ACTIVATION_POLL_MAX_ATTEMPTS[\s\S]*?(?=export default function Billing)/,
  )?.[0];
  assert.ok(helperBlock, "Billing must expose its activation polling helper block");
  const moduleSource = helperBlock.replace(/^export /gm, "");
  return import(
    `data:text/javascript;base64,${Buffer.from(`${moduleSource}\nexport { pollForActivatedAccess };`).toString("base64")}`
  );
}

const originalWindow = globalThis.window;
globalThis.window = globalThis;
const { pollForActivatedAccess } = await importActivationHelpers();

test.after(() => {
  if (originalWindow === undefined) delete globalThis.window;
  else globalThis.window = originalWindow;
});

test("activation polling succeeds after Stripe entitlement becomes visible", async () => {
  let calls = 0;
  const activeAccess = { fullAccess: true, record: { access_status: "active" } };

  const result = await pollForActivatedAccess({
    load: async () => {
      calls += 1;
      return calls === 3 ? activeAccess : { fullAccess: false };
    },
    maxAttempts: 5,
    intervalMs: 1,
    maxDurationMs: 1_000,
    requestTimeoutMs: 100,
  });

  assert.equal(result.status, "active");
  assert.equal(result.attempts, 3);
  assert.equal(result.access, activeAccess);
  assert.equal(calls, 3);
});

test("activation polling stops after the configured attempt bound", async () => {
  let calls = 0;
  const result = await pollForActivatedAccess({
    load: async () => {
      calls += 1;
      return { fullAccess: false };
    },
    maxAttempts: 3,
    intervalMs: 1,
    maxDurationMs: 1_000,
    requestTimeoutMs: 100,
  });

  assert.equal(result.status, "timeout");
  assert.equal(result.attempts, 3);
  assert.equal(calls, 3);
});

test("activation polling has a wall-clock bound even when access loading hangs", async () => {
  const startedAt = Date.now();
  const result = await pollForActivatedAccess({
    load: () => new Promise(() => {}),
    maxAttempts: 10,
    intervalMs: 5,
    maxDurationMs: 25,
    requestTimeoutMs: 100,
  });

  assert.equal(result.status, "timeout");
  assert.ok(Date.now() - startedAt < 250, "the overall activation deadline must win");
});

test("aborting activation clears the pending wait and returns without another read", async () => {
  const controller = new AbortController();
  let calls = 0;
  const polling = pollForActivatedAccess({
    load: async () => {
      calls += 1;
      return { fullAccess: false };
    },
    signal: controller.signal,
    maxAttempts: 10,
    intervalMs: 1_000,
    maxDurationMs: 10_000,
    requestTimeoutMs: 100,
  });
  window.setTimeout(() => controller.abort(), 5);

  const result = await polling;
  assert.equal(result.status, "cancelled");
  assert.equal(calls, 1);
});

test("the paid return suppresses checkout and offers polling-only recovery", () => {
  assert.match(billingSource, /searchParams\.get\("paid"\) === "1"/);
  assert.match(billingSource, /Activating your access/);
  assert.match(billingSource, /Retry activation/);
  assert.match(billingSource, /retry only checks your existing payment/i);
  assert.match(billingSource, /controller\.abort\(\)/);

  const retryHandler = billingSource.match(
    /function retryActivation\(\) \{[\s\S]*?\n  \}/,
  )?.[0];
  assert.ok(retryHandler, "Billing must have an explicit activation retry handler");
  assert.doesNotMatch(retryHandler, /createAccessCheckout|startCheckout|UnlockAccessButton/);

  const standardAction = billingSource.match(
    /if \(plan\.id === "standard_150"\) \{[\s\S]*?\n    \}/,
  )?.[0];
  assert.ok(standardAction, "the Standard 150 plan action must be present");
  assert.match(standardAction, /checkoutSuppressed/);
});
