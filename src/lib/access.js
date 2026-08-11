import { base44 } from "@/api/base44Client";

export const UNLOCK_PRICE_LABEL = "$30";
export const FREE_PREVIEW_FIX_COUNT = 0;

function normalizeEmail(value) {
  return String(value || "").trim().toLowerCase();
}

export function isActivePaidAccess(record, user = {}) {
  const email = normalizeEmail(user?.email);
  const userId = String(user?.id || "").trim();
  if (!record || !email || !userId) return false;
  return (
    normalizeEmail(record.user_email) === email &&
    String(record.owner_user_id || "") === userId &&
    record.has_full_access === true &&
    record.access_status === "active" &&
    record.plan_id === "standard150_lifetime" &&
    record.grant_source === "stripe_checkout" &&
    record.app_id === "6a498732ec779dfaaeab0e53" &&
    Boolean(record.paid_at)
  );
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
