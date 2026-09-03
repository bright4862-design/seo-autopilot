import { createClientFromRequest } from "npm:@base44/sdk@0.8.40";
import Stripe from "npm:stripe@17.5.0";
import { secrets } from "base44:runtime";
import { FUNCTION_BUILD_ID } from "./generatedBuildId.js";
const BASE44_RUNTIME_ACTIVATION_ID = "checkout-prod-reactivation-20260903-v1";

const APP_ID = "6a498732ec779dfaaeab0e53";
const PLAN_ID = "standard150_lifetime";
const MAX_BETA_CUSTOMERS = 25;
const PRODUCTION_APP_ORIGIN = "https://rich-rank-pilot-flow.base44.app";
const PRICE_DATA = {
  currency: "usd",
  unit_amount: 5000,
  product: "prod_V0lLfb5lSwxOxh",
};
const LOCAL_DEVELOPMENT_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);
const BETA_USER_ID_PATTERN = /^[A-Za-z0-9_-]{3,128}$/;
const BETA_GENERATION_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;

function normalizeEmail(value) {
  return String(value || "").trim().toLowerCase();
}

function uniqueRecords(records) {
  return Array.from(new Map((records || []).map((record) => [record.id, record])).values());
}

function parseOrigin(value) {
  const raw = String(value || "").trim();
  if (!raw) return null;

  try {
    const parsed = new URL(raw);
    if (parsed.username || parsed.password || parsed.pathname !== "/" || parsed.search || parsed.hash) return null;
    if (parsed.protocol !== "https:" && parsed.protocol !== "http:") return null;
    return parsed;
  } catch {
    return null;
  }
}

function configuredCheckoutOrigins() {
  const configured = String(Deno.env.get("CHECKOUT_RETURN_ORIGINS") || "")
    .split(",")
    .map((value) => parseOrigin(value))
    .filter((origin) => origin?.protocol === "https:")
    .map((origin) => origin.origin);
  return new Set([PRODUCTION_APP_ORIGIN, ...configured]);
}

function resolveCheckoutReturnOrigin(value) {
  const requested = parseOrigin(value);
  if (!requested) return "";

  if (configuredCheckoutOrigins().has(requested.origin)) return requested.origin;

  const allowLocalhost = String(Deno.env.get("CHECKOUT_ALLOW_LOCALHOST") || "")
    .trim()
    .toLowerCase() === "true";
  if (allowLocalhost && LOCAL_DEVELOPMENT_HOSTS.has(requested.hostname)) return requested.origin;
  return "";
}

function betaCheckoutPolicy() {
  const enabled = String(Deno.env.get("BETA_CHECKOUT_ENABLED") || "")
    .trim()
    .toLowerCase() === "true";
  if (!enabled) {
    return { ok: false, code: "checkout_paused", allowedUserIds: [], generation: "" };
  }

  const generation = String(Deno.env.get("BETA_CHECKOUT_GENERATION") || "").trim();
  const allowedUserIds = Array.from(new Set(
    String(Deno.env.get("BETA_COHORT_ALLOWED_USER_IDS") || "")
      .split(/[\s,]+/)
      .map((value) => value.trim())
      .filter(Boolean),
  ));
  const valid = BETA_GENERATION_PATTERN.test(generation)
    && allowedUserIds.length > 0
    && allowedUserIds.length <= MAX_BETA_CUSTOMERS
    && allowedUserIds.every((userId) => BETA_USER_ID_PATTERN.test(userId));
  if (!valid) {
    return {
      ok: false,
      code: "checkout_configuration_invalid",
      allowedUserIds: [],
      generation: "",
    };
  }
  return { ok: true, code: "", allowedUserIds, generation };
}

async function checkoutIdempotencyKey(access, generation) {
  const userId = String(access?.owner_user_id || "").trim();
  const checkoutGeneration = String(generation || "").trim();
  if (!BETA_USER_ID_PATTERN.test(userId) || !BETA_GENERATION_PATTERN.test(checkoutGeneration)) {
    throw new Error("checkout_configuration_invalid");
  }
  const previousSessionId = String(access?.stripe_checkout_session_id || "").trim() || "initial";
  const basis = `${APP_ID}\n${userId}\n${checkoutGeneration}\n${previousSessionId}`;
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(basis));
  const fingerprint = Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
  return `access-checkout:${APP_ID}:${fingerprint}`;
}

function classifyExistingCheckoutSession(session) {
  if (session?.payment_status === "paid" || session?.status === "complete") return "payment_processing";
  if (session?.status === "open" && session?.url) return "reusable";
  if (session?.status === "expired") return "renew";
  return "blocked";
}

function assertSessionBelongsToAccess(session, access, userId, email) {
  const metadata = session?.metadata || {};
  if (
    String(metadata.base44_app_id || "") !== APP_ID ||
    String(metadata.plan_id || "") !== PLAN_ID ||
    String(metadata.access_id || "") !== String(access?.id || "") ||
    String(metadata.owner_user_id || "") !== userId ||
    normalizeEmail(metadata.user_email || session?.customer_email) !== email ||
    String(session?.client_reference_id || "") !== userId
  ) {
    throw new Error("checkout_access_binding_mismatch");
  }
}

async function findOwnedAccess(base44, userId, email) {
  const [byUser, byEmail] = await Promise.all([
    userId ? base44.asServiceRole.entities.Access.filter({ owner_user_id: userId }) : [],
    email ? base44.asServiceRole.entities.Access.filter({ user_email: email }) : [],
  ]);
  return uniqueRecords([...(byUser || []), ...(byEmail || [])]);
}

function checkoutAccessStateResponse(access) {
  const status = String(access?.access_status || "").trim();
  if (status === "revoked") {
    return Response.json(
      { error: "Your access record needs support before checkout can continue.", code: "access_conflict" },
      { status: 409 },
    );
  }
  if (status === "active" || access?.has_full_access === true) {
    return Response.json({ error: "Full access is already active.", code: "already_active" }, { status: 409 });
  }
  return null;
}

export default async function (req) {
  if (req.method !== "POST") {
    return Response.json({ success: false, error_code: "method_not_allowed", error: "Use POST to create checkout.", build_id: FUNCTION_BUILD_ID, runtime_activation_id: BASE44_RUNTIME_ACTIVATION_ID }, { status: 405 });
  }

  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();
    const userId = String(user?.id || "").trim();
    const email = normalizeEmail(user?.email);
    if (!user || !userId || !email) {
      return Response.json({ error: "Unauthorized" }, { status: 401 });
    }

    const body = await req.json().catch(() => ({}));
    const origin = resolveCheckoutReturnOrigin(body?.origin);
    if (!origin) {
      return Response.json(
        { error: "Checkout return URL is not configured.", code: "checkout_origin_not_allowed" },
        { status: 403 },
      );
    }

    // Paid beta admission is fail-closed. The allowlist itself is the hard seat
    // cap, so no concurrent checkout can allocate a 26th place. Operators must
    // pre-provision exactly one Access row for each invited ID before enabling
    // this generation; checkout never creates entitlement rows.
    const policy = betaCheckoutPolicy();
    if (!policy.ok) {
      const configurationInvalid = policy.code === "checkout_configuration_invalid";
      return Response.json(
        {
          error: configurationInvalid
            ? "Checkout is not configured for this beta cohort."
            : "Checkout is temporarily paused.",
          code: policy.code,
        },
        { status: 503 },
      );
    }
    if (!policy.allowedUserIds.includes(userId)) {
      return Response.json(
        { error: "This paid beta cohort is currently invite-only.", code: "checkout_not_invited" },
        { status: 403 },
      );
    }

    let rows = await findOwnedAccess(base44, userId, email);
    if (rows.length > 1) {
      return Response.json(
        { error: "Your access record needs support before checkout can continue.", code: "duplicate_access" },
        { status: 409 },
      );
    }

    let access = rows[0] || null;
    if (!access) {
      return Response.json(
        {
          error: "Your beta access invitation is not ready yet.",
          code: "checkout_access_not_preprovisioned",
        },
        { status: 409 },
      );
    }
    if (
      String(access.owner_user_id || "").trim() !== userId
      || normalizeEmail(access.user_email) !== email
    ) {
      return Response.json(
        { error: "Your access record needs support before checkout can continue.", code: "access_conflict" },
        { status: 409 },
      );
    }
    const initialStateResponse = checkoutAccessStateResponse(access);
    if (initialStateResponse) return initialStateResponse;

    rows = await findOwnedAccess(base44, userId, email);
    if (rows.length !== 1 || rows[0]?.id !== access?.id) {
      return Response.json(
        { error: "Checkout could not establish a unique access record.", code: "access_conflict" },
        { status: 409 },
      );
    }
    access = rows[0];
    if (
      String(access.owner_user_id || "").trim() !== userId
      || normalizeEmail(access.user_email) !== email
    ) {
      return Response.json(
        { error: "Your access record needs support before checkout can continue.", code: "access_conflict" },
        { status: 409 },
      );
    }
    const freshStateResponse = checkoutAccessStateResponse(access);
    if (freshStateResponse) return freshStateResponse;

    const stripe = new Stripe(secrets.get("STRIPE_SECRET_KEY"));
    const previousSessionId = String(access?.stripe_checkout_session_id || "").trim();
    if (previousSessionId) {
      const previousSession = await stripe.checkout.sessions.retrieve(previousSessionId);
      assertSessionBelongsToAccess(previousSession, access, userId, email);
      const previousSessionState = classifyExistingCheckoutSession(previousSession);

      if (previousSessionState === "reusable") {
        return Response.json({ url: previousSession.url, reused: true });
      }
      if (previousSessionState === "payment_processing") {
        return Response.json(
          { error: "Your payment is already being processed.", code: "checkout_payment_processing" },
          { status: 409 },
        );
      }
      if (previousSessionState !== "renew") {
        return Response.json(
          { error: "Your checkout needs support before it can continue.", code: "checkout_session_conflict" },
          { status: 409 },
        );
      }
    }

    const session = await stripe.checkout.sessions.create(
      {
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
      },
      { idempotencyKey: await checkoutIdempotencyKey(access, policy.generation) },
    );

    await base44.asServiceRole.entities.Access.update(access.id, {
      stripe_checkout_session_id: String(session.id),
    });

    return Response.json({ url: session.url });
  } catch (error) {
    console.error("createAccessCheckout failed", {
      name: String(error?.name || "checkout_error").slice(0, 80),
      code: String(error?.code || "checkout_failed").slice(0, 80),
    });
    return Response.json(
      { error: "Checkout is temporarily unavailable.", code: "checkout_failed" },
      { status: 500 },
    );
  }
}
