import { authoritySnapshotFromRows } from "./authoritySnapshot.js";
import { PUBLISHED_REVIEW_ATTESTATION_VERSION } from "./publishedRepairEvidence.js";

export const STAGE3_AUTHORITY_VERSION = "standard_review_snapshot_hmac_stage3_delivery_v1";
const STAGE3_V7_DELIVERY_VERSION = "stage3_v7_delivery_v1";
const STAGE3_PRIORITY_VERSION = "repair_priority_v3_four_factor_v1";

const object = (value) => value && typeof value === "object" && !Array.isArray(value) ? value : null;
const text = (value, limit = 160) => typeof value === "string" ? value.trim().slice(0, limit) : "";

function validStage3Rows(scan, fixItems) {
  const capsule = object(object(scan?.health_score_explanation)?.stage3_delivery);
  if (!capsule || capsule.version !== STAGE3_V7_DELIVERY_VERSION) return null;
  if (capsule.private_preview_source?.scan_id !== scan?.id) return null;
  if (capsule.health_score_decision?.adjusted_health_score !== scan?.health_score) return null;
  if (capsule.handoff_v2_source?.handoff_version !== "fixlist_handoff_v2" || capsule.handoff_v2_source?.suppressed_findings !== undefined) return null;
  if (capsule.handoff_v2_source?.scan?.scan_id !== scan?.id || capsule.handoff_v2_source?.scan?.scan_run_id !== scan?.id) return null;
  const rows = Array.isArray(fixItems) ? fixItems : [];
  const ids = new Set();
  for (const row of rows) {
    const id = text(row?.fix_id);
    const stage3 = object(object(row?.raw_finding)?.stage3_delivery);
    if (!id || ids.has(id) || !stage3 || stage3.version !== STAGE3_V7_DELIVERY_VERSION || stage3.priority_factors?.version !== STAGE3_PRIORITY_VERSION || !object(stage3.counts)) return null;
    ids.add(id);
  }
  if (!Array.isArray(capsule.handoff_v2_source?.fixes) || capsule.handoff_v2_source.fixes.some((fix) => !ids.has(text(fix?.rule_id)))) return null;
  return capsule;
}

export function authoritySnapshotFromRowsStage3(args) {
  const scan = object(args?.scan) || {};
  if (scan.authority_seal_version !== STAGE3_AUTHORITY_VERSION) return authoritySnapshotFromRows(args);
  const capsule = validStage3Rows(scan, args?.fixItems);
  if (!capsule) throw new Error("Persisted Stage3 Grok authority payload is invalid");
  const base = authoritySnapshotFromRows({
    ...args,
    scan: { ...scan, authority_seal_version: PUBLISHED_REVIEW_ATTESTATION_VERSION },
  });
  base.version = STAGE3_AUTHORITY_VERSION;
  base.scan.health_score_explanation = {
    ...(object(base.scan.health_score_explanation) || {}),
    stage3_delivery: capsule,
  };
  const rows = new Map((Array.isArray(args?.fixItems) ? args.fixItems : []).map((item) => [text(item?.fix_id), item]));
  base.recommendations = base.recommendations.map((fix) => ({
    ...fix,
    raw_finding: {
      ...(object(fix.raw_finding) || {}),
      stage3_delivery: object(rows.get(text(fix.fix_id))?.raw_finding)?.stage3_delivery,
    },
  }));
  return base;
}
