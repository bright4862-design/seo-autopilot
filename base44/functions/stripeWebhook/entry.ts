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

    if (event.type === "checkout.session.completed") {
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
      if (
        access.has_full_access === true &&
        access.access_status === "active" &&
        String(access.stripe_checkout_session_id || "") === String(session.id)
      ) {
        return Response.json({ received: true, replay: true });
      }

      if (
        access.has_full_access === true ||
        (access.stripe_checkout_session_id && String(access.stripe_checkout_session_id) !== String(session.id))
      ) {
        throw new Error("checkout_access_binding_mismatch");
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
