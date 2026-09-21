import {
  authoritySnapshotFromRows,
  buildCustomerProjection,
} from "./projection.js";
import { PUBLISHED_REVIEW_ATTESTATION_VERSION } from "./publishedRepairEvidence.js";

export const STAGE3_AUTHORITY_VERSION = "standard_review_snapshot_hmac_stage3_delivery_v1";
export const STAGE3_V7_DELIVERY_VERSION = "stage3_v7_delivery_v1";
export const STAGE3_PRIORITY_VERSION = "repair_priority_v3_four_factor_v1";
export const STAGE3_PREVIEW_SOURCE_VERSION = "stage3_preview_source_v1_verified_evidence";
export const STAGE3_SCORE_CAP_VERSION = "stage3_health_score_caps_v1_verified_root_cause";
export const STAGE3_HANDOFF_VERSION = "fixlist_handoff_v2";

const object = (value) => value && typeof value === "object" && !Array.isArray(value) ? value : null;
const text = (value, limit = 2_000) => typeof value === "string" ? value.trim().slice(0, limit) : "";
const finite = (value, min, max) => typeof value === "number" && Number.isFinite(value) && value >= min && value <= max;
const nullableFinite = (value, min, max) => value === null || finite(value, min, max);
const nonNegativeInteger = (value) => Number.isInteger(value) && value >= 0;
const nullableNonNegativeInteger = (value) => value === null || nonNegativeInteger(value);

function validPriorityFactors(value) {
  const source = object(value);
  if (!source || source.version !== STAGE3_PRIORITY_VERSION) return false;
  if (!Number.isInteger(source.impact) || source.impact < 0 || source.impact > 5) return false;
  if (!nullableFinite(source.reach, 0, 1) || !nullableFinite(source.page_value, 0, 1) || !nullableFinite(source.confidence, 0, 1) || !nullableFinite(source.priority_factor_score, 0, 5)) return false;
  if (!nonNegativeInteger(source.reach_affected_indexable) || !nonNegativeInteger(source.reach_observed_indexable_family) || source.reach_affected_indexable > source.reach_observed_indexable_family) return false;
  if (!Array.isArray(source.explanation) || source.explanation.length > 8 || source.explanation.some((item) => typeof item !== "string")) return false;
  if (source.priority_factor_score !== null) {
    if (source.reach === null || source.page_value === null || source.confidence === null) return false;
    const expected = Math.round(source.impact * source.reach * source.page_value * source.confidence * 1_000_000) / 1_000_000;
    if (Math.abs(expected - source.priority_factor_score) > 1e-9) return false;
  }
  return true;
}

function validCounts(value) {
  const source = object(value);
  if (!source) return false;
  if (!nonNegativeInteger(source.unique_affected_page_count) || !nullableNonNegativeInteger(source.observation_count) || !nullableNonNegativeInteger(source.known_population_count)) return false;
  if (!nonNegativeInteger(source.displayed_sample_count) || source.displayed_sample_count > 10 || !nonNegativeInteger(source.truncated_sample_count)) return false;
  if (!Array.isArray(source.displayed_samples) || source.displayed_samples.length !== source.displayed_sample_count || source.displayed_samples.some((item) => typeof item !== "string")) return false;
  if (source.known_population_count !== null && source.known_population_count < source.unique_affected_page_count) return false;
  if (source.displayed_sample_count > source.unique_affected_page_count || source.truncated_sample_count !== source.unique_affected_page_count - source.displayed_sample_count) return false;
  return source.examples_partial === (source.displayed_sample_count < source.unique_affected_page_count);
}

function validCapsule(run, fixItems) {
  const explanation = object(run?.health_score_explanation);
  const capsule = object(explanation?.stage3_delivery);
  if (!capsule || capsule.version !== STAGE3_V7_DELIVERY_VERSION) return null;
  const delivery = object(capsule.delivery);
  const preview = object(capsule.private_preview_source);
  const decision = object(capsule.health_score_decision);
  const handoff = object(capsule.handoff_v2_source);
  if (!delivery || delivery.version !== "stage3_delivery_v1_rank_before_truncate") return null;
  if (!preview || preview.version !== STAGE3_PREVIEW_SOURCE_VERSION || text(preview.scan_id, 160) !== text(run?.id, 160) || preview.entitlement_state !== "requires_authenticated_customer_gate") return null;
  if (!Array.isArray(preview.findings) || preview.findings.length > 2) return null;
  if (!decision || decision.version !== STAGE3_SCORE_CAP_VERSION || decision.state !== "decided" || !Number.isInteger(decision.adjusted_health_score) || decision.adjusted_health_score < 0 || decision.adjusted_health_score > 100 || decision.adjusted_health_score !== run?.health_score) return null;
  if (!handoff || handoff.handoff_version !== STAGE3_HANDOFF_VERSION || handoff.suppressed_findings !== undefined || !object(handoff.scan) || text(handoff.scan.scan_id, 160) !== text(run?.id, 160) || text(handoff.scan.scan_run_id, 160) !== text(run?.id, 160)) return null;
  const ids = new Set();
  for (const item of Array.isArray(fixItems) ? fixItems : []) {
    const id = text(item?.fix_id, 160);
    const perFix = object(object(item?.raw_finding)?.stage3_delivery);
    if (!id || ids.has(id) || !perFix || perFix.version !== STAGE3_V7_DELIVERY_VERSION || !validPriorityFactors(perFix.priority_factors) || !validCounts(perFix.counts)) return null;
    ids.add(id);
  }
  if (preview.findings.some((finding) => !ids.has(text(finding?.rule_id, 160)))) return null;
  if (!Array.isArray(handoff.fixes) || handoff.fixes.length !== handoff.fix_count || handoff.fixes.some((fix) => !ids.has(text(fix?.rule_id, 160)) || fix?.suppressed_findings !== undefined)) return null;
  return capsule;
}

export function authoritySnapshotFromRowsStage3(args) {
  const run = object(args?.run) || {};
  if (run.authority_seal_version !== STAGE3_AUTHORITY_VERSION) return authoritySnapshotFromRows(args);
  const capsule = validCapsule(run, args?.fixItems);
  if (!capsule) throw new Error("Persisted Stage3 authority payload is invalid");
  const base = authoritySnapshotFromRows({
    ...args,
    run: { ...run, authority_seal_version: PUBLISHED_REVIEW_ATTESTATION_VERSION },
  });
  base.version = STAGE3_AUTHORITY_VERSION;
  base.scan.health_score_explanation = {
    ...(object(base.scan.health_score_explanation) || {}),
    stage3_delivery: capsule,
  };
  const rowById = new Map((Array.isArray(args?.fixItems) ? args.fixItems : []).map((item) => [text(item?.fix_id, 160), item]));
  base.recommendations = base.recommendations.map((fix) => {
    const row = rowById.get(text(fix.fix_id, 160));
    return {
      ...fix,
      raw_finding: {
        ...(object(fix.raw_finding) || {}),
        stage3_delivery: object(row?.raw_finding)?.stage3_delivery,
      },
    };
  });
  return base;
}

export function buildCustomerProjectionStage3(args) {
  const projection = buildCustomerProjection(args);
  if (args?.fullAccess !== true || args?.authorityVerified !== true || args?.run?.authority_seal_version !== STAGE3_AUTHORITY_VERSION) return projection;
  const capsule = validCapsule(args.run, args.fixItems);
  if (!capsule) throw new Error("Verified Stage3 customer payload is invalid");
  projection.run.stage3_health_score_decision = capsule.health_score_decision;
  projection.run.stage3_handoff_v2 = capsule.handoff_v2_source;
  const rowById = new Map((Array.isArray(args.fixItems) ? args.fixItems : []).map((item) => [text(item?.fix_id, 160), item]));
  projection.fixItems = projection.fixItems.map((item) => {
    const raw = object(rowById.get(text(item.fix_id, 160))?.raw_finding);
    const perFix = object(raw?.stage3_delivery);
    return {
      ...item,
      stage3_priority_factors: perFix.priority_factors,
      stage3_counts: perFix.counts,
    };
  });
  return projection;
}
