// Customer-owned scan-history cleanup. Deletion runs server-side with owner
// verification (ScanRun/FixList/FixItem are admin-only by RLS), so this module
// only calls it and normalizes the result for the UI. It never touches the
// scanner or the scan pipeline.

import { base44 } from "@/api/base44Client";

const DELETE_FUNCTION = "deleteCustomerScanDataV2";

export const KEEP_NEWEST_SCANS = 3;

function resultOf(response) {
  return response?.data && typeof response.data === "object" ? response.data : response;
}

// Removes one saved scan and its recommendations. Returns { ok } so the caller
// can keep the row visible when the server refuses.
export async function deleteScanRun(projectId, scanId) {
  const project_id = String(projectId || "").trim();
  const scan_id = String(scanId || "").trim();
  if (!project_id || !scan_id) return { ok: false, reason: "missing_identity" };
  try {
    const result = resultOf(await base44.functions.invoke(DELETE_FUNCTION, {
      action: "delete",
      project_id,
      scan_id,
    }));
    if (result?.success !== true) {
      return { ok: false, reason: String(result?.error_code || "delete_failed") };
    }
    return { ok: true, deletedScanIds: result.deleted_scan_ids || [scan_id] };
  } catch (error) {
    console.warn("Saved scan delete failed.", error?.code || "request_failed");
    return { ok: false, reason: "delete_failed" };
  }
}

// Keeps only the newest scans for a website. Best-effort: a failure here must
// never block the history view from rendering.
export async function pruneScanHistory(projectId) {
  const project_id = String(projectId || "").trim();
  if (!project_id) return { ok: false, deletedScanIds: [] };
  try {
    const result = resultOf(await base44.functions.invoke(DELETE_FUNCTION, {
      action: "prune",
      project_id,
    }));
    return {
      ok: result?.success === true,
      deletedScanIds: Array.isArray(result?.deleted_scan_ids) ? result.deleted_scan_ids : [],
    };
  } catch (error) {
    console.warn("Saved scan cleanup failed.", error?.code || "request_failed");
    return { ok: false, deletedScanIds: [] };
  }
}