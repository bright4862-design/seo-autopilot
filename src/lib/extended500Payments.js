// Extended 500 $49 lifetime payment core. Canonical source; byte-identical
// copies ship inside base44/functions/createExtended500CheckoutV1/ and
// base44/functions/extended500StripeWebhookV1/ (a test enforces this).
//
// Pure and dependency-injected: no imports, no network, no globals besides
// WebCrypto. Callers pass server-owned Base44 service entities, a Stripe client
// and a secret reader. NOT routed, NOT imported by Standard 150, and inert
// unless the separately configured Base44 secrets enable it.
//
// Invariants:
// - Access is granted only from a verified, paid Stripe Checkout Session that
//   is re-read from the Stripe API and matches the exact Extended 500 price,
//   product, amount, currency, plan and app.
// - A pending or unpaid checkout is never treated as payment.
// - One owner has at most one Extended 500 Access row. Standard 150 rows are
//   never read for authority, written, converted or revoked here.
// - Nothing here creates a charge; a second paid session is reported for
//   manual refund, never granted twice.

export const EXTENDED500_APP_ID = "6a498732ec779dfaaeab0e53";
export const EXTENDED500_PLAN_ID = "extended500_lifetime";
export const EXTENDED500_STRIPE_PRODUCT_ID = "prod_VWxozdmSEe3iqm";
export const EXTENDED500_STRIPE_PRICE_ID = "price_1UVtse4DcTLS57kiivKSCXKC";
export const EXTENDED500_AMOUNT = 4900;
export const EXTENDED500_CURRENCY = "usd";
export const STANDARD150_PLAN_ID = "standard150_lifetime";
export const STRIPE_SIGNATURE_TOLERANCE_SECONDS = 300;

const IDENTIFIER = /^[A-Za-z0-9_-]{3,128}$/;
const STRIPE_ID = /^[A-Za-z0-9_]{3,255}$/;
const GENERATION = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;
const encoder = new TextEncoder();

export function normalizeEmail(value) {
  return String(value || "").trim().toLowerCase();
}

const text = (value) => String(value ?? "").trim();
const isId = (value) => IDENTIFIER.test(text(value));
const isStripeId = (value) => STRIPE_ID.test(text(value));
const stripeRef = (value) => (typeof value === "string" ? value : text(value?.id));

function uniqueRecords(records) {
  return Array.from(new Map((records || []).filter(Boolean).map((record) => [String(record.id), record])).values());
}

/** Every Access row bound to this owner by id or email, de-duplicated. */
export async function findOwnerAccessRows(entities, userId, email) {
  const [byUser, byEmail] = await Promise.all([
    userId ? entities.Access.filter({ owner_user_id: userId }) : [],
    email ? entities.Access.filter({ user_email: email }) : [],
  ]);
  return uniqueRecords([...(byUser || []), ...(byEmail || [])]);
}

export function extended500Rows(rows) {
  return (rows || []).filter((row) => text(row?.plan_id) === EXTENDED500_PLAN_ID);
}

function ownsRow(row, userId, email) {
  return text(row?.owner_user_id) === userId && normalizeEmail(row?.user_email) === email;
}

/** Fail-closed checkout switch. Disabled unless BOTH secrets are set. */
export function extended500CheckoutPolicy(secret) {
  if (typeof secret !== "function") return { ok: false, code: "extended500_checkout_disabled" };
  const enabled = text(secret("EXTENDED500_CHECKOUT_ENABLED"));
  if (enabled !== "true") return { ok: false, code: "extended500_checkout_disabled" };
  // No default generation: the release acceptance names one explicitly, and it
  // seeds the Stripe idempotency key so each acceptance gets fresh sessions.
  const generation = text(secret("EXTENDED500_CHECKOUT_GENERATION"));
  if (!GENERATION.test(generation)) return { ok: false, code: "extended500_checkout_configuration_invalid" };
  return { ok: true, generation };
}

export function extended500WebhookPolicy(secret) {
  if (typeof secret !== "function") return { ok: false, code: "extended500_webhook_disabled" };
  if (text(secret("EXTENDED500_WEBHOOK_ENABLED")) !== "true") return { ok: false, code: "extended500_webhook_disabled" };
  const signingSecret = String(secret("EXTENDED500_STRIPE_WEBHOOK_SECRET") || "");
  if (!signingSecret.startsWith("whsec_") || signingSecret.length < 16) {
    return { ok: false, code: "extended500_webhook_configuration_invalid" };
  }
  return { ok: true, signingSecret };
}

function hex(bytes) {
  return Array.from(new Uint8Array(bytes), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function constantTimeEqual(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let diff = 0;
  for (let index = 0; index < a.length; index += 1) diff |= a.charCodeAt(index) ^ b.charCodeAt(index);
  return diff === 0;
}

/**
 * Stripe webhook signature check (Stripe-Signature `t=...,v1=...`): HMAC-SHA256
 * of `${t}.${rawBody}` with the endpoint secret, any v1 may match, and the
 * timestamp must be within the tolerance. Returns the parsed event or a reason.
 */
export async function verifyStripeWebhook(rawBody, header, signingSecret, nowSeconds, tolerance = STRIPE_SIGNATURE_TOLERANCE_SECONDS) {
  if (typeof rawBody !== "string" || typeof header !== "string" || !header || typeof signingSecret !== "string" || !signingSecret) {
    return { ok: false, reason: "signature_missing" };
  }
  let timestamp = null;
  const signatures = [];
  for (const part of header.split(",")) {
    const [key, ...rest] = part.trim().split("=");
    const value = rest.join("=");
    if (key === "t" && /^\d{1,12}$/.test(value)) timestamp = Number(value);
    if (key === "v1" && /^[0-9a-f]{64}$/.test(value)) signatures.push(value);
  }
  if (timestamp === null || signatures.length === 0) return { ok: false, reason: "signature_malformed" };
  if (!Number.isFinite(nowSeconds) || Math.abs(nowSeconds - timestamp) > tolerance) {
    return { ok: false, reason: "signature_timestamp_outside_tolerance" };
  }
  const key = await crypto.subtle.importKey("raw", encoder.encode(signingSecret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const expected = hex(await crypto.subtle.sign("HMAC", key, encoder.encode(`${timestamp}.${rawBody}`)));
  if (!signatures.some((signature) => constantTimeEqual(signature, expected))) return { ok: false, reason: "signature_mismatch" };
  try {
    const event = JSON.parse(rawBody);
    if (!event || typeof event !== "object" || !isStripeId(event.id) || typeof event.type !== "string") {
      return { ok: false, reason: "event_malformed" };
    }
    return { ok: true, event };
  } catch {
    return { ok: false, reason: "event_malformed" };
  }
}

/** Stable per owner + plan + acceptance generation + previous session. */
export async function extended500CheckoutIdempotencyKey(access, generation) {
  const userId = text(access?.owner_user_id);
  if (!isId(userId) || !GENERATION.test(text(generation))) throw new Error("checkout_configuration_invalid");
  const previous = text(access?.stripe_checkout_session_id) || "initial";
  const basis = `${EXTENDED500_APP_ID}\n${EXTENDED500_PLAN_ID}\n${userId}\n${text(generation)}\n${previous}`;
  const digest = await crypto.subtle.digest("SHA-256", encoder.encode(basis));
  return `extended500-checkout:${EXTENDED500_APP_ID}:${hex(digest)}`;
}

/** The exact single Extended 500 line item, from an expanded session. */
export function sessionUsesExtended500Price(session) {
  const items = Array.isArray(session?.line_items?.data) ? session.line_items.data : [];
  if (items.length !== 1) return false;
  const item = items[0] || {};
  const price = item.price && typeof item.price === "object" ? item.price : { id: stripeRef(item.price) };
  return text(price.id) === EXTENDED500_STRIPE_PRICE_ID
    && (price.product === undefined || stripeRef(price.product) === EXTENDED500_STRIPE_PRODUCT_ID)
    && (price.unit_amount === undefined || Number(price.unit_amount) === EXTENDED500_AMOUNT)
    && (price.currency === undefined || text(price.currency).toLowerCase() === EXTENDED500_CURRENCY)
    && (price.type === undefined || price.type === "one_time")
    && Number(item.quantity) === 1;
}

/** Plan claimed by session metadata; used only to route, never as authority. */
export function sessionPlan(session) {
  return text(session?.metadata?.plan_id);
}

/**
 * Validates a session re-read from the Stripe API (line items expanded). Any
 * mismatch is a rejection, never a grant.
 */
export function assertPaidExtended500Session(session) {
  const metadata = session?.metadata || {};
  if (!session || typeof session !== "object") return { ok: false, reason: "session_missing" };
  if (session.object !== undefined && session.object !== "checkout.session") return { ok: false, reason: "session_object_invalid" };
  if (session.mode !== "payment") return { ok: false, reason: "session_mode_invalid" };
  if (session.status !== "complete") return { ok: false, reason: "session_not_complete" };
  if (session.payment_status !== "paid") return { ok: false, reason: "session_not_paid" };
  if (Number(session.amount_total) !== EXTENDED500_AMOUNT || Number(session.amount_subtotal ?? EXTENDED500_AMOUNT) !== EXTENDED500_AMOUNT) {
    return { ok: false, reason: "amount_mismatch" };
  }
  if (text(session.currency).toLowerCase() !== EXTENDED500_CURRENCY) return { ok: false, reason: "currency_mismatch" };
  if (!sessionUsesExtended500Price(session)) return { ok: false, reason: "price_mismatch" };
  if (text(metadata.base44_app_id) !== EXTENDED500_APP_ID) return { ok: false, reason: "app_mismatch" };
  if (text(metadata.plan_id) !== EXTENDED500_PLAN_ID) return { ok: false, reason: "plan_mismatch" };
  const userId = text(metadata.owner_user_id);
  const email = normalizeEmail(metadata.user_email || session.customer_email);
  const accessId = text(metadata.access_id);
  if (!isId(userId) || !email || !isId(accessId) || text(session.client_reference_id) !== userId) {
    return { ok: false, reason: "identity_missing" };
  }
  if (!isStripeId(session.id) || !isStripeId(stripeRef(session.payment_intent))) return { ok: false, reason: "stripe_reference_missing" };
  return { ok: true, userId, email, accessId, sessionId: text(session.id), paymentIntentId: stripeRef(session.payment_intent) };
}

function grantedRowMatches(row, userId, email, sessionId) {
  return ownsRow(row, userId, email)
    && text(row?.plan_id) === EXTENDED500_PLAN_ID
    && text(row?.app_id) === EXTENDED500_APP_ID
    && text(row?.access_status) === "active"
    && row?.has_full_access === true
    && text(row?.grant_source) === "stripe_checkout"
    && text(row?.stripe_checkout_session_id) === sessionId;
}

/**
 * Grants Extended 500 for a verified paid session. Idempotent: a replay of the
 * same session reports `replay`. Never touches non-Extended 500 rows.
 * `paidAtMs` comes from the Stripe event (or the reconciling read time).
 */
export async function fulfillExtended500Session({ session, entities, paidAtMs, eventId = "" }) {
  const paid = assertPaidExtended500Session(session);
  if (!paid.ok) return { outcome: "rejected", reason: paid.reason, granted: false };
  const { userId, email, accessId, sessionId, paymentIntentId } = paid;

  const rows = extended500Rows(await findOwnerAccessRows(entities, userId, email));
  if (rows.length !== 1 || text(rows[0]?.id) !== accessId) {
    return { outcome: "rejected", reason: rows.length > 1 ? "duplicate_extended500_access" : "access_binding_mismatch", granted: false };
  }
  const access = rows[0];
  if (!ownsRow(access, userId, email) || text(access.app_id) !== EXTENDED500_APP_ID) {
    return { outcome: "rejected", reason: "access_identity_mismatch", granted: false };
  }
  if (text(access.access_status) === "revoked") return { outcome: "rejected", reason: "access_revoked", granted: false };
  if (text(access.access_status) === "active" || access.has_full_access === true) {
    if (grantedRowMatches(access, userId, email, sessionId)) return { outcome: "replay", granted: false };
    // A second paid session for an owner who already has Extended 500. Never
    // grant twice; surface it for a manual refund.
    return { outcome: "duplicate_payment", reason: "already_active_other_session", granted: false, sessionId, paymentIntentId };
  }
  if (text(access.stripe_checkout_session_id) !== sessionId) {
    return { outcome: "rejected", reason: "session_not_bound_to_access", granted: false };
  }
  if (!Number.isFinite(paidAtMs) || paidAtMs <= 0) return { outcome: "rejected", reason: "paid_time_invalid", granted: false };

  await entities.Access.update(access.id, {
    user_email: email,
    owner_user_id: userId,
    access_status: "active",
    plan_id: EXTENDED500_PLAN_ID,
    grant_source: "stripe_checkout",
    app_id: EXTENDED500_APP_ID,
    has_full_access: true,
    paid_at: new Date(paidAtMs).toISOString(),
    stripe_checkout_session_id: sessionId,
    stripe_payment_intent_id: paymentIntentId,
    stripe_event_id: text(eventId),
  });

  // Authoritative re-read: exactly one granted Extended 500 row must result.
  const after = extended500Rows(await findOwnerAccessRows(entities, userId, email));
  if (after.length !== 1 || !grantedRowMatches(after[0], userId, email, sessionId)) {
    return { outcome: "conflict_after_grant", reason: "post_grant_verification_failed", granted: true };
  }
  return { outcome: "granted", granted: true, accessId: text(access.id) };
}

/**
 * Async payment failure: the pending row keeps no claim on the failed session,
 * so the customer can start a new checkout. Never grants, never revokes.
 */
export async function releaseFailedExtended500Session({ session, entities }) {
  const metadata = session?.metadata || {};
  const userId = text(metadata.owner_user_id);
  const email = normalizeEmail(metadata.user_email || session?.customer_email);
  if (text(metadata.plan_id) !== EXTENDED500_PLAN_ID || text(metadata.base44_app_id) !== EXTENDED500_APP_ID) {
    return { outcome: "ignored", reason: "not_extended500_session" };
  }
  if (!isId(userId) || !email || !isStripeId(session?.id)) return { outcome: "ignored", reason: "identity_missing" };
  const rows = extended500Rows(await findOwnerAccessRows(entities, userId, email));
  const pending = rows.find((row) => text(row.stripe_checkout_session_id) === text(session.id));
  if (!pending) return { outcome: "ignored", reason: "no_bound_pending_access" };
  if (text(pending.access_status) !== "pending" || pending.has_full_access === true || !ownsRow(pending, userId, email)) {
    return { outcome: "ignored", reason: "access_not_pending" };
  }
  await entities.Access.update(pending.id, { stripe_checkout_session_id: "" });
  return { outcome: "released_for_retry" };
}

/**
 * Full refund or lost dispute revokes only the Extended 500 row whose payment
 * intent matches. Standard 150 payments are ignored. Partial refunds and open
 * disputes are left for manual review.
 */
export async function revokeExtended500ForPayment({ paymentIntentId, entities, reason }) {
  if (!isStripeId(paymentIntentId)) return { outcome: "ignored", reason: "payment_intent_missing" };
  const rows = extended500Rows(await entities.Access.filter({ stripe_payment_intent_id: paymentIntentId }))
    .filter((row) => text(row.stripe_payment_intent_id) === paymentIntentId);
  if (rows.length === 0) return { outcome: "ignored", reason: "not_extended500_payment" };
  if (rows.length > 1) return { outcome: "manual_review", reason: "duplicate_payment_intent_binding" };
  const access = rows[0];
  if (text(access.access_status) === "revoked" && access.has_full_access !== true) return { outcome: "replay" };
  await entities.Access.update(access.id, { access_status: "revoked", has_full_access: false });
  return { outcome: "revoked", reason, accessId: text(access.id) };
}
