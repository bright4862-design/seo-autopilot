export const OWNER_SCAN_DEBUG_EMAIL = "bright4862@gmail.com";
export const OWNER_SCAN_DEBUG_USER_ID = "6a498da58ef5cec1f5cd4486";

function normalizeEmail(value) {
  return String(value || "").trim().toLowerCase();
}

export function isOwnerScanDebugUser(user = {}) {
  return (
    String(user?.id || "").trim() === OWNER_SCAN_DEBUG_USER_ID
    && normalizeEmail(user?.email) === OWNER_SCAN_DEBUG_EMAIL
    && String(user?.role || "").trim().toLowerCase() === "admin"
  );
}
