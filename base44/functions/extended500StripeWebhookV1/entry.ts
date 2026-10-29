// Extended 500 Stripe webhook candidate. NOT the Standard 150 stripeWebhook
// package, NOT routed and NOT in the release manifest. Inert unless the Base44
// secrets EXTENDED500_WEBHOOK_ENABLED="true" and a dedicated
// EXTENDED500_STRIPE_WEBHOOK_SECRET (whsec_...) are configured.
import { createClientFromRequest } from "npm:@base44/sdk@0.8.40";
import Stripe from "npm:stripe@17.5.0";
import { secrets } from "base44:runtime";
import { processExtended500StripeWebhook } from "./handler.js";

function readPrivate(name: string): string {
  try { return String(secrets.get(name) || ""); }
  catch { return ""; }
}

export default async function (req: Request): Promise<Response> {
  if (req.method !== "POST") {
    return Response.json({ received: false, code: "method_not_allowed" }, { status: 405 });
  }
  try {
    const base44 = createClientFromRequest(req);
    const rawBody = await req.text();
    if (rawBody.length > 262144) {
      return Response.json({ received: false, code: "payload_too_large" }, { status: 413 });
    }
    let client: Stripe | null = null;
    const stripe = {
      get checkout() {
        client ??= new Stripe(readPrivate("STRIPE_SECRET_KEY"));
        return client.checkout;
      },
    };
    const outcome = await processExtended500StripeWebhook({
      rawBody,
      signatureHeader: req.headers.get("stripe-signature") || "",
      entities: base44.asServiceRole.entities,
      stripe,
      secret: readPrivate,
    });
    if (outcome.alert) console.error("extended500StripeWebhook needs review", outcome.payload);
    return Response.json(outcome.payload, { status: outcome.status });
  } catch {
    return Response.json({ received: false, code: "extended500_webhook_retryable_failure" }, { status: 500 });
  }
}
