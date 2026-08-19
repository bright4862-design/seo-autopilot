export const SUPPORTED_REPAIR_CONTRACTS = Object.freeze([
  "repair_contract_v2_shadow_calibrated",
]);

export const REPAIR_PRESENTATION_MODES = Object.freeze({
  CANONICAL: "canonical_repair_contract",
  LEGACY: "legacy_frozen",
  UNSUPPORTED: "unsupported_contract",
});

function clean(value = "") {
  return String(value || "").trim();
}

export function repairContractVersionOf(item = {}) {
  return clean(
    item.repairContractVersion
      || item.repair_contract_version
      || item.original?.repair_contract_version,
  );
}

export function repairPresentationMode(item = {}) {
  const version = repairContractVersionOf(item);
  if (!version) return REPAIR_PRESENTATION_MODES.LEGACY;
  if (SUPPORTED_REPAIR_CONTRACTS.includes(version)) return REPAIR_PRESENTATION_MODES.CANONICAL;
  return REPAIR_PRESENTATION_MODES.UNSUPPORTED;
}

export function canConsumeCanonicalActionPriority(item = {}) {
  return repairPresentationMode(item) === REPAIR_PRESENTATION_MODES.CANONICAL;
}

/**
 * Historical scans must not be silently reinterpreted by whichever prioritizer
 * happens to be current when the user opens them later.
 *
 * - Supported versioned repairs may consume persisted canonical action_priority.
 * - Repairs with no contract remain in frozen legacy presentation mode.
 * - Unknown or superseded contracts fail closed until the UI explicitly
 *   supports them.
 *
 * This helper is intentionally additive. The live FixList page does not switch
 * presentation modes unless the persisted repair contract is explicitly listed
 * above. The original v1 shadow contract is intentionally unsupported after
 * calibration proved its base-severity fallback could inherit reach-inflated
 * legacy priority.
 */
export function repairPresentationContract(item = {}) {
  const version = repairContractVersionOf(item);
  const mode = repairPresentationMode(item);
  return {
    version,
    mode,
    canonicalActionPriorityAllowed: mode === REPAIR_PRESENTATION_MODES.CANONICAL,
    frozenLegacyPresentation: mode === REPAIR_PRESENTATION_MODES.LEGACY,
    unsupported: mode === REPAIR_PRESENTATION_MODES.UNSUPPORTED,
  };
}
