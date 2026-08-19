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

/**
 * One durable FixList snapshot has one presentation authority.
 *
 * A single unsupported row makes the snapshot unsupported. A fully supported
 * snapshot may use canonical action priority. Any mixture of canonical and
 * historical/no-contract rows remains legacy so the customer never sees two
 * ranking authorities inside one saved scan.
 */
export function repairSnapshotPresentationMode(items = []) {
  const list = Array.isArray(items) ? items.filter(Boolean) : [];
  if (list.length === 0) return REPAIR_PRESENTATION_MODES.LEGACY;

  const modes = list.map((item) => repairPresentationMode(item));
  if (modes.some((mode) => mode === REPAIR_PRESENTATION_MODES.UNSUPPORTED)) {
    return REPAIR_PRESENTATION_MODES.UNSUPPORTED;
  }
  if (modes.every((mode) => mode === REPAIR_PRESENTATION_MODES.CANONICAL)) {
    return REPAIR_PRESENTATION_MODES.CANONICAL;
  }
  return REPAIR_PRESENTATION_MODES.LEGACY;
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
