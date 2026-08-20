export const SCAN_HISTORY_PRESENTATION_VERSION = "scan_history_presentation_v1_explicit_lineage";

function clean(value = "") {
  return String(value || "").trim();
}

/**
 * Present only durable scan lineage that the server explicitly persisted.
 *
 * A scan may be labeled "Rescan" when it points to a previous scan through the
 * existing lineage fields. This helper deliberately does not inspect health
 * score movement, repair counts, missing findings, or verification outcomes and
 * therefore cannot manufacture "improved", "worsened", or "fixed" history.
 */
export function scanHistoryLineagePresentation(scan = {}) {
  const previousScanId = clean(scan.previous_scan_id || scan.previousScanId);
  const rescanOfScanId = clean(scan.rescan_of_scan_id || scan.rescanOfScanId);
  const parentScanId = rescanOfScanId || previousScanId;

  if (!parentScanId) return null;

  return {
    version: SCAN_HISTORY_PRESENTATION_VERSION,
    state: "explicit_rescan_lineage",
    label: "Rescan",
    parentScanId,
    comparisonClaimAllowed: false,
  };
}
