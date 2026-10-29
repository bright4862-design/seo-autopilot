// Extended 500 Stripe webhook. NOT the Standard 150 stripeWebhook package, NOT
// routed, and inert unless EXTENDED500_WEBHOOK_ENABLED is exactly "true" and a
// dedicated EXTENDED500_STRIPE_WEBHOOK_SECRET endpoint secret is configured.
//
// Response policy: a bad signature is 400; a transient Base44/Stripe failure is
// 500 so Stripe retries; every verified event is otherwise acknowledged with
// 200 and a bounded outcome, including rejections (which are alerted, never
// granted) and other plans' sessions (which this endpoint must ignore).
import {
  EXTENDED500_PLAN_ID,
  fulfillExtended500Session,
  releaseFailedExtended500Session,
  revokeExtended500ForPayment,
  sessionPlan,
  verifyStripeWebhook,
  extended500WebhookPolicy,
} from "./extended500Payments.js";

const SESSION_EVENTS = new Set([
  "checkout.session.completed",
  "checkout.session.async_payment_succeeded",
  "checkout.session.async_payment_failed",
]);
const ALERT_OUTCOMES = new Set(["rejected", "duplicate_payment", "conflict_after_grant", "manual_review"]);

const ack = (outcome, extra = {}) => ({
  status: 200,
  payload: { received: true, outcome, ...extra },
  alert: ALERT_OUTCOMES.has(outcome),
});
const text = (value) => String(value ?? "").trim();
const ref = (value) => (typeof value === "string" ? value : text(value?.id));

async function handleSessionEvent(event, { entities, stripe }) {
  const eventSession = event?.data?.object || {};
  // Route on the plan the session was created for; other plans belong to the
  // Standard 150 endpoint and must not be failed (or Stripe would retry them).
  if (sessionPlan(eventSession) !== EXTENDED500_PLAN_ID) return ack("ignored", { reason: "foreign_plan" });

  // The Stripe API read, not the event body, is the payment authority.
  const session = await stripe.checkout.sessions.retrieve(text(eventSession.id), { expand: ["line_items.data.price"] });
  if (text(session?.id) !== text(eventSession.id) || sessionPlan(session) !== EXTENDED500_PLAN_ID) {
    return ack("rejected", { reason: "session_reread_mismatch" });
  }

  if (event.type === "checkout.session.async_payment_failed") {
    if (session.payment_status === "paid") return ack("rejected", { reason: "failed_event_but_session_paid" });
    const released = await releaseFailedExtended500Session({ session, entities });
    return ack(released.outcome, released.reason ? { reason: released.reason } : {});
  }
  if (session.payment_status !== "paid") {
    // checkout.session.completed for a delayed payment method: not payment yet.
    return ack("awaiting_payment");
  }
  const result = await fulfillExtended500Session({
    session,
    entities,
    paidAtMs: Number(event.created) * 1000,
    eventId: text(event.id),
  });
  return ack(result.outcome, result.reason ? { reason: result.reason } : {});
}

async function handleRefund(event, { entities }) {
  const charge = event?.data?.object || {};
  const fullyRefunded = charge.refunded === true
    || (Number(charge.amount) > 0 && Number(charge.amount_refunded) >= Number(charge.amount));
  if (!fullyRefunded) return ack("manual_review", { reason: "partial_refund" });
  const result = await revokeExtended500ForPayment({ paymentIntentId: ref(charge.payment_intent), entities, reason: "refunded" });
  return ack(result.outcome, result.reason ? { reason: result.reason } : {});
}

async function handleDispute(event, { entities }) {
  const dispute = event?.data?.object || {};
  if (event.type === "charge.dispute.created") return ack("manual_review", { reason: "dispute_opened" });
  if (text(dispute.status) !== "lost") return ack("ignored", { reason: "dispute_not_lost" });
  const result = await revokeExtended500ForPayment({ paymentIntentId: ref(dispute.payment_intent), entities, reason: "dispute_lost" });
  return ack(result.outcome, result.reason ? { reason: result.reason } : {});
}

export async function processExtended500StripeWebhook({ rawBody, signatureHeader, entities, stripe, secret, nowMs = Date.now() }) {
  const policy = extended500WebhookPolicy(secret);
  if (!policy.ok) return { status: 503, payload: { received: false, code: policy.code }, alert: false };

  const verified = await verifyStripeWebhook(rawBody, signatureHeader, policy.signingSecret, Math.floor(nowMs / 1000));
  if (!verified.ok) return { status: 400, payload: { received: false, code: verified.reason }, alert: true };
  const event = verified.event;

  try {
    if (SESSION_EVENTS.has(event.type)) return await handleSessionEvent(event, { entities, stripe });
    if (event.type === "charge.refunded") return await handleRefund(event, { entities });
    if (event.type === "charge.dispute.created" || event.type === "charge.dispute.closed") return await handleDispute(event, { entities });
    return ack("ignored", { reason: "unhandled_event_type" });
  } catch {
    // Transient dependency failure: no grant was confirmed, so let Stripe retry.
    return { status: 500, payload: { received: false, code: "extended500_webhook_retryable_failure" }, alert: true };
  }
}
