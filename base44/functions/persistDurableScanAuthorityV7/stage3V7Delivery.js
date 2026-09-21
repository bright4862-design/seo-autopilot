import * as strict from "./stage3V7DeliveryStrict.js";

export * from "./stage3V7DeliveryStrict.js";

const plainObject = (value) => value && typeof value === "object" && !Array.isArray(value) ? value : null;

function isTruthfulUnknownReach(factors) {
  const source = plainObject(factors);
  return Boolean(
    source
    && source.version === strict.STAGE3_PRIORITY_VERSION
    && source.reach === null
    && source.priority_factor_score === null
    && source.reach_observed_indexable_family === null
    && Number.isInteger(source.reach_affected_indexable)
    && source.reach_affected_indexable >= 0
  );
}

function unknownIdsFromReview(review) {
  const ids = new Set();
  for (const repair of Array.isArray(review?.canonical_repairs) ? review.canonical_repairs : []) {
    if (isTruthfulUnknownReach(repair?.stage3_priority_factors) && typeof repair?.fix_id === "string" && repair.fix_id.trim()) {
      ids.add(repair.fix_id.trim());
    }
  }
  return ids;
}

function strictReviewForUnknownReach(review, ids) {
  if (!ids.size) return review;
  const copy = structuredClone(review);
  for (const repair of Array.isArray(copy?.canonical_repairs) ? copy.canonical_repairs : []) {
    const id = typeof repair?.fix_id === "string" ? repair.fix_id.trim() : "";
    if (ids.has(id) && isTruthfulUnknownReach(repair?.stage3_priority_factors)) {
      repair.stage3_priority_factors.reach_observed_indexable_family = 0;
    }
  }
  const handoffFixes = Array.isArray(copy?.stage3_handoff_v2_source?.fixes)
    ? copy.stage3_handoff_v2_source.fixes
    : [];
  for (const fix of handoffFixes) {
    const id = typeof fix?.rule_id === "string" ? fix.rule_id.trim() : "";
    if (!ids.has(id)) continue;
    if (!isTruthfulUnknownReach(fix?.priority_factors)) {
      throw new Error("Stage3 unknown reach differs between canonical repair and handoff evidence");
    }
    fix.priority_factors.reach_observed_indexable_family = 0;
  }
  return copy;
}

function restoreUnknownReach(snapshot, ids) {
  if (!ids.size) return snapshot;
  for (const fix of Array.isArray(snapshot?.recommendations) ? snapshot.recommendations : []) {
    const id = typeof fix?.fix_id === "string" ? fix.fix_id.trim() : "";
    const factors = fix?.raw_finding?.stage3_delivery?.priority_factors;
    if (ids.has(id) && factors?.reach === null && factors?.priority_factor_score === null) {
      factors.reach_observed_indexable_family = null;
    }
  }
  const handoffFixes = snapshot?.scan?.health_score_explanation?.stage3_delivery?.handoff_v2_source?.fixes;
  for (const fix of Array.isArray(handoffFixes) ? handoffFixes : []) {
    const id = typeof fix?.rule_id === "string" ? fix.rule_id.trim() : "";
    const factors = fix?.priority_factors;
    if (ids.has(id) && factors?.reach === null && factors?.priority_factor_score === null) {
      factors.reach_observed_indexable_family = null;
    }
  }
  return snapshot;
}

function unknownIdsFromPersisted(fixItems) {
  const ids = new Set();
  for (const item of Array.isArray(fixItems) ? fixItems : []) {
    const id = typeof item?.fix_id === "string" ? item.fix_id.trim() : "";
    if (id && isTruthfulUnknownReach(item?.raw_finding?.stage3_delivery?.priority_factors)) ids.add(id);
  }
  return ids;
}

function strictPersistedArgs(args, ids) {
  if (!ids.size) return args;
  const run = structuredClone(args?.run || {});
  const fixItems = structuredClone(Array.isArray(args?.fixItems) ? args.fixItems : []);
  for (const item of fixItems) {
    const id = typeof item?.fix_id === "string" ? item.fix_id.trim() : "";
    const factors = item?.raw_finding?.stage3_delivery?.priority_factors;
    if (ids.has(id) && isTruthfulUnknownReach(factors)) {
      factors.reach_observed_indexable_family = 0;
    }
  }
  const handoffFixes = run?.health_score_explanation?.stage3_delivery?.handoff_v2_source?.fixes;
  for (const fix of Array.isArray(handoffFixes) ? handoffFixes : []) {
    const id = typeof fix?.rule_id === "string" ? fix.rule_id.trim() : "";
    if (!ids.has(id)) continue;
    if (!isTruthfulUnknownReach(fix?.priority_factors)) {
      throw new Error("Persisted Stage3 unknown reach differs between repair and handoff evidence");
    }
    fix.priority_factors.reach_observed_indexable_family = 0;
  }
  return { ...args, run, fixItems };
}

/**
 * The strict Stage-3 serializer predates truthful unknown reach denominators and
 * required an integer there. Adapt only the documented unknown state while
 * retaining every other strict check, then restore null before the HMAC bytes
 * are produced so unknown evidence is never converted to a fabricated zero.
 */
export function buildAuthoritySnapshotStage3(options = {}) {
  const ids = unknownIdsFromReview(options?.review);
  const snapshot = strict.buildAuthoritySnapshotStage3({
    ...options,
    review: strictReviewForUnknownReach(options?.review, ids),
  });
  return restoreUnknownReach(snapshot, ids);
}

export function buildPersistedAuthoritySnapshotStage3(args = {}) {
  const ids = unknownIdsFromPersisted(args?.fixItems);
  const snapshot = strict.buildPersistedAuthoritySnapshotStage3(strictPersistedArgs(args, ids));
  return restoreUnknownReach(snapshot, ids);
}
