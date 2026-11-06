// New optional signed repair sub-contract. Historical v2 snapshots omit it
// byte-for-byte; the parent marker selects it only for new, complete scans.
export const SIGNED_ARCHITECTURE_CONTEXT_VERSION = "repair_architecture_signed_context_v1_role_first";
export const SIGNED_ARCHITECTURE_PRIORITY_VERSION = "repair_architecture_priority_v2_provenance_shadow";
export const SIGNED_ARCHITECTURE_SCORE_POLICY = "architecture_score_policy_v2_role_first";

const ROLE_KEYS = Object.freeze([
  "structural", "business_critical", "commercial_leaf", "support", "other",
]);
const REACH_VALUES = new Set(["structural", "broad_in_sample", "repeated", "isolated"]);

export function signedArchitecturePriorityContext(value, contractVersion = "") {
  if (!contractVersion) return {};
  if (contractVersion !== SIGNED_ARCHITECTURE_CONTEXT_VERSION) {
    throw new Error("Unsupported signed architecture context version");
  }
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : null;
  const counts = source?.architecture_role_counts;
  if (
    !source
    || source.architecture_priority_version !== SIGNED_ARCHITECTURE_PRIORITY_VERSION
    || source.architecture_score_policy_version !== SIGNED_ARCHITECTURE_SCORE_POLICY
    || !counts || typeof counts !== "object" || Array.isArray(counts)
    || ROLE_KEYS.some((key) => !Number.isSafeInteger(counts[key]) || counts[key] < 0 || counts[key] > 150)
    || Object.keys(counts).some((key) => !ROLE_KEYS.includes(key))
    || ROLE_KEYS.reduce((sum, key) => sum + counts[key], 0) > 150
    || !Number.isSafeInteger(source.architecture_role_bonus)
    || source.architecture_role_bonus < 0 || source.architecture_role_bonus > 63
    || !REACH_VALUES.has(source.repair_reach)
    || ((counts.structural > 0 || counts.business_critical > 0) !== (source.repair_reach === "structural"))
  ) {
    throw new Error("Signed architecture context is missing or inconsistent");
  }
  return {
    architecture_priority_version: SIGNED_ARCHITECTURE_PRIORITY_VERSION,
    architecture_score_policy_version: SIGNED_ARCHITECTURE_SCORE_POLICY,
    architecture_role_counts: Object.fromEntries(ROLE_KEYS.map((key) => [key, counts[key]])),
    architecture_role_bonus: source.architecture_role_bonus,
    repair_reach: source.repair_reach,
  };
}
