// Extended 500 $49 lifetime checkout. NOT routed, NOT the Standard 150
// createAccessCheckout package, and inert unless EXTENDED500_CHECKOUT_ENABLED
// is exactly "true" AND an explicit EXTENDED500_CHECKOUT_GENERATION is set.
// Dependencies are injected so every branch is covered by Node tests.
import {
  EXTENDED500_APP_ID,
  EXTENDED500_PLAN_ID,
  EXTENDED500_STRIPE_PRICE_ID,
  STANDARD150_PLAN_ID,
  extended500CheckoutIdempotencyKey,
  extended500CheckoutPolicy,
  extended500Rows,
  findOwnerAccessRows,
  fulfillExtended500Session,
  normalizeEmail,
  sessionUsesExtended500Price,
} from "./extended500Payments.js";

const PRODUCTION_ORIGINS = ["https://rich-rank-pilot-flow.base44.app", "https://getfixlist.com", "https://www.getfixlist.com"];
const USER_ID = /^[A-Za-z0-9_-]{3,128}$/;
const BODY_KEYS = new Set(["origin"]);

const reply = (status, payload) => ({ status, payload });
const failure = (status, code, error) => reply(status, { success: false, code, error });
const text = (value) => String(value ?? "").trim();

function parseOrigin(value) {
  try {
    const parsed = new URL(text(value));
    if (parsed.protocol !== "https:" || parsed.username || parsed.password || parsed.pathname !== "/" || parsed.search || parsed.hash) return "";
    return parsed.origin;
  } catch {
    return "";
  }
}

function allowedOrigins(secret) {
  const configured = String(secret("EXTENDED500_CHECKOUT_RETURN_ORIGINS") || "")
    .split(",")
    .map(parseOrigin)
    .filter(Boolean);
  return new Set([...PRODUCTION_ORIGINS, ...configured]);
}

function ownsRow(row, userId, email) {
  return text(row?.owner_user_id) === userId && normalizeEmail(row?.user_email) === email;
}

function isSafePendingExtended500(row, userId, email) {
  return ownsRow(row, userId, email)
    && text(row.access_status) === "pending"
    && row.has_full_access !== true
    && text(row.plan_id) === EXTENDED500_PLAN_ID
    && text(row.app_id) === EXTENDED500_APP_ID
    && text(row.grant_source) === "checkout_pending"
    && !text(row.paid_at)
    && !text(row.stripe_payment_intent_id)
    && !text(row.stripe_event_id);
}

// Concurrent first checkouts can each create a pending row. Collapse them only
// when every row is a safe, unpaid pending Extended 500 row with at most one
// bound session; anything else needs support, never a guess.
async function reconcilePendingDuplicates(entities, rows, userId, email) {
  if (rows.length <= 1 || !rows.every((row) => isSafePendingExtended500(row, userId, email))) return rows;
  const withSession = rows.filter((row) => text(row.stripe_checkout_session_id));
  if (withSession.length > 1) return rows;
  const canonical = withSession[0] || [...rows].sort((a, b) => String(a.id).localeCompare(String(b.id)))[0];
  await Promise.all(rows.filter((row) => row.id !== canonical.id).map(async (row) => {
    try {
      await entities.Access.delete(row.id);
    } catch {
      // A concurrent request may have removed it; the re-read below decides.
    }
  }));
  return extended500Rows(await findOwnerAccessRows(entities, userId, email));
}

// Standard 150 buyers keep their purchased rights. Until the owner sets an
// upgrade policy they are not sold Extended 500 (no second $49 charge), and an
// in-flight Standard 150 checkout blocks a parallel Extended 500 purchase.
function standard150Block(rows) {
  const standard = rows.filter((row) => text(row?.plan_id) === STANDARD150_PLAN_ID);
  if (standard.some((row) => text(row.access_status) === "active" || row.has_full_access === true)) {
    return failure(409, "standard150_upgrade_policy_pending", "Your Standard 150 access stays active. Upgrades are not available yet.");
  }
  if (standard.some((row) => text(row.access_status) === "pending" && text(row.stripe_checkout_session_id))) {
    return failure(409, "standard150_checkout_pending", "Finish or cancel your existing checkout first.");
  }
  return null;
}

function accessStateBlock(access) {
  const status = text(access?.access_status);
  if (status === "revoked") return failure(409, "access_conflict", "Your access record needs support before checkout can continue.");
  if (status === "active" || access?.has_full_access === true) return failure(409, "already_active", "Extended 500 access is already active.");
  return null;
}

function sessionBoundToAccess(session, access, userId, email) {
  const metadata = session?.metadata || {};
  return text(metadata.base44_app_id) === EXTENDED500_APP_ID
    && text(metadata.plan_id) === EXTENDED500_PLAN_ID
    && text(metadata.access_id) === text(access?.id)
    && text(metadata.owner_user_id) === userId
    && normalizeEmail(metadata.user_email || session?.customer_email) === email
    && text(session?.client_reference_id) === userId;
}

async function loadSingleExtended500Row(entities, userId, email) {
  let rows = extended500Rows(await findOwnerAccessRows(entities, userId, email));
  if (rows.length > 1) rows = await reconcilePendingDuplicates(entities, rows, userId, email);
  return rows;
}

export async function createExtended500Checkout({ body, user, entities, stripe, secret, nowMs = Date.now() }) {
  // The switch is read before any entity, Stripe or request processing.
  const policy = extended500CheckoutPolicy(secret);
  if (!policy.ok) return failure(503, policy.code, "Extended 500 checkout is not available.");

  const userId = text(user?.id);
  const email = normalizeEmail(user?.email);
  if (!USER_ID.test(userId) || !email) return failure(401, "unauthorized", "Unauthorized");
  if (!body || typeof body !== "object" || Array.isArray(body) || Object.keys(body).some((key) => !BODY_KEYS.has(key))) {
    return failure(400, "invalid_request", "Unsupported checkout request.");
  }
  const origin = parseOrigin(body.origin);
  if (!origin || !allowedOrigins(secret).has(origin)) {
    return failure(403, "checkout_origin_not_allowed", "Checkout return URL is not configured.");
  }

  try {
    const ownerRows = await findOwnerAccessRows(entities, userId, email);
    const blocked = standard150Block(ownerRows);
    if (blocked) return blocked;

    let rows = await loadSingleExtended500Row(entities, userId, email);
    if (rows.length > 1) return failure(409, "duplicate_access", "Your access record needs support before checkout can continue.");
    if (rows.length === 0) {
      await entities.Access.create({
        user_email: email,
        owner_user_id: userId,
        access_status: "pending",
        plan_id: EXTENDED500_PLAN_ID,
        grant_source: "checkout_pending",
        app_id: EXTENDED500_APP_ID,
        has_full_access: false,
      });
      rows = await loadSingleExtended500Row(entities, userId, email);
      if (rows.length !== 1) return failure(409, "access_conflict", "Checkout could not establish a unique access record.");
    }
    const access = rows[0];
    if (!ownsRow(access, userId, email) || text(access.app_id) !== EXTENDED500_APP_ID) {
      return failure(409, "access_conflict", "Your access record needs support before checkout can continue.");
    }
    const stateBlock = accessStateBlock(access);
    if (stateBlock) return stateBlock;

    const previousSessionId = text(access.stripe_checkout_session_id);
    if (previousSessionId) {
      const previous = await stripe.checkout.sessions.retrieve(previousSessionId, { expand: ["line_items.data.price"] });
      if (!sessionBoundToAccess(previous, access, userId, email)) {
        return failure(409, "checkout_session_conflict", "Your checkout needs support before it can continue.");
      }
      if (previous.status === "open" && previous.url && sessionUsesExtended500Price(previous)) {
        return reply(200, { success: true, url: previous.url, reused: true });
      }
      if (previous.status === "complete" && previous.payment_status === "paid") {
        // Paid but the webhook has not granted yet (late or lost delivery).
        // Re-verify the session from Stripe and fulfil through the same path.
        const fulfilled = await fulfillExtended500Session({ session: previous, entities, paidAtMs: nowMs });
        if (fulfilled.outcome === "granted" || fulfilled.outcome === "replay") {
          return reply(200, { success: true, already_active: true, reconciled: fulfilled.outcome === "granted" });
        }
        return failure(409, "checkout_payment_processing", "Your payment is already being processed.");
      }
      if (previous.status === "complete") {
        // Delayed payment methods: never a second session while one may settle.
        return failure(409, "checkout_payment_processing", "Your payment is already being processed.");
      }
      if (previous.status === "open") {
        await stripe.checkout.sessions.expire(previousSessionId);
      } else if (previous.status !== "expired") {
        return failure(409, "checkout_session_conflict", "Your checkout needs support before it can continue.");
      }
    }

    const metadata = {
      base44_app_id: EXTENDED500_APP_ID,
      owner_user_id: userId,
      user_email: email,
      plan_id: EXTENDED500_PLAN_ID,
      access_id: text(access.id),
    };
    const session = await stripe.checkout.sessions.create(
      {
        mode: "payment",
        line_items: [{ price: EXTENDED500_STRIPE_PRICE_ID, quantity: 1 }],
        customer_email: email,
        client_reference_id: userId,
        success_url: `${origin}/billing?paid=1&plan=extended500`,
        cancel_url: `${origin}/billing`,
        metadata,
        payment_intent_data: { metadata },
      },
      { idempotencyKey: await extended500CheckoutIdempotencyKey(access, policy.generation) },
    );
    await entities.Access.update(access.id, { stripe_checkout_session_id: text(session.id) });
    return reply(200, { success: true, url: session.url });
  } catch {
    return failure(500, "checkout_failed", "Checkout is temporarily unavailable.");
  }
}
