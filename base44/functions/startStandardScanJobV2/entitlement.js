export const ACCESS_APP_ID = "6a498732ec779dfaaeab0e53";
export const ACCESS_PLAN_ID = "standard150_lifetime";
export const OWNER_TEST_EMAIL = "bright4862@gmail.com";
export const OWNER_TEST_USER_ID = "6a498da58ef5cec1f5cd4486";

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
  const grantedAt = Date.parse(String(row?.granted_at || ""));
  const identityMatches = Boolean(
    email &&
    userId &&
    normalizeEmail(row?.user_email) === email &&
    String(row?.owner_user_id || "").trim() === userId
  );
  const activeGrant = Boolean(
    row?.has_full_access === true &&
    row?.access_status === "active" &&
    row?.plan_id === ACCESS_PLAN_ID &&
    row?.app_id === ACCESS_APP_ID
  );
  const paidGrantMatches = Boolean(
    activeGrant &&
    row?.grant_source === "stripe_checkout" &&
    String(row?.stripe_checkout_session_id || "").trim() &&
    Number.isFinite(paidAt)
  );
  const ownerTestGrantMatches = Boolean(
    activeGrant &&
    row?.grant_source === "owner_test" &&
    email === OWNER_TEST_EMAIL &&
    userId === OWNER_TEST_USER_ID &&
    Number.isFinite(grantedAt)
  );
  const manualGrantMatches = Boolean(
    activeGrant &&
    row?.grant_source === "manual_grant" &&
    Number.isFinite(grantedAt)
  );

  return identityMatches && (paidGrantMatches || ownerTestGrantMatches || manualGrantMatches)
    ? { ok: true, record: row }
    : { ok: false, failureCode: "paid_access_required" };
}
