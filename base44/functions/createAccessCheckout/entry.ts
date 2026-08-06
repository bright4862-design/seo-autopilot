import { createClientFromRequest } from "npm:@base44/sdk@0.8.40";
import Stripe from "npm:stripe@17.5.0";
import { secrets } from "base44:runtime";

// One-time $75 full-access payment, defined inline on the checkout session.
const PRICE_DATA = {
  currency: "usd",
  unit_amount: 7500,
  product: "prod_V0lLfb5lSwxOxh",
};

export default async function (req) {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();
    if (!user) return Response.json({ error: "Unauthorized" }, { status: 401 });

    const body = await req.json().catch(() => ({}));
    const origin = String(body?.origin || "").replace(/\/+$/, "");
    if (!origin) return Response.json({ error: "Missing origin" }, { status: 400 });

    const stripe = new Stripe(secrets.get("STRIPE_SECRET_KEY"));
    const session = await stripe.checkout.sessions.create({
      mode: "payment",
      line_items: [{ price_data: PRICE_DATA, quantity: 1 }],
      customer_email: user.email,
      success_url: `${origin}/billing?paid=1`,
      cancel_url: `${origin}/billing`,
      metadata: {
        base44_app_id: Deno.env.get("BASE44_APP_ID"),
        user_email: String(user.email || "").toLowerCase(),
      },
    });

    return Response.json({ url: session.url });
  } catch (error) {
    console.error("createAccessCheckout failed", error);
    return Response.json({ error: error.message }, { status: 500 });
  }
}