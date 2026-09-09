import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const checkoutPath = "base44/functions/createAccessCheckout/entry.ts";
const checkoutSource = readFileSync(checkoutPath, "utf8");

async function importHandlerWithHarness(source, harnessName) {
  const withoutImports = source.replace(/^import .*;\s*$/gm, "");
  const harnessPrelude = `const { createClientFromRequest, Stripe, secrets, console = globalThis.console } = globalThis.${harnessName};`;
  const moduleSource = `${harnessPrelude}\n${withoutImports}`;
  return import(`data:text/javascript;base64,${Buffer.from(moduleSource).toString("base64")}`);
}

test("first-time authenticated customer gets exactly one pending Access row before checkout", async () => {
  const priorDeno = globalThis.Deno;
  const env = new Map([
    ["BETA_CHECKOUT_ENABLED", "true"],
    ["BETA_CHECKOUT_GENERATION", "public-2026-09"],
  ]);
  let accessRecord = null;
  let createCount = 0;
  const stripeCalls = [];

  const Access = {
    async filter(query) {
      if (!accessRecord) return [];
      const byOwner = query.owner_user_id && query.owner_user_id === accessRecord.owner_user_id;
      const byEmail = query.user_email && query.user_email === accessRecord.user_email;
      return byOwner || byEmail ? [{ ...accessRecord }] : [];
    },
    async create(fields) {
      createCount += 1;
      accessRecord = { id: "access-new", ...fields };
      return { ...accessRecord };
    },
    async update(id, fields) {
      assert.equal(id, accessRecord.id);
      accessRecord = { ...accessRecord, ...fields };
      return { ...accessRecord };
    },
  };
  const base44 = {
    auth: { me: async () => ({ id: "user-new", email: "new@example.com" }) },
    asServiceRole: { entities: { Access } },
  };

  class FakeStripe {
    constructor() {
      this.checkout = {
        sessions: {
          retrieve: async () => { throw new Error("unexpected retrieve"); },
          create: async (params, options) => {
            stripeCalls.push({ params, options });
            return {
              id: "cs_new",
              status: "open",
              payment_status: "unpaid",
              url: "https://checkout.stripe.test/cs_new",
              customer_email: params.customer_email,
              client_reference_id: params.client_reference_id,
              metadata: params.metadata,
            };
          },
        },
      };
    }
  }

  globalThis.Deno = { env: { get: (name) => env.get(name) } };
  globalThis.__publicCheckoutProvisionHarness = {
    createClientFromRequest: () => base44,
    Stripe: FakeStripe,
    secrets: { get: () => "test-secret" },
  };

  try {
    const { default: checkoutHandler } = await importHandlerWithHarness(
      checkoutSource,
      "__publicCheckoutProvisionHarness",
    );
    const response = await checkoutHandler(new Request("https://function.test", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ origin: "https://rich-rank-pilot-flow.base44.app" }),
    }));
    assert.equal(response.status, 200);
    assert.equal((await response.json()).url, "https://checkout.stripe.test/cs_new");
    assert.equal(createCount, 1);
    assert.equal(stripeCalls.length, 1);
    assert.deepEqual(
      {
        user_email: accessRecord.user_email,
        owner_user_id: accessRecord.owner_user_id,
        access_status: accessRecord.access_status,
        plan_id: accessRecord.plan_id,
        grant_source: accessRecord.grant_source,
        app_id: accessRecord.app_id,
        has_full_access: accessRecord.has_full_access,
      },
      {
        user_email: "new@example.com",
        owner_user_id: "user-new",
        access_status: "pending",
        plan_id: "standard150_lifetime",
        grant_source: "checkout_pending",
        app_id: "6a498732ec779dfaaeab0e53",
        has_full_access: false,
      },
    );
  } finally {
    delete globalThis.__publicCheckoutProvisionHarness;
    if (priorDeno === undefined) delete globalThis.Deno;
    else globalThis.Deno = priorDeno;
  }
});

test("public checkout source contains no static invitation membership gate", () => {
  assert.doesNotMatch(checkoutSource, /BETA_COHORT_ALLOWED_USER_IDS|checkout_not_invited|MAX_BETA_CUSTOMERS/);
});
