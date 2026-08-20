import { REPAIR_PRESENTATION_MODES, repairPresentationMode } from "./repairContractPresentation.js";
import { repairRowModel } from "./repairPresentation.js";

/**
 * Keep canonical evidence presentation tied to the persisted repair authority.
 *
 * Browser normalization may make harmless customer-copy changes such as a
 * friendlier title, but it must not rewrite the evidence-backed surface, scope,
 * priority reason, leverage, or verification state of a canonical repair.
 * Legacy rows retain their existing presentation behavior.
 */
export function canonicalRepairDisplayModel(item = {}, suppliedModel = null) {
  const model = suppliedModel || repairRowModel(item);
  const original = item?.original;

  if (
    repairPresentationMode(item) !== REPAIR_PRESENTATION_MODES.CANONICAL
    || !original
    || typeof original !== "object"
  ) {
    return model;
  }

  const persisted = repairRowModel(original);
  return {
    ...model,
    surface: persisted.surface,
    scope: persisted.scope,
    reason: persisted.reason,
    leverage: persisted.leverage,
    verification: persisted.verification,
    verificationKind: persisted.verificationKind,
    affectedPageCount: persisted.affectedPageCount,
    sharedRepairConfirmed: persisted.sharedRepairConfirmed,
  };
}
