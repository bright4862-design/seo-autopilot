import { createClientFromRequest } from "npm:@base44/sdk@0.8.40";
import Stripe from "npm:stripe@17.5.0";
import { secrets } from "base44:runtime";

const APP_ID = "6a498732ec779dfaaeab0e53";
const PLAN_ID = "standard150_lifetime";
const EXPECTED_AMOUNT = 5000;
const EXPECTED_CURRENCY = "usd";

function normalizeEmail(value) {
  return String(value || "").trim().toLowerCase();
}

function uniqueRecords(records) {
  return Array.from(new Map((records || []).map((record) => [record.id, record])).values());
}

async function findOwnedAccess(base44, userId, email) {
  const [byUser, byEmail] = await Promise.all([
    userId ? base44.asServiceRole.entities.Access.filter({ owner_user_id: userId }) : [],
    email ? base44.asServiceRole.entities.Access.filter({ user_email: email }) : [],
  ]);
  return uniqueRecords([...(byUser || []), ...(byEmail || [])]);
}

function assertPaidSession(session) {
  const metadata = session?.metadata || {};
  if (session?.payment_status !== "paid") throw new Error("checkout_not_paid");
  if (Number(session?.amount_total) !== EXPECTED_AMOUNT) throw new Error("checkout_amount_mismatch");
  if (String(session?.currency || "").toLowerCase() !== EXPECTED_CURRENCY) throw new Error("checkout_currency_mismatch");
  if (String(metadata.base44_app_id || "") !== APP_ID) throw new Error("checkout_app_mismatch");
  if (String(metadata.plan_id || "") !== PLAN_ID) throw new Error("checkout_plan_mismatch");
}

function classifyPaidDelivery(access, sessionId) {
  if (access?.access_status === "revoked") return "revoked";
  if (access?.has_full_access !== true || access?.access_status !== "active") return "grant";
  if (String(access?.stripe_checkout_session_id || "") === String(sessionId || "")) return "replay";
  return "already_active";
}

export default async function (req) {
  try {
    const base44 = createClientFromRequest(req);
    const stripe = new Stripe(secrets.get("STRIPE_SECRET_KEY"));
    const body = await req.text();
    const signature = req.headers.get("stripe-signature");

    const event = await stripe.webhooks.constructEventAsync(
      body,
      signature,
      secrets.get("STRIPE_WEBHOOK_SECRET"),
    );

    const isCheckoutCompleted = event.type === "checkout.session.completed";
    const isAsyncPaymentSucceeded = event.type === "checkout.session.async_payment_succeeded";

    if (isCheckoutCompleted && event.data.object?.payment_status !== "paid") {
      return Response.json({ received: true });
    }

    if (isCheckoutCompleted || isAsyncPaymentSucceeded) {
      const session = event.data.object;
      assertPaidSession(session);

      const metadata = session.metadata || {};
      const accessId = String(metadata.access_id || "");
      const userId = String(metadata.owner_user_id || "");
      const email = normalizeEmail(metadata.user_email || session.customer_email);
      if (!accessId || !userId || !email || String(session.client_reference_id || "") !== userId) {
        throw new Error("checkout_identity_missing");
      }

      const rows = await findOwnedAccess(base44, userId, email);
      if (rows.length !== 1 || String(rows[0]?.id || "") !== accessId) {
        throw new Error("checkout_access_conflict");
      }

      const access = rows[0];
      if (String(access.owner_user_id || "") !== userId || normalizeEmail(access.user_email) !== email) {
        throw new Error("checkout_access_identity_mismatch");
      }

      const delivery = classifyPaidDelivery(access, session.id);
      if (delivery === "revoked") throw new Error("checkout_access_revoked");
      if (delivery === "replay") {
        return Response.json({ received: true, replay: true });
      }
      if (delivery === "already_active") {
        console.warn("stripeWebhook received a paid session for an already-active access record", {
          access_id: String(access.id),
          active_session_id: String(access.stripe_checkout_session_id || ""),
          received_session_id: String(session.id || ""),
          event_id: String(event.id || ""),
        });
        return Response.json({ received: true, duplicate_payment: true });
      }

      await base44.asServiceRole.entities.Access.update(access.id, {
        user_email: email,
        owner_user_id: userId,
        access_status: "active",
        plan_id: PLAN_ID,
        grant_source: "stripe_checkout",
        app_id: APP_ID,
        has_full_access: true,
        paid_at: new Date(Number(event.created || 0) * 1000).toISOString(),
        stripe_checkout_session_id: String(session.id),
        stripe_payment_intent_id: String(session.payment_intent || ""),
        stripe_event_id: String(event.id || ""),
      });
    }

    return Response.json({ received: true });
  } catch (error) {
    console.error("stripeWebhook failed", error);
    return Response.json({ error: error.message }, { status: 400 });
  }
}
