import { base44 } from "@/api/base44Client";
import {
  OWNER_SCAN_DEBUG_EMAIL,
  OWNER_SCAN_DEBUG_USER_ID,
  isOwnerScanDebugUser,
} from "@/lib/ownerScanDebugIdentity";

export {
  OWNER_SCAN_DEBUG_EMAIL,
  OWNER_SCAN_DEBUG_USER_ID,
  isOwnerScanDebugUser,
};

const OWNER_SCAN_DEBUG_FUNCTION = "ownerScanDebugControl";

function resultOf(response) {
  return response?.data && typeof response.data === "object" ? response.data : response;
}

async function invokeOwnerControl(payload) {
  try {
    const result = resultOf(await base44.functions.invoke(OWNER_SCAN_DEBUG_FUNCTION, payload));
    if (result?.success !== true) {
      return {
        ok: false,
        reason: String(result?.error_code || "owner_scan_control_failed"),
        message: String(result?.error || "Owner scan control failed."),
      };
    }
    return { ok: true, ...result };
  } catch (error) {
    return {
      ok: false,
      reason: String(error?.code || "owner_scan_control_failed"),
      message: String(error?.message || "Owner scan control failed."),
    };
  }
}

export async function debugScanRun(scanId) {
  const scan_id = String(scanId || "").trim();
  if (!scan_id) return { ok: false, reason: "scan_id_required", message: "A scan id is required." };
  return invokeOwnerControl({ action: "debug", scan_id });
}

export async function forceStopScanRun(scanId, attemptCount) {
  const scan_id = String(scanId || "").trim();
  const attempt_count = Number(attemptCount);
  if (!scan_id || !Number.isFinite(attempt_count) || attempt_count < 1) {
    return { ok: false, reason: "scan_identity_required", message: "The current scan attempt could not be confirmed." };
  }
  return invokeOwnerControl({
    action: "kill",
    scan_id,
    attempt_count: Math.trunc(attempt_count),
  });
}
