import { createClientFromRequest } from "npm:@base44/sdk@0.8.40";
import Stripe from "npm:stripe@17.5.0";
import { secrets } from "base44:runtime";

// Grants full access when a checkout session completes.
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
      const email = String(session?.metadata?.user_email || session?.customer_email || "").toLowerCase();
      if (email) {
        const existing = await base44.asServiceRole.entities.Access.filter({ user_email: email });
        const paidAt = new Date().toISOString();
        if (existing.length > 0) {
          await base44.asServiceRole.entities.Access.update(existing[0].id, { has_full_access: true, paid_at: paidAt });
        } else {
          await base44.asServiceRole.entities.Access.create({ user_email: email, scans_used: 0, has_full_access: true, paid_at: paidAt });
        }
      } else {
        console.warn("stripeWebhook: no email on completed session", session?.id);
      }
    }

    return Response.json({ received: true });
  } catch (error) {
    console.error("stripeWebhook failed", error);
    return Response.json({ error: error.message }, { status: 400 });
  }
}