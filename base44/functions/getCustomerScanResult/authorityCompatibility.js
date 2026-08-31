import {
  REPAIR_CONTRACT_V2,
  REPAIR_PRIORITY_MODEL_V2,
} from "./projection.js";

/**
 * Saved authoritative results are compatible by persisted contract shape, not
 * by today's deployment fingerprint. The fingerprint is still part of the
 * signed snapshot and must be present/valid; deployment exactness is enforced
 * elsewhere by the release operator.
 */
export const READABLE_AUTHORITY_SEAL_VERSIONS = new Set([
  "standard_review_snapshot_hmac_v1",
  "standard_review_snapshot_hmac_v2_coverage",
  "standard_review_snapshot_hmac_v3_acceptance_evidence",
]);

function text(value, limit = 160) {
  return typeof value === "string" ? value.trim().slice(0, limit) : "";
}

function validFingerprint(value) {
  return /^[a-f0-9]{16}$/.test(text(value, 32));
}

function repairShape(value) {
  const contract = text(value?.repair_contract_version);
  const snapshot = text(value?.repair_snapshot_contract_version);
  const priority = text(value?.repair_priority_model_version);
  const complete = value?.repair_snapshot_contract_complete;

  const entirelyLegacy = !contract && !snapshot && !priority && complete !== true;
  if (entirelyLegacy) return "legacy";

  const canonicalV2 = contract === REPAIR_CONTRACT_V2
    && snapshot === REPAIR_CONTRACT_V2
    && priority === REPAIR_PRIORITY_MODEL_V2
    && complete === true;
  return canonicalV2 ? "canonical_v2" : "unsupported";
}

export function isReadableAuthorityContract({ run, fixList, fixItems = [] } = {}) {
  if (!READABLE_AUTHORITY_SEAL_VERSIONS.has(text(run?.authority_seal_version))) return false;
  if (!validFingerprint(run?.beta_revision_fingerprint)) return false;

  const listShape = repairShape(fixList);
  if (listShape === "unsupported") return false;

  const items = Array.isArray(fixItems) ? fixItems : [];
  for (const item of items) {
    if (repairShape(item) !== listShape) return false;
  }
  return true;
}
