export const REPAIR_CONTRACT_V2 = "repair_contract_v2_shadow_calibrated";
export const REPAIR_PRIORITY_MODEL_V2 = "repair_priority_v2_technical_severity";
export const RULE_EVALUATION_CONTRACT_V1 = "rule_evaluation_v1_explicit";

const BASE_SEVERITIES = new Set(["critical", "high", "medium", "low"]);
const EVIDENCE_CLASSES = new Set(["confirmed_problem", "improvement", "opportunity"]);
const ACTION_PRIORITIES = new Set(["fix_first", "important", "improve", "review"]);

function clean(value = "") {
  return String(value || "").trim();
}

function finiteNumber(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function nonNegativeInteger(value) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 0 ? parsed : 0;
}

function clone(value) {
  return value == null ? value : structuredClone(value);
}

function exactIdSet(expectedIds, actualIds, code) {
  if (expectedIds.length !== actualIds.length) throw new Error(`${code}:count`);
  if (new Set(expectedIds).size !== expectedIds.length) throw new Error(`${code}:duplicate_expected`);
  if (new Set(actualIds).size !== actualIds.length) throw new Error(`${code}:duplicate_actual`);
  const expected = new Set(expectedIds);
  if (actualIds.some((id) => !expected.has(id))) throw new Error(`${code}:set`);
}

function priorityContext(value = {}) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const result = {};
  const numericKeys = [
    "affected_checked",
    "checked_eligible",
    "indexable_affected",
    "indexable_checked_eligible",
    "important_affected",
  ];
  for (const key of numericKeys) {
    if (source[key] !== undefined) result[key] = nonNegativeInteger(source[key]);
  }
  if (source.shared_repair_confirmed !== undefined) {
    result.shared_repair_confirmed = source.shared_repair_confirmed === true;
  }
  return result;
}

function normalizeRuleEvaluation(value = {}) {
  const rule = clean(value.rule || value.rule_id || value.category);
  if (!rule) throw new Error("repair_contract_v2_rule_evaluation_missing_rule");
  return {
    rule,
    rule_definition_version: clean(value.rule_definition_version),
    evaluated: value.evaluated === true,
    applicable: value.applicable === true,
    passed: value.passed === true,
    eligible_checked_count: nonNegativeInteger(value.eligible_checked_count),
    evaluated_page_count: nonNegativeInteger(value.evaluated_page_count),
    limitation_code: clean(value.limitation_code),
  };
}

function normalizeRepairAnnotation(value = {}, { rank, parentIdentityVersion, parentVerificationVersion } = {}) {
  const fixId = clean(value.fix_id || value.id);
  const baseSeverity = clean(value.base_severity).toLowerCase();
  const evidenceClass = clean(value.evidence_class).toLowerCase();
  const actionPriority = clean(value.action_priority).toLowerCase();
  const identityVersion = clean(value.repair_identity_version || parentIdentityVersion);
  const verificationVersion = clean(value.repair_verification_version || parentVerificationVersion);
  const fingerprint = clean(value.repair_fingerprint);
  const priorityReason = clean(value.priority_reason);

  if (!fixId) throw new Error("repair_contract_v2_missing_fix_id");
  if (!BASE_SEVERITIES.has(baseSeverity)) throw new Error(`repair_contract_v2_base_severity:${fixId}`);
  if (!EVIDENCE_CLASSES.has(evidenceClass)) throw new Error(`repair_contract_v2_evidence_class:${fixId}`);
  if (!ACTION_PRIORITIES.has(actionPriority)) throw new Error(`repair_contract_v2_action_priority:${fixId}`);
  if (!identityVersion) throw new Error(`repair_contract_v2_identity_version:${fixId}`);
  if (!fingerprint) throw new Error(`repair_contract_v2_fingerprint:${fixId}`);
  if (!priorityReason) throw new Error(`repair_contract_v2_priority_reason:${fixId}`);

  const normalized = {
    repair_contract_version: REPAIR_CONTRACT_V2,
    repair_priority_model_version: REPAIR_PRIORITY_MODEL_V2,
    base_severity: baseSeverity,
    evidence_class: evidenceClass,
    action_priority: actionPriority,
    canonical_action_rank: rank,
    action_priority_score: finiteNumber(value.action_priority_score),
    priority_reason: priorityReason,
    priority_context: priorityContext(value.priority_context),
    repair_identity_version: identityVersion,
    repair_fingerprint: fingerprint,
    repair_surface: clean(value.repair_surface),
    remediation_family: clean(value.remediation_family),
    shared_repair_confirmed: value.shared_repair_confirmed === true,
    rule_definition_version: clean(value.rule_definition_version),
    comparison_profile_version: clean(value.comparison_profile_version),
    repair_verification_version: verificationVersion,
    repair_verification_state: clean(value.repair_verification_state),
  };
  return { fixId, normalized };
}

function v2ParentFromContract(contract = {}, canonicalIds, ruleEvaluations) {
  const identityVersion = clean(contract.repair_identity_version);
  const verificationVersion = clean(contract.repair_verification_version);
  if (!identityVersion) throw new Error("repair_contract_v2_parent_identity_version");
  if (!verificationVersion) throw new Error("repair_contract_v2_parent_verification_version");

  const parent = {
    repair_contract_version: REPAIR_CONTRACT_V2,
    repair_snapshot_contract_version: REPAIR_CONTRACT_V2,
    repair_snapshot_contract_complete: true,
    repair_priority_model_version: REPAIR_PRIORITY_MODEL_V2,
    repair_identity_version: identityVersion,
    repair_verification_version: verificationVersion,
    canonical_action_fix_ids: canonicalIds,
  };
  if (ruleEvaluations) {
    parent.rule_evaluation_contract_version = RULE_EVALUATION_CONTRACT_V1;
    parent.rule_evaluations = ruleEvaluations;
  }
  return parent;
}

/**
 * Apply a complete v2 repair contract to an already-built authoritative snapshot.
 *
 * Candidate only: runtime authority builders must not import this module until a
 * separate activation decision. The legacy snapshot is cloned and remains
 * untouched. Recommendation serialization order stays unchanged; canonical
 * customer order is persisted separately in canonical_action_fix_ids.
 */
export function applyRepairContractV2Candidate(snapshot, contract = {}) {
  const result = clone(snapshot);
  const repairs = Array.isArray(contract.repairs) ? contract.repairs : [];
  const canonicalIds = Array.isArray(contract.canonical_action_fix_ids)
    ? contract.canonical_action_fix_ids.map(clean).filter(Boolean)
    : [];
  const snapshotIds = (result?.recommendations || []).map((item) => clean(item?.fix_id)).filter(Boolean);

  if (clean(contract.repair_contract_version) !== REPAIR_CONTRACT_V2) {
    throw new Error("repair_contract_v2_parent_contract_version");
  }
  if (clean(contract.repair_priority_model_version) !== REPAIR_PRIORITY_MODEL_V2) {
    throw new Error("repair_contract_v2_parent_priority_model");
  }
  exactIdSet(snapshotIds, canonicalIds, "repair_contract_v2_canonical_order");

  const repairById = new Map();
  const canonicalRank = new Map(canonicalIds.map((id, index) => [id, index + 1]));
  for (const value of repairs) {
    const id = clean(value?.fix_id || value?.id);
    if (!id) throw new Error("repair_contract_v2_missing_fix_id");
    if (repairById.has(id)) throw new Error(`repair_contract_v2_duplicate_repair:${id}`);
    const { normalized } = normalizeRepairAnnotation(value, {
      rank: canonicalRank.get(id),
      parentIdentityVersion: contract.repair_identity_version,
      parentVerificationVersion: contract.repair_verification_version,
    });
    if (!canonicalRank.has(id)) throw new Error(`repair_contract_v2_unknown_repair:${id}`);
    repairById.set(id, normalized);
  }
  exactIdSet(snapshotIds, [...repairById.keys()], "repair_contract_v2_repair_annotations");

  const ruleEvaluations = clean(contract.rule_evaluation_contract_version)
    ? (() => {
        if (clean(contract.rule_evaluation_contract_version) !== RULE_EVALUATION_CONTRACT_V1) {
          throw new Error("repair_contract_v2_rule_evaluation_contract");
        }
        if (!Array.isArray(contract.rule_evaluations)) {
          throw new Error("repair_contract_v2_rule_evaluations_missing");
        }
        return contract.rule_evaluations.map(normalizeRuleEvaluation);
      })()
    : null;

  result.fix_list = {
    ...result.fix_list,
    ...v2ParentFromContract(contract, canonicalIds, ruleEvaluations),
  };
  result.recommendations = (result.recommendations || []).map((fix) => ({
    ...fix,
    ...repairById.get(clean(fix?.fix_id)),
  }));
  return result;
}

function hasAnyV2ParentField(fixList = {}) {
  return Boolean(
    clean(fixList.repair_contract_version)
    || clean(fixList.repair_snapshot_contract_version)
    || fixList.repair_snapshot_contract_complete !== undefined
    || clean(fixList.repair_priority_model_version)
    || Array.isArray(fixList.canonical_action_fix_ids),
  );
}

function requireCompleteV2Parent(fixList = {}) {
  if (clean(fixList.repair_contract_version) !== REPAIR_CONTRACT_V2) throw new Error("repair_contract_v2_row_parent_contract");
  if (clean(fixList.repair_snapshot_contract_version) !== REPAIR_CONTRACT_V2) throw new Error("repair_contract_v2_row_snapshot_contract");
  if (fixList.repair_snapshot_contract_complete !== true) throw new Error("repair_contract_v2_row_snapshot_incomplete");
  if (clean(fixList.repair_priority_model_version) !== REPAIR_PRIORITY_MODEL_V2) throw new Error("repair_contract_v2_row_priority_model");
}

/**
 * Rehydrate candidate v2 signed fields from persisted rows onto a legacy
 * reconstruction. Historical rows with no v2 parent fields return unchanged.
 * Partial/mixed v2 parent state fails closed instead of being interpreted.
 */
export function rehydrateRepairContractV2Candidate(legacySnapshot, fixList = {}, fixItems = []) {
  const result = clone(legacySnapshot);
  if (!hasAnyV2ParentField(fixList)) return result;
  requireCompleteV2Parent(fixList);

  const canonicalIds = Array.isArray(fixList.canonical_action_fix_ids)
    ? fixList.canonical_action_fix_ids.map(clean).filter(Boolean)
    : [];
  const snapshotIds = (result?.recommendations || []).map((item) => clean(item?.fix_id)).filter(Boolean);
  exactIdSet(snapshotIds, canonicalIds, "repair_contract_v2_row_canonical_order");

  const rowsById = new Map();
  for (const row of fixItems || []) {
    const id = clean(row?.fix_id);
    if (!id) throw new Error("repair_contract_v2_row_missing_fix_id");
    if (rowsById.has(id)) throw new Error(`repair_contract_v2_row_duplicate_fix_id:${id}`);
    rowsById.set(id, row);
  }
  exactIdSet(snapshotIds, [...rowsById.keys()], "repair_contract_v2_row_items");

  const canonicalRank = new Map(canonicalIds.map((id, index) => [id, index + 1]));
  const identityVersion = clean(fixList.repair_identity_version);
  const verificationVersion = clean(fixList.repair_verification_version);
  if (!identityVersion) throw new Error("repair_contract_v2_row_identity_version");
  if (!verificationVersion) throw new Error("repair_contract_v2_row_verification_version");

  result.fix_list = {
    ...result.fix_list,
    repair_contract_version: REPAIR_CONTRACT_V2,
    repair_snapshot_contract_version: REPAIR_CONTRACT_V2,
    repair_snapshot_contract_complete: true,
    repair_priority_model_version: REPAIR_PRIORITY_MODEL_V2,
    repair_identity_version: identityVersion,
    repair_verification_version: verificationVersion,
    canonical_action_fix_ids: canonicalIds,
  };

  if (clean(fixList.rule_evaluation_contract_version)) {
    if (clean(fixList.rule_evaluation_contract_version) !== RULE_EVALUATION_CONTRACT_V1) {
      throw new Error("repair_contract_v2_row_rule_evaluation_contract");
    }
    if (!Array.isArray(fixList.rule_evaluations)) throw new Error("repair_contract_v2_row_rule_evaluations_missing");
    result.fix_list.rule_evaluation_contract_version = RULE_EVALUATION_CONTRACT_V1;
    result.fix_list.rule_evaluations = fixList.rule_evaluations.map(normalizeRuleEvaluation);
  }

  result.recommendations = (result.recommendations || []).map((legacyFix) => {
    const id = clean(legacyFix?.fix_id);
    const row = rowsById.get(id);
    const { normalized } = normalizeRepairAnnotation(row, {
      rank: canonicalRank.get(id),
      parentIdentityVersion: identityVersion,
      parentVerificationVersion: verificationVersion,
    });
    if (Number(row?.canonical_action_rank) !== canonicalRank.get(id)) {
      throw new Error(`repair_contract_v2_row_rank_mismatch:${id}`);
    }
    return { ...legacyFix, ...normalized };
  });
  return result;
}
