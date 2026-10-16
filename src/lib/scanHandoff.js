import * as legacy from "./scanHandoffLegacy.js";

export * from "./scanHandoffLegacy.js";

const STAGE3_HANDOFF_VERSION = "fixlist_handoff_v2";
const STAGE3_SCORE_CAP_VERSION = "stage3_health_score_caps_v1_verified_root_cause";

function validStage3Handoff(scanRecord) {
  const handoff = scanRecord?.stage3_handoff_v2;
  const decision = scanRecord?.stage3_health_score_decision;
  if (!handoff || typeof handoff !== "object" || Array.isArray(handoff)) return null;
  if (!decision || typeof decision !== "object" || Array.isArray(decision)) return null;
  if (handoff.handoff_version !== STAGE3_HANDOFF_VERSION) return null;
  if (decision.version !== STAGE3_SCORE_CAP_VERSION || decision.state !== "decided") return null;
  if (Object.prototype.hasOwnProperty.call(handoff, "suppressed_findings")) return null;
  if (!Array.isArray(handoff.fixes) || !Number.isInteger(handoff.fix_count) || handoff.fix_count !== handoff.fixes.length) return null;
  const scan = handoff.scan;
  if (!scan || typeof scan !== "object" || Array.isArray(scan)) return null;
  const scanId = typeof scanRecord?.id === "string" ? scanRecord.id.trim() : "";
  if (!scanId || scan.scan_id !== scanId || scan.scan_run_id !== scanId) return null;
  if (!Number.isInteger(decision.adjusted_health_score) || decision.adjusted_health_score < 0 || decision.adjusted_health_score > 100) return null;
  if (Number(scanRecord?.health_score) !== decision.adjusted_health_score) return null;
  if (handoff.fixes.some((fix) => fix?.priority_factors?.version !== "repair_priority_v3_four_factor_v1")) return null;
  return handoff;
}

/**
 * Handoff v2 is already produced by Python and authenticated by the V7 HMAC.
 * Return that exact customer-safe source rather than rebuilding rankings,
 * counts or scores in the browser. Historical scans continue to use v1.
 */
export function buildScanHandoff(options = {}) {
  const scanRecord = options?.scanRecord;
  const stage3Claimed = Boolean(
    scanRecord
    && (
      Object.prototype.hasOwnProperty.call(scanRecord, "stage3_handoff_v2")
      || Object.prototype.hasOwnProperty.call(scanRecord, "stage3_health_score_decision")
    )
  );
  if (!stage3Claimed) return legacy.buildScanHandoff(options);
  const handoff = validStage3Handoff(scanRecord);
  if (!handoff) throw new Error("Stage3 handoff is invalid");
  return structuredClone(handoff);
}
