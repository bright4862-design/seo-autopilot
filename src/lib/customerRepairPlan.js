import * as legacy from "./customerRepairPlanLegacy.js";

export * from "./customerRepairPlanLegacy.js";

const STAGE3_PRIORITY_VERSION = "repair_priority_v3_four_factor_v1";

function clean(value) {
  return String(value ?? "").trim();
}

function isStage3Card(card) {
  return Boolean(
    card
    && typeof card === "object"
    && card.priorityFactors?.version === STAGE3_PRIORITY_VERSION
    && card.stage3Counts
    && typeof card.stage3Counts === "object"
  );
}

/**
 * The authenticated Stage-3 reader already supplies Python-owned order after
 * rank-before-truncate. Preserve that order exactly; the browser must not
 * reconstruct priority from legacy action bands. Historical cards keep the
 * existing plan ordering unchanged.
 */
export function buildCustomerRepairPlan(cards = [], { fallbackNextBestStep = "" } = {}) {
  const source = Array.isArray(cards) ? cards.filter(Boolean) : [];
  if (source.length === 0 || !source.every(isStage3Card)) {
    return legacy.buildCustomerRepairPlan(cards, { fallbackNextBestStep });
  }
  const first = source[0] || {};
  const nextBestStep = clean(first.whatToChange || first.what_to_change || first.title)
    || clean(fallbackNextBestStep);
  return {
    cards: [...source],
    fixFirstCount: source.filter((card) => clean(card.actionPriority || card.action_priority).toLowerCase() === "fix_first").length,
    nextBestStep,
  };
}
