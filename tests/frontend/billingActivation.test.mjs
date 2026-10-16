import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { transformSync } from "esbuild";

const billingSource = readFileSync("src/pages/Billing.jsx", "utf8");

const compiledBilling = transformSync(billingSource, { loader: "jsx", format: "cjs" }).code;

function renderCheckoutReturn({ access = null, activationStatus = "checking" } = {}) {
  // Render the actual page at the access-read boundary without running effects
  // or contacting Stripe/Base44. A paid=1 URL is deliberately not payment proof.
  const states = ["none", null, "", access, activationStatus !== "checking", activationStatus, 0];
  let stateIndex = 0;
  const hooks = {
    ...React,
    useState: () => [states[stateIndex++], () => {}],
    useEffect: () => {},
    useRef: (initial) => ({ current: initial }),
  };
  const boundary = {
    react: hooks,
    "react-router-dom": {
      useNavigate: () => () => {},
      useSearchParams: () => [new URLSearchParams("paid=1")],
    },
    "@/api/base44Client": { base44: {} },
    "@/lib/analytics": { trackEvent: () => {} },
    "@/components/billing/LeadRequestModal": { default: () => null },
    "@/components/billing/UnlockAccessButton": {
      default: () => React.createElement("button", null, "Start checkout"),
    },
    "@/lib/access": {
      UNLOCK_PRICE_LABEL: "$49",
      loadAccess: () => { throw new Error("render must not start an access read"); },
    },
  };
  const module = { exports: {} };
  new Function("require", "module", "exports", compiledBilling)((name) => {
    assert.ok(Object.hasOwn(boundary, name), `unexpected render dependency: ${name}`);
    return boundary[name];
  }, module, module.exports);
  return renderToStaticMarkup(module.exports.default());
}

test("an unverified paid return never renders a completed payment or active access", () => {
  for (const activationStatus of ["checking", "timeout"]) {
    const html = renderCheckoutReturn({ access: { fullAccess: false }, activationStatus });
    assert.doesNotMatch(html, /Payment complete|existing payment|>Full access is active<|Continue to your account|>Start checkout</i);
    assert.match(html, /checking.*access|access.*not.*confirmed|haven.{0,12}t confirmed/i);
  }
});

test("verified access still renders the active state after a checkout return", () => {
  const html = renderCheckoutReturn({ access: { fullAccess: true }, activationStatus: "active" });
  assert.match(html, /Full access is active/);
  assert.match(html, /Continue to your account/);
  assert.doesNotMatch(html, /Start checkout/);
});

async function importActivationHelpers() {
  const helperBlock = billingSource.match(
    /export const ACTIVATION_POLL_MAX_ATTEMPTS[\s\S]*?(?=export default function Billing)/,
  )?.[0];
  assert.ok(helperBlock, "Billing must expose its activation polling helper block");
  // Keep the browser timer alias local to the extracted helpers. Shared window
  // cleanup can race with polling when Node 20 resumes this awaited import.
  const moduleSource = `const window = globalThis;\n${helperBlock.replace(/^export /gm, "")}`;
  return import(
    `data:text/javascript;base64,${Buffer.from(`${moduleSource}\nexport { pollForActivatedAccess };`).toString("base64")}`
  );
}

const { pollForActivatedAccess } = await importActivationHelpers();

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
  globalThis.setTimeout(() => controller.abort(), 5);

  const result = await polling;
  assert.equal(result.status, "cancelled");
  assert.equal(calls, 1);
});

test("the paid return suppresses checkout and offers polling-only recovery", () => {
  assert.match(billingSource, /searchParams\.get\("paid"\) === "1"/);
  assert.match(billingSource, /Checking your access/);
  assert.match(billingSource, /onClick=\{retryActivation\}>Check again/);
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
