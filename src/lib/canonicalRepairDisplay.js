import { REPAIR_PRESENTATION_MODES, repairPresentationMode } from "./repairContractPresentation.js";
import { repairRowModel } from "./repairPresentation.js";

function qualifyCanonicalScope(scope = "", affectedPageCount = 0) {
  const value = String(scope || "").trim();
  if (!/^\d+ pages?$/.test(value)) return value;

  const count = Math.max(0, Number(affectedPageCount) || 0);
  if (count === 1) return "1 affected page found in this scan";
  if (count > 1) return `${count} affected pages found in this scan`;
  return value;
}

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

  if (repairPresentationMode(item) !== REPAIR_PRESENTATION_MODES.CANONICAL) {
    return model;
  }

  if (!original || typeof original !== "object") {
    return {
      ...model,
      scope: qualifyCanonicalScope(model.scope, model.affectedPageCount),
    };
  }

  const persisted = repairRowModel(original);
  return {
    ...model,
    surface: persisted.surface,
    scope: qualifyCanonicalScope(persisted.scope, persisted.affectedPageCount),
    reason: persisted.reason,
    leverage: persisted.leverage,
    verification: persisted.verification,
    verificationKind: persisted.verificationKind,
    affectedPageCount: persisted.affectedPageCount,
    sharedRepairConfirmed: persisted.sharedRepairConfirmed,
  };
}
