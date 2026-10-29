// Extended 500 $49 lifetime checkout candidate. NOT routed and NOT part of the
// Standard 150 release manifest. Inert unless the Base44 secrets
// EXTENDED500_CHECKOUT_ENABLED="true" and EXTENDED500_CHECKOUT_GENERATION are set.
import { createClientFromRequest } from "npm:@base44/sdk@0.8.40";
import Stripe from "npm:stripe@17.5.0";
import { secrets } from "base44:runtime";
import { createExtended500Checkout } from "./handler.js";

function readPrivate(name: string): string {
  try { return String(secrets.get(name) || ""); }
  catch { return ""; }
}

export default async function (req: Request): Promise<Response> {
  if (req.method !== "POST") {
    return Response.json({ success: false, code: "method_not_allowed" }, { status: 405 });
  }
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me().catch(() => null);
    if (!user?.id || !user?.email) {
      return Response.json({ success: false, code: "unauthorized" }, { status: 401 });
    }
    const raw = await req.text();
    if (raw.length > 2048) {
      return Response.json({ success: false, code: "request_too_large" }, { status: 413 });
    }
    let body;
    try { body = JSON.parse(raw || "{}"); }
    catch { return Response.json({ success: false, code: "invalid_json" }, { status: 400 }); }

    // Built lazily, once, so a disabled checkout never reads Stripe config.
    let client: Stripe | null = null;
    const stripe = {
      get checkout() {
        client ??= new Stripe(readPrivate("STRIPE_SECRET_KEY"));
        return client.checkout;
      },
    };
    const outcome = await createExtended500Checkout({
      body,
      user,
      entities: base44.asServiceRole.entities,
      stripe,
      secret: readPrivate,
    });
    return Response.json(outcome.payload, { status: outcome.status });
  } catch {
    return Response.json({ success: false, code: "checkout_failed" }, { status: 500 });
  }
}
