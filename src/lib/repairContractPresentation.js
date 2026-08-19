export const SUPPORTED_REPAIR_CONTRACTS = Object.freeze([
  "repair_contract_v2_shadow_calibrated",
]);

export const REPAIR_PRESENTATION_MODES = Object.freeze({
  CANONICAL: "canonical_repair_contract",
  LEGACY: "legacy_frozen",
  UNSUPPORTED: "unsupported_contract",
});

export const CANONICAL_ACTION_PRIORITIES = Object.freeze([
  "fix_first",
  "important",
  "improve",
  "review",
]);

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

export function repairSnapshotContractVersionOf(item = {}) {
  return clean(
    item.repairSnapshotContractVersion
      || item.repair_snapshot_contract_version
      || item.original?.repair_snapshot_contract_version,
  );
}

export function repairSnapshotContractComplete(item = {}) {
  return item.repairSnapshotContractComplete === true
    || item.repair_snapshot_contract_complete === true
    || item.original?.repair_snapshot_contract_complete === true;
}

export function explicitCanonicalActionPriorityOf(item = {}) {
  const value = clean(
    item.actionPriority
      || item.action_priority
      || item.original?.action_priority,
  ).toLowerCase();
  return CANONICAL_ACTION_PRIORITIES.includes(value) ? value : "";
}

/**
 * A row-level contract is not enough to switch a saved FixList into canonical
 * presentation. The persisted row must also carry an explicit snapshot-level
 * attestation proving the entire durable FixList used the same supported
 * contract. This prevents Done/deferred/filter state from manufacturing
 * canonical authority out of a mixed historical snapshot.
 *
 * A fully attested row must also carry an explicit valid persisted
 * `action_priority`. The frontend may not derive a canonical band from legacy
 * severity or another fallback when the server-owned field is missing.
 */
export function repairPresentationMode(item = {}) {
  const version = repairContractVersionOf(item);
  const snapshotVersion = repairSnapshotContractVersionOf(item);
  const snapshotComplete = repairSnapshotContractComplete(item);

  if (!version && !snapshotVersion) return REPAIR_PRESENTATION_MODES.LEGACY;
  if (version && !SUPPORTED_REPAIR_CONTRACTS.includes(version)) {
    return REPAIR_PRESENTATION_MODES.UNSUPPORTED;
  }
  if (snapshotVersion && !SUPPORTED_REPAIR_CONTRACTS.includes(snapshotVersion)) {
    return REPAIR_PRESENTATION_MODES.UNSUPPORTED;
  }
  if (version && snapshotVersion && version !== snapshotVersion) {
    return REPAIR_PRESENTATION_MODES.UNSUPPORTED;
  }

  // Transitional rows with a supported row contract but no complete persisted
  // snapshot attestation stay legacy. They may never activate canonical UI by
  // inference alone.
  if (!version || !snapshotVersion || !snapshotComplete) {
    return REPAIR_PRESENTATION_MODES.LEGACY;
  }

  if (!explicitCanonicalActionPriorityOf(item)) {
    return REPAIR_PRESENTATION_MODES.UNSUPPORTED;
  }

  return REPAIR_PRESENTATION_MODES.CANONICAL;
}

/**
 * One durable FixList snapshot has one presentation authority.
 *
 * A single unsupported row makes the snapshot unsupported. A fully attested,
 * supported snapshot may use canonical action priority. Any mixture of
 * canonical and historical/no-contract rows remains legacy so the customer
 * never sees two ranking authorities inside one saved scan.
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
 * - Fully snapshot-attested supported repairs may consume persisted canonical
 *   action_priority.
 * - Repairs with no contract remain in frozen legacy presentation mode.
 * - Supported row contracts without snapshot attestation also remain legacy.
 * - Missing canonical action priority on an otherwise attested row fails closed.
 * - Unknown, superseded, or mismatched contracts fail closed.
 */
export function repairPresentationContract(item = {}) {
  const version = repairContractVersionOf(item);
  const snapshotVersion = repairSnapshotContractVersionOf(item);
  const snapshotComplete = repairSnapshotContractComplete(item);
  const actionPriority = explicitCanonicalActionPriorityOf(item);
  const mode = repairPresentationMode(item);
  return {
    version,
    snapshotVersion,
    snapshotComplete,
    actionPriority,
    mode,
    canonicalActionPriorityAllowed: mode === REPAIR_PRESENTATION_MODES.CANONICAL,
    frozenLegacyPresentation: mode === REPAIR_PRESENTATION_MODES.LEGACY,
    unsupported: mode === REPAIR_PRESENTATION_MODES.UNSUPPORTED,
  };
}
