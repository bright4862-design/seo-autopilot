import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  EXTENDED500_AMOUNT,
  EXTENDED500_APP_ID,
  EXTENDED500_PLAN_ID,
  EXTENDED500_STRIPE_PRICE_ID,
  EXTENDED500_STRIPE_PRODUCT_ID,
  assertPaidExtended500Session,
  verifyStripeWebhook,
} from "../../src/lib/extended500Payments.js";
import { createExtended500Checkout } from "../../base44/functions/createExtended500CheckoutV1/handler.js";
import { processExtended500StripeWebhook } from "../../base44/functions/extended500StripeWebhookV1/handler.js";

const USER = { id: "owner_one", email: "Owner@Example.com" };
const EMAIL = "owner@example.com";
const ORIGIN = "https://getfixlist.com";
const CLOCK = Date.parse("2026-10-29T15:00:00.000Z");
const WEBHOOK_SECRET = "whsec_fixture_extended500_endpoint";
const CHECKOUT_ON = { EXTENDED500_CHECKOUT_ENABLED: "true", EXTENDED500_CHECKOUT_GENERATION: "acceptance-20261029" };
const WEBHOOK_ON = { EXTENDED500_WEBHOOK_ENABLED: "true", EXTENDED500_STRIPE_WEBHOOK_SECRET: WEBHOOK_SECRET };
const secretsFrom = (values) => (name) => values[name] || "";

// In-memory Base44 Access entity with the same filter/create/update/delete surface.
function fakeEntities(initialRows = [], { failFilter = false } = {}) {
  const rows = initialRows.map((row) => ({ ...row }));
  const calls = { create: [], update: [], delete: [], filter: 0 };
  let next = rows.length + 1;
  const matches = (row, where) => Object.entries(where).every(([key, value]) => String(row[key] ?? "") === String(value));
  return {
    rows,
    calls,
    Access: {
      async filter(where) {
        calls.filter += 1;
        if (failFilter) throw new Error("base44_unavailable");
        return rows.filter((row) => matches(row, where)).map((row) => ({ ...row }));
      },
      async create(data) {
        calls.create.push(data);
        const row = { id: `access_${next++}`, ...data };
        rows.push(row);
        return { ...row };
      },
      async update(id, patch) {
        calls.update.push({ id, patch });
        const row = rows.find((candidate) => candidate.id === id);
        if (!row) throw new Error("not_found");
        Object.assign(row, patch);
        return { ...row };
      },
      async delete(id) {
        calls.delete.push(id);
        const index = rows.findIndex((candidate) => candidate.id === id);
        if (index >= 0) rows.splice(index, 1);
      },
    },
  };
}

const extendedLineItems = (overrides = {}) => ({
  data: [{
    quantity: 1,
    price: { id: EXTENDED500_STRIPE_PRICE_ID, product: EXTENDED500_STRIPE_PRODUCT_ID, unit_amount: EXTENDED500_AMOUNT, currency: "usd", type: "one_time", ...overrides },
  }],
});

// Stripe Checkout Sessions API fake: idempotent create, retrieve, expire.
function fakeStripe(sessions = {}) {
  const store = { ...sessions };
  const calls = { create: [], retrieve: [], expire: [] };
  const byKey = new Map();
  let next = Object.keys(store).length + 1;
  return {
    store,
    calls,
    checkout: {
      sessions: {
        async create(params, options) {
          calls.create.push({ params, options });
          if (byKey.has(options?.idempotencyKey)) return structuredClone(store[byKey.get(options.idempotencyKey)]);
          const id = `cs_test_${next++}`;
          store[id] = {
            id, object: "checkout.session", url: `https://checkout.stripe.test/${id}`, status: "open", payment_status: "unpaid",
            mode: params.mode, amount_total: EXTENDED500_AMOUNT, amount_subtotal: EXTENDED500_AMOUNT, currency: "usd",
            customer_email: params.customer_email, client_reference_id: params.client_reference_id,
            metadata: { ...params.metadata },
            line_items: { data: params.line_items.map((item) => ({ quantity: item.quantity, price: { id: item.price, product: item.price === EXTENDED500_STRIPE_PRICE_ID ? EXTENDED500_STRIPE_PRODUCT_ID : "prod_other", unit_amount: EXTENDED500_AMOUNT, currency: "usd", type: "one_time" } })) },
            payment_intent: null,
          };
          byKey.set(options?.idempotencyKey, id);
          return structuredClone(store[id]);
        },
        async retrieve(id) {
          calls.retrieve.push(id);
          if (!store[id]) throw new Error("no_such_session");
          return structuredClone(store[id]);
        },
        async expire(id) {
          calls.expire.push(id);
          store[id].status = "expired";
          return structuredClone(store[id]);
        },
      },
    },
  };
}

function paySession(stripe, id, { paymentStatus = "paid", paymentIntent = "pi_test_1" } = {}) {
  Object.assign(stripe.store[id], { status: "complete", payment_status: paymentStatus, payment_intent: paymentIntent });
  return structuredClone(stripe.store[id]);
}

function pendingExtendedRow(overrides = {}) {
  return {
    id: "access_ext", user_email: EMAIL, owner_user_id: USER.id, access_status: "pending",
    plan_id: EXTENDED500_PLAN_ID, grant_source: "checkout_pending", app_id: EXTENDED500_APP_ID, has_full_access: false,
    ...overrides,
  };
}

function paidSession(overrides = {}) {
  return {
    id: "cs_test_paid", object: "checkout.session", status: "complete", payment_status: "paid", mode: "payment",
    amount_total: EXTENDED500_AMOUNT, amount_subtotal: EXTENDED500_AMOUNT, currency: "usd",
    customer_email: EMAIL, client_reference_id: USER.id, payment_intent: "pi_test_paid",
    metadata: { base44_app_id: EXTENDED500_APP_ID, plan_id: EXTENDED500_PLAN_ID, owner_user_id: USER.id, user_email: EMAIL, access_id: "access_ext" },
    line_items: extendedLineItems(),
    ...overrides,
  };
}

function signedDelivery(event, { secret = WEBHOOK_SECRET, timestamp = Math.floor(CLOCK / 1000) } = {}) {
  const rawBody = JSON.stringify(event);
  const signature = createHmac("sha256", secret).update(`${timestamp}.${rawBody}`).digest("hex");
  return { rawBody, signatureHeader: `t=${timestamp},v1=${signature}` };
}

function sessionEvent(type, session, id = "evt_test_1") {
  return { id, type, created: Math.floor(CLOCK / 1000) - 5, data: { object: session } };
}

const checkout = (entities, stripe, values = CHECKOUT_ON, user = USER, body = { origin: ORIGIN }) =>
  createExtended500Checkout({ body, user, entities, stripe, secret: secretsFrom(values), nowMs: CLOCK });

const webhook = (delivery, entities, stripe, values = WEBHOOK_ON) =>
  processExtended500StripeWebhook({ ...delivery, entities, stripe, secret: secretsFrom(values), nowMs: CLOCK });

// ---------------------------------------------------------------- checkout

test("checkout is disabled by default and touches neither Base44 nor Stripe", async () => {
  for (const values of [{}, { EXTENDED500_CHECKOUT_ENABLED: "TRUE" }, { EXTENDED500_CHECKOUT_ENABLED: "true" }, { EXTENDED500_CHECKOUT_ENABLED: "true", EXTENDED500_CHECKOUT_GENERATION: "../bad" }]) {
    const entities = fakeEntities();
    const stripe = fakeStripe();
    const result = await checkout(entities, stripe, values);
    assert.equal(result.status, 503);
    assert.match(result.payload.code, /^extended500_checkout_(disabled|configuration_invalid)$/);
    assert.equal(entities.calls.filter, 0);
    assert.equal(stripe.calls.create.length, 0);
  }
});

test("checkout requires an authenticated owner, a strict body and an allowed https origin", async () => {
  const entities = fakeEntities();
  const stripe = fakeStripe();
  assert.equal((await checkout(entities, stripe, CHECKOUT_ON, { id: "", email: EMAIL })).status, 401);
  assert.equal((await checkout(entities, stripe, CHECKOUT_ON, USER, { origin: ORIGIN, plan_id: "extended500_lifetime" })).status, 400);
  for (const origin of ["https://evil.example", "http://getfixlist.com", "https://getfixlist.com/billing", ""]) {
    assert.equal((await checkout(entities, stripe, CHECKOUT_ON, USER, { origin })).status, 403, origin);
  }
  assert.equal(entities.calls.create.length + stripe.calls.create.length, 0);
});

test("a first checkout creates one pending Extended 500 row and one exact $49 session", async () => {
  const entities = fakeEntities();
  const stripe = fakeStripe();
  const result = await checkout(entities, stripe);
  assert.equal(result.status, 200);
  assert.match(result.payload.url, /^https:\/\/checkout\.stripe\.test\//);

  assert.equal(entities.rows.length, 1);
  const row = entities.rows[0];
  assert.deepEqual(
    { plan_id: row.plan_id, access_status: row.access_status, has_full_access: row.has_full_access, grant_source: row.grant_source, user_email: row.user_email },
    { plan_id: EXTENDED500_PLAN_ID, access_status: "pending", has_full_access: false, grant_source: "checkout_pending", user_email: EMAIL },
  );
  assert.equal(stripe.calls.create.length, 1);
  const { params, options } = stripe.calls.create[0];
  assert.equal(params.mode, "payment");
  assert.deepEqual(params.line_items, [{ price: EXTENDED500_STRIPE_PRICE_ID, quantity: 1 }]);
  assert.equal(params.client_reference_id, USER.id);
  assert.equal(params.customer_email, EMAIL);
  assert.deepEqual(params.metadata, { base44_app_id: EXTENDED500_APP_ID, owner_user_id: USER.id, user_email: EMAIL, plan_id: EXTENDED500_PLAN_ID, access_id: row.id });
  assert.deepEqual(params.payment_intent_data.metadata, params.metadata);
  assert.equal(params.allow_promotion_codes, undefined, "no discount path can change the $49 amount");
  assert.match(options.idempotencyKey, /^extended500-checkout:6a498732ec779dfaaeab0e53:[0-9a-f]{64}$/);
  assert.equal(row.stripe_checkout_session_id, Object.keys(stripe.store)[0]);
});

test("retrying checkout reuses the open session instead of creating another", async () => {
  const entities = fakeEntities();
  const stripe = fakeStripe();
  const first = await checkout(entities, stripe);
  const second = await checkout(entities, stripe);
  assert.equal(second.status, 200);
  assert.equal(second.payload.reused, true);
  assert.equal(second.payload.url, first.payload.url);
  assert.equal(stripe.calls.create.length, 1);
  assert.equal(entities.rows.length, 1);
});

test("concurrent first checkouts collapse safe duplicate pending rows to one", async () => {
  const entities = fakeEntities([pendingExtendedRow({ id: "access_a" }), pendingExtendedRow({ id: "access_b" })]);
  const stripe = fakeStripe();
  const result = await checkout(entities, stripe);
  assert.equal(result.status, 200);
  assert.deepEqual(entities.rows.map((row) => row.id), ["access_a"]);
  assert.deepEqual(entities.calls.delete, ["access_b"]);
});

test("duplicate rows that are not all safe pending rows need support, never a guess", async () => {
  const entities = fakeEntities([pendingExtendedRow({ id: "access_a" }), pendingExtendedRow({ id: "access_b", access_status: "active", has_full_access: true })]);
  const result = await checkout(entities, fakeStripe());
  assert.equal(result.status, 409);
  assert.equal(result.payload.code, "duplicate_access");
  assert.equal(entities.calls.delete.length, 0);
});

test("active or revoked Extended 500 access never opens a new checkout", async () => {
  for (const [row, code] of [
    [pendingExtendedRow({ access_status: "active", has_full_access: true, grant_source: "stripe_checkout" }), "already_active"],
    [pendingExtendedRow({ access_status: "revoked" }), "access_conflict"],
  ]) {
    const stripe = fakeStripe();
    const result = await checkout(fakeEntities([row]), stripe);
    assert.equal(result.status, 409);
    assert.equal(result.payload.code, code);
    assert.equal(stripe.calls.create.length + stripe.calls.retrieve.length, 0);
  }
});

test("Standard 150 buyers keep their rights and are not charged $49 again", async () => {
  const standard = { id: "access_150", user_email: EMAIL, owner_user_id: USER.id, plan_id: "standard150_lifetime", access_status: "active", has_full_access: true, grant_source: "stripe_checkout", app_id: EXTENDED500_APP_ID, stripe_checkout_session_id: "cs_150" };
  const entities = fakeEntities([standard]);
  const stripe = fakeStripe();
  const result = await checkout(entities, stripe);
  assert.equal(result.status, 409);
  assert.equal(result.payload.code, "standard150_upgrade_policy_pending");
  assert.deepEqual(entities.rows, [standard], "the Standard 150 row is untouched and no Extended 500 row is created");
  assert.equal(stripe.calls.create.length, 0);

  const inFlight = fakeEntities([{ ...standard, access_status: "pending", has_full_access: false, grant_source: "checkout_pending" }]);
  const blocked = await checkout(inFlight, fakeStripe());
  assert.equal(blocked.payload.code, "standard150_checkout_pending");
});

test("a paid session whose webhook was lost is reconciled from Stripe, not from the client", async () => {
  const entities = fakeEntities([pendingExtendedRow({ stripe_checkout_session_id: "cs_test_paid" })]);
  const stripe = fakeStripe({ cs_test_paid: paidSession() });
  const result = await checkout(entities, stripe);
  assert.equal(result.status, 200);
  assert.equal(result.payload.already_active, true);
  assert.equal(result.payload.reconciled, true);
  assert.equal(entities.rows[0].access_status, "active");
  assert.equal(entities.rows[0].has_full_access, true);
  assert.equal(entities.rows[0].stripe_payment_intent_id, "pi_test_paid");
  assert.equal(stripe.calls.create.length, 0);
});

test("a delayed payment that may still settle blocks a second session", async () => {
  const entities = fakeEntities([pendingExtendedRow({ stripe_checkout_session_id: "cs_test_paid" })]);
  const stripe = fakeStripe({ cs_test_paid: paidSession({ payment_status: "unpaid", payment_intent: "pi_processing" }) });
  const result = await checkout(entities, stripe);
  assert.equal(result.status, 409);
  assert.equal(result.payload.code, "checkout_payment_processing");
  assert.equal(entities.rows[0].access_status, "pending", "a pending checkout is never treated as payment");
  assert.equal(stripe.calls.create.length, 0);
});

test("an open session at the wrong price is expired and replaced at the Extended 500 price", async () => {
  const wrong = paidSession({ status: "open", payment_status: "unpaid", url: "https://checkout.stripe.test/old", line_items: extendedLineItems({ id: "price_old" }) });
  const entities = fakeEntities([pendingExtendedRow({ stripe_checkout_session_id: "cs_test_paid" })]);
  const stripe = fakeStripe({ cs_test_paid: wrong });
  const result = await checkout(entities, stripe);
  assert.equal(result.status, 200);
  assert.deepEqual(stripe.calls.expire, ["cs_test_paid"]);
  assert.equal(stripe.calls.create[0].params.line_items[0].price, EXTENDED500_STRIPE_PRICE_ID);
  assert.notEqual(entities.rows[0].stripe_checkout_session_id, "cs_test_paid");
});

test("an expired session gets a fresh idempotency key; a foreign-bound session is refused", async () => {
  const entities = fakeEntities([pendingExtendedRow({ stripe_checkout_session_id: "cs_test_paid" })]);
  const stripe = fakeStripe({ cs_test_paid: paidSession({ status: "expired", payment_status: "unpaid" }) });
  assert.equal((await checkout(entities, stripe)).status, 200);
  assert.equal(stripe.calls.create.length, 1);

  const foreign = fakeEntities([pendingExtendedRow({ stripe_checkout_session_id: "cs_test_paid" })]);
  const foreignStripe = fakeStripe({ cs_test_paid: paidSession({ status: "open", url: "https://x", metadata: { ...paidSession().metadata, access_id: "access_other" } }) });
  const refused = await checkout(foreign, foreignStripe);
  assert.equal(refused.status, 409);
  assert.equal(refused.payload.code, "checkout_session_conflict");
  assert.equal(foreignStripe.calls.create.length, 0);
});

test("checkout dependency failures return a generic error", async () => {
  const result = await checkout(fakeEntities([], { failFilter: true }), fakeStripe());
  assert.equal(result.status, 500);
  assert.deepEqual(Object.keys(result.payload).sort(), ["code", "error", "success"]);
});

// ---------------------------------------------------------------- webhook

test("the webhook is disabled by default and requires a dedicated whsec_ endpoint secret", async () => {
  const delivery = signedDelivery(sessionEvent("checkout.session.completed", paidSession()));
  for (const values of [{}, { EXTENDED500_WEBHOOK_ENABLED: "true" }, { EXTENDED500_WEBHOOK_ENABLED: "true", EXTENDED500_STRIPE_WEBHOOK_SECRET: "not-a-secret" }]) {
    const entities = fakeEntities([pendingExtendedRow({ stripe_checkout_session_id: "cs_test_paid" })]);
    const stripe = fakeStripe({ cs_test_paid: paidSession() });
    const result = await webhook(delivery, entities, stripe, values);
    assert.equal(result.status, 503);
    assert.equal(entities.calls.filter + stripe.calls.retrieve.length, 0);
  }
});

test("Stripe signatures are verified exactly, including tolerance and multiple v1 values", async () => {
  const event = sessionEvent("checkout.session.completed", paidSession());
  const good = signedDelivery(event);
  const now = Math.floor(CLOCK / 1000);
  assert.equal((await verifyStripeWebhook(good.rawBody, good.signatureHeader, WEBHOOK_SECRET, now)).ok, true);
  const rotated = `${good.signatureHeader.split(",")[0]},v1=${"0".repeat(64)},${good.signatureHeader.split(",")[1]}`;
  assert.equal((await verifyStripeWebhook(good.rawBody, rotated, WEBHOOK_SECRET, now)).ok, true);

  for (const [delivery, reason] of [
    [{ ...good, signatureHeader: "" }, "signature_missing"],
    [{ ...good, signatureHeader: "t=123" }, "signature_malformed"],
    [signedDelivery(event, { secret: "whsec_other_endpoint_secret" }), "signature_mismatch"],
    [signedDelivery(event, { timestamp: now - 301 }), "signature_timestamp_outside_tolerance"],
    [{ ...good, rawBody: good.rawBody.replace('"paid"', '"PAID"') }, "signature_mismatch"],
  ]) {
    const entities = fakeEntities([pendingExtendedRow({ stripe_checkout_session_id: "cs_test_paid" })]);
    const result = await webhook(delivery, entities, fakeStripe({ cs_test_paid: paidSession() }));
    assert.equal(result.status, 400, reason);
    assert.equal(result.payload.code, reason);
    assert.equal(entities.calls.update.length, 0);
  }
});

test("a verified paid completion grants exactly one Extended 500 entitlement", async () => {
  const standard = { id: "access_150", user_email: EMAIL, owner_user_id: USER.id, plan_id: "standard150_lifetime", access_status: "revoked", has_full_access: false, app_id: EXTENDED500_APP_ID };
  const entities = fakeEntities([pendingExtendedRow({ stripe_checkout_session_id: "cs_test_paid" }), standard]);
  const stripe = fakeStripe({ cs_test_paid: paidSession() });
  const result = await webhook(signedDelivery(sessionEvent("checkout.session.completed", paidSession())), entities, stripe);
  assert.equal(result.status, 200);
  assert.equal(result.payload.outcome, "granted");
  const granted = entities.rows.find((row) => row.id === "access_ext");
  assert.equal(granted.access_status, "active");
  assert.equal(granted.has_full_access, true);
  assert.equal(granted.grant_source, "stripe_checkout");
  assert.equal(granted.plan_id, EXTENDED500_PLAN_ID);
  assert.equal(granted.stripe_payment_intent_id, "pi_test_paid");
  assert.equal(granted.stripe_event_id, "evt_test_1");
  assert.equal(granted.paid_at, new Date((Math.floor(CLOCK / 1000) - 5) * 1000).toISOString());
  assert.deepEqual(entities.rows.find((row) => row.id === "access_150"), standard, "Standard 150 rows are never written");
  assert.deepEqual(stripe.calls.retrieve, ["cs_test_paid"], "the session is re-read from Stripe before granting");
});

test("replayed and concurrent deliveries are idempotent", async () => {
  const entities = fakeEntities([pendingExtendedRow({ stripe_checkout_session_id: "cs_test_paid" })]);
  const stripe = fakeStripe({ cs_test_paid: paidSession() });
  const completed = signedDelivery(sessionEvent("checkout.session.completed", paidSession(), "evt_completed"));
  const succeeded = signedDelivery(sessionEvent("checkout.session.async_payment_succeeded", paidSession(), "evt_async"));
  const outcomes = await Promise.all([webhook(completed, entities, stripe), webhook(succeeded, entities, stripe), webhook(completed, entities, stripe)]);
  assert.ok(outcomes.every((result) => result.status === 200));
  const after = await webhook(completed, entities, stripe);
  assert.equal(after.payload.outcome, "replay");
  assert.equal(entities.rows.length, 1);
  assert.equal(entities.rows[0].access_status, "active");
});

test("an unpaid completion is not payment; async success grants and async failure frees a retry", async () => {
  const entities = fakeEntities([pendingExtendedRow({ stripe_checkout_session_id: "cs_test_paid" })]);
  const stripe = fakeStripe({ cs_test_paid: paidSession({ payment_status: "unpaid", payment_intent: "pi_async" }) });
  const pending = await webhook(signedDelivery(sessionEvent("checkout.session.completed", paidSession({ payment_status: "unpaid" }))), entities, stripe);
  assert.equal(pending.payload.outcome, "awaiting_payment");
  assert.equal(entities.rows[0].access_status, "pending");
  assert.equal(entities.calls.update.length, 0);

  const failed = await webhook(signedDelivery(sessionEvent("checkout.session.async_payment_failed", paidSession({ payment_status: "unpaid" }), "evt_failed")), entities, stripe);
  assert.equal(failed.payload.outcome, "released_for_retry");
  assert.equal(entities.rows[0].stripe_checkout_session_id, "");
  assert.equal(entities.rows[0].has_full_access, false);

  const retry = fakeEntities([pendingExtendedRow({ stripe_checkout_session_id: "cs_test_paid" })]);
  const settled = fakeStripe({ cs_test_paid: paidSession() });
  const success = await webhook(signedDelivery(sessionEvent("checkout.session.async_payment_succeeded", paidSession(), "evt_ok")), retry, settled);
  assert.equal(success.payload.outcome, "granted");
});

test("the Stripe API read, not the event body, decides payment", async () => {
  const entities = fakeEntities([pendingExtendedRow({ stripe_checkout_session_id: "cs_test_paid" })]);
  const stripe = fakeStripe({ cs_test_paid: paidSession({ payment_status: "unpaid" }) });
  const result = await webhook(signedDelivery(sessionEvent("checkout.session.completed", paidSession())), entities, stripe);
  assert.equal(result.payload.outcome, "awaiting_payment");
  assert.equal(entities.rows[0].has_full_access, false);
});

test("Standard 150 and other plans are acknowledged but never processed here", async () => {
  const standardSession = paidSession({ metadata: { ...paidSession().metadata, plan_id: "standard150_lifetime" } });
  const entities = fakeEntities([pendingExtendedRow({ stripe_checkout_session_id: "cs_test_paid" })]);
  const stripe = fakeStripe({ cs_test_paid: paidSession() });
  const result = await webhook(signedDelivery(sessionEvent("checkout.session.completed", standardSession)), entities, stripe);
  assert.equal(result.status, 200);
  assert.deepEqual(result.payload, { received: true, outcome: "ignored", reason: "foreign_plan" });
  assert.equal(stripe.calls.retrieve.length + entities.calls.filter, 0);
});

test("any mismatch in price, product, amount, currency, quantity, mode, app or identity is rejected, never granted", async () => {
  const meta = paidSession().metadata;
  for (const [label, session] of [
    ["price", paidSession({ line_items: extendedLineItems({ id: "price_1UFXgX4DcTLS57kiIag23r8C" }) })],
    ["product", paidSession({ line_items: extendedLineItems({ product: "prod_VG3oLdyyJw2NvM" }) })],
    ["unit amount", paidSession({ line_items: extendedLineItems({ unit_amount: 100 }) })],
    ["recurring price", paidSession({ line_items: extendedLineItems({ type: "recurring" }) })],
    ["quantity", paidSession({ line_items: { data: [{ ...extendedLineItems().data[0], quantity: 2 }] } })],
    ["two line items", paidSession({ line_items: { data: [...extendedLineItems().data, ...extendedLineItems().data] } })],
    ["discounted total", paidSession({ amount_total: 100 })],
    ["currency", paidSession({ currency: "eur" })],
    ["mode", paidSession({ mode: "subscription" })],
    ["app", paidSession({ metadata: { ...meta, base44_app_id: "other_app" } })],
    ["client reference", paidSession({ client_reference_id: "owner_two" })],
    ["access binding", paidSession({ metadata: { ...meta, access_id: "access_other" } })],
    ["foreign owner", paidSession({ metadata: { ...meta, owner_user_id: "owner_two" }, client_reference_id: "owner_two" })],
  ]) {
    const entities = fakeEntities([pendingExtendedRow({ stripe_checkout_session_id: "cs_test_paid" })]);
    const stripe = fakeStripe({ cs_test_paid: session });
    const result = await webhook(signedDelivery(sessionEvent("checkout.session.completed", paidSession())), entities, stripe);
    assert.equal(result.status, 200, label);
    assert.equal(result.payload.outcome, "rejected", label);
    assert.equal(result.alert, true, label);
    assert.equal(entities.calls.update.length, 0, label);
    assert.equal(entities.rows[0].has_full_access, false, label);
  }
});

test("a second paid session never grants twice; revoked and duplicate rows are refused", async () => {
  const active = pendingExtendedRow({ access_status: "active", has_full_access: true, grant_source: "stripe_checkout", stripe_checkout_session_id: "cs_first", paid_at: "2026-10-20T00:00:00Z" });
  const entities = fakeEntities([active]);
  const duplicate = await webhook(signedDelivery(sessionEvent("checkout.session.completed", paidSession())), entities, fakeStripe({ cs_test_paid: paidSession() }));
  assert.equal(duplicate.payload.outcome, "duplicate_payment");
  assert.equal(duplicate.alert, true);
  assert.equal(entities.calls.update.length, 0);

  const revoked = fakeEntities([pendingExtendedRow({ access_status: "revoked", stripe_checkout_session_id: "cs_test_paid" })]);
  assert.equal((await webhook(signedDelivery(sessionEvent("checkout.session.completed", paidSession())), revoked, fakeStripe({ cs_test_paid: paidSession() }))).payload.reason, "access_revoked");

  const twoRows = fakeEntities([pendingExtendedRow({ stripe_checkout_session_id: "cs_test_paid" }), pendingExtendedRow({ id: "access_dup" })]);
  const conflict = await webhook(signedDelivery(sessionEvent("checkout.session.completed", paidSession())), twoRows, fakeStripe({ cs_test_paid: paidSession() }));
  assert.equal(conflict.payload.reason, "duplicate_extended500_access");
  assert.equal(twoRows.calls.update.length, 0);
});

test("a full refund or lost dispute revokes only the matching Extended 500 payment", async () => {
  const granted = pendingExtendedRow({ access_status: "active", has_full_access: true, grant_source: "stripe_checkout", stripe_checkout_session_id: "cs_test_paid", stripe_payment_intent_id: "pi_test_paid" });
  const standard = { id: "access_150", user_email: EMAIL, owner_user_id: USER.id, plan_id: "standard150_lifetime", access_status: "active", has_full_access: true, stripe_payment_intent_id: "pi_150" };

  const entities = fakeEntities([granted, standard]);
  const partial = await webhook(signedDelivery({ id: "evt_r1", type: "charge.refunded", created: 1, data: { object: { payment_intent: "pi_test_paid", amount: 4900, amount_refunded: 1000, refunded: false } } }), entities, fakeStripe());
  assert.equal(partial.payload.outcome, "manual_review");
  assert.equal(entities.rows[0].access_status, "active");

  const ignored = await webhook(signedDelivery({ id: "evt_r2", type: "charge.refunded", created: 1, data: { object: { payment_intent: "pi_150", amount: 4900, amount_refunded: 4900, refunded: true } } }), entities, fakeStripe());
  assert.equal(ignored.payload.reason, "not_extended500_payment");
  assert.equal(entities.rows[1].access_status, "active", "Standard 150 rights are never revoked here");

  const full = await webhook(signedDelivery({ id: "evt_r3", type: "charge.refunded", created: 1, data: { object: { payment_intent: "pi_test_paid", amount: 4900, amount_refunded: 4900, refunded: true } } }), entities, fakeStripe());
  assert.equal(full.payload.outcome, "revoked");
  assert.equal(entities.rows[0].access_status, "revoked");
  assert.equal(entities.rows[0].has_full_access, false);
  const again = await webhook(signedDelivery({ id: "evt_r3", type: "charge.refunded", created: 1, data: { object: { payment_intent: "pi_test_paid", amount: 4900, amount_refunded: 4900, refunded: true } } }), entities, fakeStripe());
  assert.equal(again.payload.outcome, "replay");

  const disputed = fakeEntities([{ ...granted }]);
  assert.equal((await webhook(signedDelivery({ id: "evt_d1", type: "charge.dispute.created", created: 1, data: { object: { payment_intent: "pi_test_paid", status: "needs_response" } } }), disputed, fakeStripe())).payload.outcome, "manual_review");
  assert.equal(disputed.rows[0].access_status, "active");
  assert.equal((await webhook(signedDelivery({ id: "evt_d2", type: "charge.dispute.closed", created: 1, data: { object: { payment_intent: "pi_test_paid", status: "won" } } }), disputed, fakeStripe())).payload.outcome, "ignored");
  assert.equal((await webhook(signedDelivery({ id: "evt_d3", type: "charge.dispute.closed", created: 1, data: { object: { payment_intent: "pi_test_paid", status: "lost" } } }), disputed, fakeStripe())).payload.outcome, "revoked");
});

test("transient Base44 failures are retryable 500s with no grant; unrelated events are acknowledged", async () => {
  const failing = fakeEntities([], { failFilter: true });
  const result = await webhook(signedDelivery(sessionEvent("checkout.session.completed", paidSession())), failing, fakeStripe({ cs_test_paid: paidSession() }));
  assert.equal(result.status, 500);
  const other = await webhook(signedDelivery({ id: "evt_x", type: "customer.created", created: 1, data: { object: {} } }), fakeEntities(), fakeStripe());
  assert.deepEqual(other.payload, { received: true, outcome: "ignored", reason: "unhandled_event_type" });
});

test("end to end: checkout, payment, webhook grant, no second sale, refund revocation", async () => {
  const entities = fakeEntities();
  const stripe = fakeStripe();
  const started = await checkout(entities, stripe);
  assert.equal(started.status, 200);
  const sessionId = entities.rows[0].stripe_checkout_session_id;
  const paid = paySession(stripe, sessionId, { paymentIntent: "pi_e2e" });

  const grant = await webhook(signedDelivery(sessionEvent("checkout.session.completed", paid, "evt_e2e")), entities, stripe);
  assert.equal(grant.payload.outcome, "granted");
  assert.equal((await checkout(entities, stripe)).payload.code, "already_active");
  assert.equal(stripe.calls.create.length, 1, "one customer, one session, one charge");

  const refund = await webhook(signedDelivery({ id: "evt_refund", type: "charge.refunded", created: 1, data: { object: { payment_intent: "pi_e2e", amount: 4900, amount_refunded: 4900, refunded: true } } }), entities, stripe);
  assert.equal(refund.payload.outcome, "revoked");
  assert.equal((await checkout(entities, stripe)).payload.code, "access_conflict");
});

test("the paid-session validator never accepts a pending, open or Standard 150 session", () => {
  assert.equal(assertPaidExtended500Session(paidSession()).ok, true);
  for (const session of [
    paidSession({ payment_status: "unpaid" }),
    paidSession({ payment_status: "no_payment_required" }),
    paidSession({ status: "open" }),
    paidSession({ metadata: { ...paidSession().metadata, plan_id: "standard150_lifetime" } }),
    paidSession({ payment_intent: null }),
    null,
  ]) {
    assert.equal(assertPaidExtended500Session(session).ok, false);
  }
});

// ---------------------------------------------------------------- contracts

test("both packages ship a byte-identical copy of the canonical payment core", () => {
  const canonical = readFileSync("src/lib/extended500Payments.js", "utf8");
  for (const pkg of ["createExtended500CheckoutV1", "extended500StripeWebhookV1"]) {
    assert.equal(readFileSync(`base44/functions/${pkg}/extended500Payments.js`, "utf8"), canonical, pkg);
  }
});

test("the Extended 500 payment packages are unrouted, outside the release manifest and unused by the app", () => {
  const routes = readFileSync("data/base44-function-routes.json", "utf8");
  const manifest = readFileSync("scripts/generate_release_contracts.mjs", "utf8");
  for (const pkg of ["createExtended500CheckoutV1", "extended500StripeWebhookV1"]) {
    assert.doesNotMatch(routes, new RegExp(pkg));
    assert.doesNotMatch(manifest, new RegExp(pkg));
  }
  const billing = readFileSync("src/pages/Billing.jsx", "utf8");
  const access = readFileSync("src/lib/access.js", "utf8");
  assert.doesNotMatch(billing + access, /Extended500Checkout|extended500_lifetime/);
});

test("the live Standard 150 checkout and webhook still pin the Standard 150 product", () => {
  const checkoutSource = readFileSync("base44/functions/createAccessCheckout/entry.ts", "utf8");
  const webhookSource = readFileSync("base44/functions/stripeWebhook/entry.ts", "utf8");
  assert.match(checkoutSource, /const PLAN_ID = "standard150_lifetime";/);
  assert.match(checkoutSource, /const STRIPE_PRICE_ID = "price_1UFXgX4DcTLS57kiIag23r8C";/);
  assert.match(webhookSource, /const PLAN_ID = "standard150_lifetime";/);
  assert.match(webhookSource, /const EXPECTED_AMOUNT = 4900;/);
  assert.doesNotMatch(checkoutSource + webhookSource, /extended500|price_1UVtse4DcTLS57kiivKSCXKC/);
});
