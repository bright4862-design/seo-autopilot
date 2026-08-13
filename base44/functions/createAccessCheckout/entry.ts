import { createClientFromRequest } from "npm:@base44/sdk@0.8.40";
import Stripe from "npm:stripe@17.5.0";
import { secrets } from "base44:runtime";

const APP_ID = "6a498732ec779dfaaeab0e53";
const PLAN_ID = "standard150_lifetime";
const PRICE_DATA = {
  currency: "usd",
  unit_amount: 5000,
  product: "prod_V0lLfb5lSwxOxh",
};

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

export default async function (req) {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();
    const userId = String(user?.id || "").trim();
    const email = normalizeEmail(user?.email);
    if (!user || !userId || !email) {
      return Response.json({ error: "Unauthorized" }, { status: 401 });
    }

    const body = await req.json().catch(() => ({}));
    const origin = String(body?.origin || "").replace(/\/+$/, "");
    if (!origin) return Response.json({ error: "Missing origin" }, { status: 400 });

    let rows = await findOwnedAccess(base44, userId, email);
    if (rows.length > 1) {
      return Response.json(
        { error: "Your access record needs support before checkout can continue.", code: "duplicate_access" },
        { status: 409 },
      );
    }

    let access = rows[0] || null;
    if (access?.has_full_access === true && access?.access_status === "active") {
      return Response.json({ error: "Full access is already active.", code: "already_active" }, { status: 409 });
    }

    const pendingFields = {
      user_email: email,
      owner_user_id: userId,
      access_status: "pending",
      plan_id: PLAN_ID,
      grant_source: "stripe_checkout",
      app_id: APP_ID,
      has_full_access: false,
    };

    if (access) {
      access = await base44.asServiceRole.entities.Access.update(access.id, pendingFields);
    } else {
      access = await base44.asServiceRole.entities.Access.create(pendingFields);
    }

    rows = await findOwnedAccess(base44, userId, email);
    if (rows.length !== 1 || rows[0]?.id !== access?.id) {
      return Response.json(
        { error: "Checkout could not establish a unique access record.", code: "access_conflict" },
        { status: 409 },
      );
    }

    const stripe = new Stripe(secrets.get("STRIPE_SECRET_KEY"));
    const session = await stripe.checkout.sessions.create({
      mode: "payment",
      line_items: [{ price_data: PRICE_DATA, quantity: 1 }],
      customer_email: email,
      client_reference_id: userId,
      success_url: `${origin}/billing?paid=1`,
      cancel_url: `${origin}/billing`,
      metadata: {
        base44_app_id: APP_ID,
        owner_user_id: userId,
        user_email: email,
        plan_id: PLAN_ID,
        access_id: String(access.id),
      },
    });

    await base44.asServiceRole.entities.Access.update(access.id, {
      stripe_checkout_session_id: String(session.id),
    });

    return Response.json({ url: session.url });
  } catch (error) {
    console.error("createAccessCheckout failed", error);
    return Response.json({ error: error.message }, { status: 500 });
  }
}
