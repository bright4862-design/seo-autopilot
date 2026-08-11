import { base44 } from "@/api/base44Client";

export const UNLOCK_PRICE_LABEL = "$50";
export const LOCKED_PREVIEW_FIX_COUNT = 0;
const OWNER_TEST_EMAIL = "bright4862@gmail.com";
const OWNER_TEST_USER_ID = "6a498da58ef5cec1f5cd4486";

function normalizeEmail(value) {
  return String(value || "").trim().toLowerCase();
}

export function isActivePaidAccess(record, user = {}) {
  const email = normalizeEmail(user?.email);
  const userId = String(user?.id || "").trim();
  if (!record || !email || !userId) return false;
  const identityMatches = (
    normalizeEmail(record.user_email) === email &&
    String(record.owner_user_id || "") === userId
  );
  const activeGrant = (
    record.has_full_access === true &&
    record.access_status === "active" &&
    record.plan_id === "standard150_lifetime" &&
    record.app_id === "6a498732ec779dfaaeab0e53"
  );
  const paidGrant = record.grant_source === "stripe_checkout" && Boolean(record.paid_at);
  const ownerTestGrant = (
    record.grant_source === "owner_test" &&
    email === OWNER_TEST_EMAIL &&
    userId === OWNER_TEST_USER_ID &&
    Boolean(record.granted_at)
  );
  return identityMatches && activeGrant && (paidGrant || ownerTestGrant);
}

export async function loadAccess() {
  const user = await base44.auth.me().catch(() => null);
  const email = normalizeEmail(user?.email);
  const userId = String(user?.id || "").trim();
  if (!email || !userId) {
    return { email: "", fullAccess: false, scansUsed: 0, canScan: false, record: null };
  }

  const records = await base44.entities.Access.filter({ user_email: email }).catch(() => []);
  const rows = Array.isArray(records) ? records : [];
  const record = rows.length === 1 ? rows[0] : null;
  const fullAccess = isActivePaidAccess(record, user);

  return {
    email,
    fullAccess,
    scansUsed: 0,
    canScan: fullAccess,
    record,
    conflict: rows.length > 1,
  };
}
