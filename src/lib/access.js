import { base44 } from "@/api/base44Client";

export const UNLIMITED_EMAILS = ["bright4862@gmail.com", "londonparisandbrussels@gmail.com"];
export const FREE_SCAN_LIMIT = 1;
export const UNLOCK_PRICE_LABEL = "$75";
export const FREE_PREVIEW_FIX_COUNT = 2;

export async function loadAccess() {
  const user = await base44.auth.me().catch(() => null);
  const email = String(user?.email || "").toLowerCase();
  if (!email) {
    return { email: "", fullAccess: false, scansUsed: 0, canScan: false, record: null };
  }

  const unlimited = UNLIMITED_EMAILS.includes(email);
  const records = await base44.entities.Access.filter({ user_email: email }).catch(() => []);
  const record = Array.isArray(records) ? records[0] || null : null;
  const fullAccess = unlimited || record?.has_full_access === true;
  const scansUsed = Number(record?.scans_used || 0);

  return {
    email,
    fullAccess,
    scansUsed,
    canScan: fullAccess || scansUsed < FREE_SCAN_LIMIT,
    record,
  };
}

export async function recordScanUsed() {
  const access = await loadAccess();
  if (!access.email || access.fullAccess) return;
  if (access.record) {
    await base44.entities.Access.update(access.record.id, { scans_used: access.scansUsed + 1 }).catch(() => {});
    return;
  }
  await base44.entities.Access.create({ user_email: access.email, scans_used: 1, has_full_access: false }).catch(() => {});
}