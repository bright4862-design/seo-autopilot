export const ACCESS_APP_ID = "6a498732ec779dfaaeab0e53";
export const ACCESS_PLAN_ID = "standard150_lifetime";

function normalizeEmail(value) {
  return String(value || "").trim().toLowerCase();
}

export function uniqueAccessRows(rows = []) {
  return Array.from(new Map(
    (Array.isArray(rows) ? rows : []).filter(Boolean).map((row) => [String(row.id || ""), row]),
  ).values()).filter((row) => String(row.id || ""));
}

export function evaluatePaidAccess({ rows, user }) {
  const records = uniqueAccessRows(rows);
  if (records.length > 1) return { ok: false, failureCode: "paid_access_conflict" };
  if (records.length === 0) return { ok: false, failureCode: "paid_access_required" };

  const row = records[0];
  const email = normalizeEmail(user?.email);
  const userId = String(user?.id || "").trim();
  const paidAt = Date.parse(String(row?.paid_at || ""));
  const identityMatches = Boolean(
    email &&
    userId &&
    normalizeEmail(row?.user_email) === email &&
    String(row?.owner_user_id || "").trim() === userId
  );
  const grantMatches = Boolean(
    row?.has_full_access === true &&
    row?.access_status === "active" &&
    row?.plan_id === ACCESS_PLAN_ID &&
    row?.grant_source === "stripe_checkout" &&
    row?.app_id === ACCESS_APP_ID &&
    String(row?.stripe_checkout_session_id || "").trim() &&
    Number.isFinite(paidAt)
  );

  return identityMatches && grantMatches
    ? { ok: true, record: row }
    : { ok: false, failureCode: "paid_access_required" };
}
