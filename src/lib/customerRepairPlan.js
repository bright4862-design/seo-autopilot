import * as legacy from "./customerRepairPlanLegacy.js";

export * from "./customerRepairPlanLegacy.js";

const STAGE3_PRIORITY_VERSION = "repair_priority_v3_four_factor_v1";
const STAGE3_DEGRADED_PRESENTATION_MODE = "stage3_per_row_degraded_v1";

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

function stage3Plan(source, { fallbackNextBestStep = "", completeCount = source.length } = {}) {
  const first = source[0] || {};
  const nextBestStep = clean(first.whatToChange || first.what_to_change || first.title)
    || clean(fallbackNextBestStep);
  const plan = {
    cards: [...source],
    fixFirstCount: source.filter((card) => clean(card.actionPriority || card.action_priority).toLowerCase() === "fix_first").length,
    nextBestStep,
  };
  if (completeCount < source.length) {
    return {
      ...plan,
      presentation_mode: STAGE3_DEGRADED_PRESENTATION_MODE,
      row_coverage: {
        total_rows: source.length,
        stage3_complete_rows: completeCount,
        degraded_rows: source.length - completeCount,
      },
    };
  }
  return plan;
}

/**
 * The authenticated Stage-3 reader already supplies Python-owned order after
 * rank-before-truncate. Preserve that order exactly; the browser must not
 * reconstruct priority from legacy action bands. A malformed Stage-3 row may
 * lose only its own Stage-3 presentation fields; it must not force valid
 * neighbours through the historical sorter. Historical card batches with no
 * valid Stage-3 row keep the existing plan ordering unchanged.
 */
export function buildCustomerRepairPlan(cards = [], { fallbackNextBestStep = "" } = {}) {
  const source = Array.isArray(cards) ? cards.filter(Boolean) : [];
  const completeCount = source.filter(isStage3Card).length;
  if (source.length === 0 || completeCount === 0) {
    return legacy.buildCustomerRepairPlan(cards, { fallbackNextBestStep });
  }
  return stage3Plan(source, { fallbackNextBestStep, completeCount });
}
