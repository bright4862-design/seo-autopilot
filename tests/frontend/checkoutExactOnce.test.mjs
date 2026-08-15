import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  checkoutFailureCode,
  checkoutFailureMessage,
} from "../../src/lib/checkout.js";

const checkoutPath = "base44/functions/createAccessCheckout/entry.ts";
const webhookPath = "base44/functions/stripeWebhook/entry.ts";
const checkoutSource = readFileSync(checkoutPath, "utf8");
const webhookSource = readFileSync(webhookPath, "utf8");

async function importPureHelpers(source, names) {
  const withoutImports = source.replace(/^import .*;\s*$/gm, "");
  const moduleSource = `${withoutImports}\nexport { ${names.join(", ")} };`;
  return import(`data:text/javascript;base64,${Buffer.from(moduleSource).toString("base64")}`);
}

async function importHandlerWithHarness(source, harnessName) {
  const withoutImports = source.replace(/^import .*;\s*$/gm, "");
  const harnessPrelude = `const { createClientFromRequest, Stripe, secrets, console = globalThis.console } = globalThis.${harnessName};`;
  const moduleSource = `${harnessPrelude}\n${withoutImports}`;
  return import(`data:text/javascript;base64,${Buffer.from(moduleSource).toString("base64")}`);
}

const checkoutHelpers = await importPureHelpers(checkoutSource, [
  "MAX_BETA_CUSTOMERS",
  "PRODUCTION_APP_ORIGIN",
  "betaCheckoutPolicy",
  "checkoutIdempotencyKey",
  "classifyExistingCheckoutSession",
  "resolveCheckoutReturnOrigin",
]);
const webhookHelpers = await importPureHelpers(webhookSource, ["classifyPaidDelivery"]);

test("checkout failures remain customer-safe and distinguish paused beta admission", () => {
  assert.equal(
    checkoutFailureCode({ response: { data: { code: "checkout_paused", error: "internal" } } }),
    "checkout_paused",
  );
  assert.equal(
    checkoutFailureMessage("checkout_paused"),
    "Paid beta checkout is temporarily paused. No payment was started.",
  );
  assert.equal(
    checkoutFailureMessage("checkout_not_invited"),
    "This paid beta cohort is currently invite-only.",
  );
  assert.doesNotMatch(checkoutFailureMessage("unknown_internal_code"), /internal|stripe|access[_-]id/i);
});

test("checkout accepts only exact trusted return origins", () => {
  const priorDeno = globalThis.Deno;
  const values = new Map([
    ["CHECKOUT_RETURN_ORIGINS", "https://beta.example.com, https://preview.example.com"],
    ["CHECKOUT_ALLOW_LOCALHOST", "false"],
  ]);
  globalThis.Deno = { env: { get: (name) => values.get(name) } };

  try {
    assert.equal(
      checkoutHelpers.PRODUCTION_APP_ORIGIN,
      "https://rich-rank-pilot-flow.base44.app",
    );
    assert.equal(
      checkoutHelpers.resolveCheckoutReturnOrigin("https://rich-rank-pilot-flow.base44.app/"),
      "https://rich-rank-pilot-flow.base44.app",
    );
    assert.equal(
      checkoutHelpers.resolveCheckoutReturnOrigin("https://beta.example.com"),
      "https://beta.example.com",
    );
    assert.equal(checkoutHelpers.resolveCheckoutReturnOrigin("https://evil.example"), "");
    assert.equal(
      checkoutHelpers.resolveCheckoutReturnOrigin("https://rich-rank-pilot-flow.base44.app.evil.example"),
      "",
    );
    assert.equal(checkoutHelpers.resolveCheckoutReturnOrigin("http://beta.example.com"), "");
    assert.equal(checkoutHelpers.resolveCheckoutReturnOrigin("http://localhost:5173"), "");

    values.set("CHECKOUT_ALLOW_LOCALHOST", "true");
    assert.equal(
      checkoutHelpers.resolveCheckoutReturnOrigin("http://localhost:5173"),
      "http://localhost:5173",
    );
    assert.equal(
      checkoutHelpers.resolveCheckoutReturnOrigin("http://127.0.0.1:4173"),
      "http://127.0.0.1:4173",
    );
    assert.equal(checkoutHelpers.resolveCheckoutReturnOrigin("http://localhost.evil.example"), "");
  } finally {
    if (priorDeno === undefined) delete globalThis.Deno;
    else globalThis.Deno = priorDeno;
  }
});

test("the paid beta is default-off and capped at 25 exact invited user IDs", () => {
  const priorDeno = globalThis.Deno;
  const values = new Map();
  globalThis.Deno = { env: { get: (name) => values.get(name) } };

  try {
    assert.equal(checkoutHelpers.MAX_BETA_CUSTOMERS, 25);
    assert.deepEqual(checkoutHelpers.betaCheckoutPolicy(), {
      ok: false,
      code: "checkout_paused",
      allowedUserIds: [],
      generation: "",
    });

    values.set("BETA_CHECKOUT_ENABLED", "true");
    values.set("BETA_CHECKOUT_GENERATION", "cohort-2026-08");
    values.set("BETA_COHORT_ALLOWED_USER_IDS", "user-1, user-2\nuser-1");
    assert.deepEqual(checkoutHelpers.betaCheckoutPolicy(), {
      ok: true,
      code: "",
      allowedUserIds: ["user-1", "user-2"],
      generation: "cohort-2026-08",
    });

    values.set(
      "BETA_COHORT_ALLOWED_USER_IDS",
      Array.from({ length: 26 }, (_, index) => `user-${index + 1}`).join(","),
    );
    assert.equal(checkoutHelpers.betaCheckoutPolicy().code, "checkout_configuration_invalid");

    values.set("BETA_COHORT_ALLOWED_USER_IDS", "user-1,not/an/id");
    assert.equal(checkoutHelpers.betaCheckoutPolicy().code, "checkout_configuration_invalid");
    values.set("BETA_COHORT_ALLOWED_USER_IDS", "user-1");
    values.set("BETA_CHECKOUT_GENERATION", "generation with spaces");
    assert.equal(checkoutHelpers.betaCheckoutPolicy().code, "checkout_configuration_invalid");
  } finally {
    if (priorDeno === undefined) delete globalThis.Deno;
    else globalThis.Deno = priorDeno;
  }
});

test("pending checkout retries reuse one user-stable Stripe idempotency key", async () => {
  const access = { id: "access-1", owner_user_id: "user-1", stripe_checkout_session_id: "" };
  const expectedKey = (previousSessionId) => `access-checkout:6a498732ec779dfaaeab0e53:${createHash("sha256")
    .update(`6a498732ec779dfaaeab0e53\nuser-1\ncohort-2026-08\n${previousSessionId}`)
    .digest("hex")}`;
  assert.equal(
    await checkoutHelpers.checkoutIdempotencyKey(access, "cohort-2026-08"),
    expectedKey("initial"),
  );
  assert.equal(
    await checkoutHelpers.checkoutIdempotencyKey({
      ...access,
      stripe_checkout_session_id: "cs_expired_1",
    }, "cohort-2026-08"),
    expectedKey("cs_expired_1"),
  );

  assert.equal(
    checkoutHelpers.classifyExistingCheckoutSession({
      id: "cs_open_1",
      status: "open",
      payment_status: "unpaid",
      url: "https://checkout.stripe.test/one",
    }),
    "reusable",
  );
  assert.equal(
    checkoutHelpers.classifyExistingCheckoutSession({
      id: "cs_paid_1",
      status: "complete",
      payment_status: "paid",
      url: null,
    }),
    "payment_processing",
  );
  assert.equal(
    checkoutHelpers.classifyExistingCheckoutSession({
      id: "cs_expired_1",
      status: "expired",
      payment_status: "unpaid",
      url: null,
    }),
    "renew",
  );

  assert.match(checkoutSource, /checkout\.sessions\.retrieve\(previousSessionId\)/);
  assert.match(checkoutSource, /\{ idempotencyKey: await checkoutIdempotencyKey\(access, policy\.generation\) \}/);
  assert.ok(
    checkoutSource.indexOf("checkout.sessions.retrieve(previousSessionId)") <
      checkoutSource.indexOf("checkout.sessions.create("),
    "the stored pending session must be checked before creating another",
  );
});

test("the checkout handler rejects paused/uninvited users before writes and never creates Access", async () => {
  const priorDeno = globalThis.Deno;
  const env = new Map([
    ["BETA_CHECKOUT_ENABLED", "true"],
    ["BETA_CHECKOUT_GENERATION", "cohort-2026-08"],
    ["BETA_COHORT_ALLOWED_USER_IDS", "user-1"],
  ]);
  let accessRecord = {
    id: "access-1",
    owner_user_id: "user-1",
    user_email: "paid@example.com",
    access_status: "pending",
    has_full_access: false,
    stripe_checkout_session_id: "",
  };
  let accessCreateCount = 0;
  const sessionCreateCalls = [];
  const sessionsByKey = new Map();
  let synchronizePendingWrites = false;
  let pendingWriteCount = 0;
  let releasePendingWrites;
  const bothPendingWrites = new Promise((resolve) => {
    releasePendingWrites = resolve;
  });

  const Access = {
    async filter(query) {
      if (!accessRecord) return [];
      const matchesOwner = query.owner_user_id && query.owner_user_id === accessRecord.owner_user_id;
      const matchesEmail = query.user_email && query.user_email === accessRecord.user_email;
      return matchesOwner || matchesEmail ? [{ ...accessRecord }] : [];
    },
    async create(fields) {
      accessCreateCount += 1;
      throw new Error(`Access.create must not run during paid beta checkout: ${JSON.stringify(fields)}`);
    },
    async update(id, fields) {
      assert.equal(id, accessRecord.id);
      accessRecord = { ...accessRecord, ...fields };
      if (synchronizePendingWrites && !fields.stripe_checkout_session_id) {
        pendingWriteCount += 1;
        if (pendingWriteCount === 2) releasePendingWrites();
        await bothPendingWrites;
      }
      return { ...accessRecord };
    },
  };
  const base44 = {
    auth: { me: async () => ({ id: "user-1", email: "paid@example.com" }) },
    asServiceRole: { entities: { Access } },
  };

  class FakeStripe {
    constructor() {
      this.checkout = {
        sessions: {
          retrieve: async (id) => {
            const session = [...sessionsByKey.values()].find((candidate) => candidate.id === id);
            if (!session) throw new Error("missing_test_session");
            return session;
          },
          create: async (params, options) => {
            sessionCreateCalls.push({ params, options });
            const existing = sessionsByKey.get(options.idempotencyKey);
            if (existing) return existing;
            const session = {
              id: "cs_pending_1",
              status: "open",
              payment_status: "unpaid",
              url: "https://checkout.stripe.test/cs_pending_1",
              customer_email: params.customer_email,
              client_reference_id: params.client_reference_id,
              metadata: params.metadata,
            };
            sessionsByKey.set(options.idempotencyKey, session);
            return session;
          },
        },
      };
    }
  }

  globalThis.Deno = { env: { get: (name) => env.get(name) } };
  globalThis.__checkoutExactOnceHarness = {
    createClientFromRequest: () => base44,
    Stripe: FakeStripe,
    secrets: { get: () => "test-secret" },
  };

  try {
    const { default: checkoutHandler } = await importHandlerWithHarness(
      checkoutSource,
      "__checkoutExactOnceHarness",
    );
    const invoke = (origin) => checkoutHandler(new Request("https://function.test", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ origin }),
    }));

    const rejected = await invoke("https://rich-rank-pilot-flow.base44.app.evil.example");
    assert.equal(rejected.status, 403);
    assert.equal((await rejected.json()).code, "checkout_origin_not_allowed");
    assert.equal(accessCreateCount, 0);
    assert.equal(sessionCreateCalls.length, 0);

    env.set("BETA_CHECKOUT_ENABLED", "false");
    const paused = await invoke("https://rich-rank-pilot-flow.base44.app");
    assert.equal(paused.status, 503);
    assert.equal((await paused.json()).code, "checkout_paused");
    assert.equal(accessCreateCount, 0);
    assert.equal(sessionCreateCalls.length, 0);

    env.set("BETA_CHECKOUT_ENABLED", "true");
    env.set("BETA_COHORT_ALLOWED_USER_IDS", "user-2");
    const uninvited = await invoke("https://rich-rank-pilot-flow.base44.app");
    assert.equal(uninvited.status, 403);
    assert.equal((await uninvited.json()).code, "checkout_not_invited");
    assert.equal(accessCreateCount, 0);
    assert.equal(sessionCreateCalls.length, 0);

    env.set("BETA_COHORT_ALLOWED_USER_IDS", "user-1");
    const preprovisionedAccess = accessRecord;
    accessRecord = null;
    const notPreprovisioned = await invoke("https://rich-rank-pilot-flow.base44.app");
    assert.equal(notPreprovisioned.status, 409);
    assert.equal((await notPreprovisioned.json()).code, "checkout_access_not_preprovisioned");
    assert.equal(accessCreateCount, 0);
    assert.equal(sessionCreateCalls.length, 0);
    accessRecord = preprovisionedAccess;

    synchronizePendingWrites = true;
    const concurrentResponses = await Promise.all([
      invoke("https://rich-rank-pilot-flow.base44.app"),
      invoke("https://rich-rank-pilot-flow.base44.app"),
    ]);
    const concurrentBodies = await Promise.all(concurrentResponses.map((response) => response.json()));
    assert.deepEqual(concurrentResponses.map((response) => response.status), [200, 200]);
    assert.deepEqual(
      concurrentBodies.map((body) => body.url),
      ["https://checkout.stripe.test/cs_pending_1", "https://checkout.stripe.test/cs_pending_1"],
    );
    assert.equal(accessRecord.stripe_checkout_session_id, "cs_pending_1");
    assert.equal(sessionsByKey.size, 1, "concurrent checkout calls must converge on one Stripe session");
    assert.equal(new Set(sessionCreateCalls.map((call) => call.options.idempotencyKey)).size, 1);

    synchronizePendingWrites = false;
    const retry = await invoke("https://rich-rank-pilot-flow.base44.app");
    const retryBody = await retry.json();
    assert.equal(retry.status, 200);
    assert.deepEqual(retryBody, {
      url: "https://checkout.stripe.test/cs_pending_1",
      reused: true,
    });
    assert.equal(accessCreateCount, 0);
    assert.equal(sessionCreateCalls.length, 2, "the retry must reuse the stored session without a third create call");
  } finally {
    delete globalThis.__checkoutExactOnceHarness;
    if (priorDeno === undefined) delete globalThis.Deno;
    else globalThis.Deno = priorDeno;
  }
});

test("paid webhooks are idempotent in either historical session order", () => {
  const pendingBoundToSecond = {
    access_status: "pending",
    has_full_access: false,
    stripe_checkout_session_id: "cs_second",
  };
  assert.equal(
    webhookHelpers.classifyPaidDelivery(pendingBoundToSecond, "cs_first"),
    "grant",
    "the first legitimate paid session must not be rejected because a retry overwrote the pending binding",
  );
  assert.equal(
    webhookHelpers.classifyPaidDelivery({ ...pendingBoundToSecond, access_status: "revoked" }, "cs_first"),
    "revoked",
    "a historical payment event must not reactivate an explicitly revoked entitlement",
  );

  const grantedFromFirst = {
    access_status: "active",
    has_full_access: true,
    stripe_checkout_session_id: "cs_first",
  };
  assert.equal(webhookHelpers.classifyPaidDelivery(grantedFromFirst, "cs_first"), "replay");
  assert.equal(
    webhookHelpers.classifyPaidDelivery(grantedFromFirst, "cs_second"),
    "already_active",
    "a later paid session is acknowledged without issuing another entitlement",
  );

  const grantedFromSecond = {
    ...grantedFromFirst,
    stripe_checkout_session_id: "cs_second",
  };
  assert.equal(webhookHelpers.classifyPaidDelivery(grantedFromSecond, "cs_first"), "already_active");
  assert.doesNotMatch(webhookSource, /checkout_access_binding_mismatch/);
  assert.match(webhookSource, /duplicate_payment: true/);
});

test("the webhook handler grants once for either delivery order", async () => {
  let accessRecord;
  let updates;
  const base44 = {
    asServiceRole: {
      entities: {
        Access: {
          async filter(query) {
            const matchesOwner = query.owner_user_id && query.owner_user_id === accessRecord.owner_user_id;
            const matchesEmail = query.user_email && query.user_email === accessRecord.user_email;
            return matchesOwner || matchesEmail ? [{ ...accessRecord }] : [];
          },
          async update(id, fields) {
            assert.equal(id, accessRecord.id);
            updates.push(fields);
            accessRecord = { ...accessRecord, ...fields };
            return { ...accessRecord };
          },
        },
      },
    },
  };
  class FakeStripe {
    constructor() {
      this.webhooks = {
        constructEventAsync: async (body) => JSON.parse(body),
      };
    }
  }
  globalThis.__stripeWebhookExactOnceHarness = {
    createClientFromRequest: () => base44,
    Stripe: FakeStripe,
    secrets: { get: () => "test-secret" },
    console: { error: () => {}, warn: () => {} },
  };

  try {
    const { default: webhookHandler } = await importHandlerWithHarness(
      webhookSource,
      "__stripeWebhookExactOnceHarness",
    );
    const eventFor = (sessionId, sequence) => ({
      id: `evt_${sequence}_${sessionId}`,
      type: "checkout.session.completed",
      created: 1_786_732_000 + sequence,
      data: {
        object: {
          id: sessionId,
          payment_status: "paid",
          amount_total: 5000,
          currency: "usd",
          customer_email: "paid@example.com",
          client_reference_id: "user-1",
          payment_intent: `pi_${sessionId}`,
          metadata: {
            base44_app_id: "6a498732ec779dfaaeab0e53",
            plan_id: "standard150_lifetime",
            access_id: "access-1",
            owner_user_id: "user-1",
            user_email: "paid@example.com",
          },
        },
      },
    });
    const deliver = async (sessionId, sequence) => {
      const response = await webhookHandler(new Request("https://function.test", {
        method: "POST",
        headers: { "stripe-signature": "test-signature" },
        body: JSON.stringify(eventFor(sessionId, sequence)),
      }));
      return { status: response.status, body: await response.json() };
    };

    for (const order of [["cs_first", "cs_second"], ["cs_second", "cs_first"]]) {
      accessRecord = {
        id: "access-1",
        owner_user_id: "user-1",
        user_email: "paid@example.com",
        access_status: "pending",
        has_full_access: false,
        stripe_checkout_session_id: "cs_second",
      };
      updates = [];

      const granted = await deliver(order[0], 1);
      assert.equal(granted.status, 200);
      assert.deepEqual(granted.body, { received: true });
      assert.equal(accessRecord.stripe_checkout_session_id, order[0]);

      const replay = await deliver(order[0], 1);
      assert.deepEqual(replay.body, { received: true, replay: true });

      const laterPaidSession = await deliver(order[1], 2);
      assert.deepEqual(laterPaidSession.body, { received: true, duplicate_payment: true });
      assert.equal(accessRecord.stripe_checkout_session_id, order[0]);
      assert.equal(updates.length, 1, "only the first paid delivery may grant the entitlement");
    }
  } finally {
    delete globalThis.__stripeWebhookExactOnceHarness;
  }
});
