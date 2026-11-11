import * as legacy from "./repairCardModelLegacy.js";

export * from "./repairCardModelLegacy.js";

const STAGE3_PRIORITY_VERSION = "repair_priority_v3_four_factor_v1";
const STAGE3_PRESENTATION_ORIGIN = Symbol.for("fixlist.stage3.presentation_origin");

const plainObject = (value) => value && typeof value === "object" && !Array.isArray(value) ? value : null;
const finiteOrNull = (value, min, max) => value === null
  ? null
  : (typeof value === "number" && Number.isFinite(value) && value >= min && value <= max ? value : undefined);
const integerOrNull = (value, min = 0) => value === null
  ? null
  : (Number.isInteger(value) && value >= min ? value : undefined);
const textOrNull = (value) => value === null
  ? null
  : (typeof value === "string" ? value : undefined);

function normalizePriorityFactors(value) {
  const source = plainObject(value);
  if (!source || source.version !== STAGE3_PRIORITY_VERSION) return null;
  const impact = Number.isInteger(source.impact) && source.impact >= 0 && source.impact <= 5 ? source.impact : undefined;
  const reach = finiteOrNull(source.reach, 0, 1);
  const pageValue = finiteOrNull(source.page_value, 0, 1);
  const confidence = finiteOrNull(source.confidence, 0, 1);
  const score = finiteOrNull(source.priority_factor_score, 0, 5);
  const affected = integerOrNull(source.reach_affected_indexable);
  const denominator = integerOrNull(source.reach_observed_indexable_family);
  if ([impact, reach, pageValue, confidence, score, affected, denominator].some((item) => item === undefined)) return null;
  if (affected !== null && denominator !== null && affected > denominator) return null;
  if (!Array.isArray(source.explanation) || source.explanation.some((item) => typeof item !== "string")) return null;
  const textFields = [
    "impact_reason", "reach_state", "page_value_state", "page_value_role",
    "page_value_source", "confidence_state", "score_state",
    "technical_base_severity", "technical_severity_source",
  ];
  const output = {
    version: STAGE3_PRIORITY_VERSION,
    impact,
    reach,
    page_value: pageValue,
    confidence,
    priority_factor_score: score,
    reach_affected_indexable: affected,
    reach_observed_indexable_family: denominator,
    explanation: [...source.explanation],
  };
  for (const field of textFields) {
    const normalized = textOrNull(source[field]);
    if (normalized === undefined) return null;
    output[field] = normalized;
  }
  return output;
}

function normalizeStage3Counts(value) {
  const source = plainObject(value);
  if (!source) return null;
  const unique = integerOrNull(source.unique_affected_page_count);
  const observations = integerOrNull(source.observation_count);
  const population = integerOrNull(source.known_population_count);
  const displayed = integerOrNull(source.displayed_sample_count);
  const truncated = integerOrNull(source.truncated_sample_count);
  if ([unique, observations, population, displayed, truncated].some((item) => item === undefined)) return null;
  if (unique === null || displayed === null || truncated === null) return null;
  if (population !== null && population < unique) return null;
  if (!Array.isArray(source.displayed_samples) || source.displayed_samples.some((item) => typeof item !== "string")) return null;
  if (displayed !== source.displayed_samples.length || truncated !== unique - displayed) return null;
  if (source.examples_partial !== (displayed < unique)) return null;
  return {
    unique_affected_page_count: unique,
    observation_count: observations,
    known_population_count: population,
    displayed_sample_count: displayed,
    displayed_samples: [...source.displayed_samples],
    examples_partial: source.examples_partial === true,
    truncated_sample_count: truncated,
  };
}

function stage3Fields(item) {
  const priorityFactors = normalizePriorityFactors(item?.stage3_priority_factors);
  const stage3Counts = normalizeStage3Counts(item?.stage3_counts);
  return priorityFactors && stage3Counts ? { priorityFactors, stage3Counts } : null;
}

function hasStage3PresentationSignal(item) {
  return Boolean(
    item?.stage3_priority_factors !== undefined
      || item?.stage3_counts !== undefined,
  );
}

function markStage3PresentationOrigin(card) {
  Object.defineProperty(card, STAGE3_PRESENTATION_ORIGIN, {
    value: true,
    enumerable: false,
    configurable: false,
    writable: false,
  });
  return card;
}

export function hasStage3PresentationOrigin(card) {
  return Boolean(
    card
      && typeof card === "object"
      && card[STAGE3_PRESENTATION_ORIGIN] === true,
  );
}

export function buildRepairCard(item = {}) {
  const base = legacy.buildRepairCard(item);
  const stage3 = stage3Fields(item);
  const card = stage3 ? { ...base, ...stage3 } : base;
  // Retain the row identity for a server-owned shortlist. Historical merged
  // cards continue to use their existing mergedFromFixIds identities.
  if (typeof (item.fix_id || item.id) === "string" && (item.fix_id || item.id)) card.fixId = item.fix_id || item.id;
  const estimates = item.template_impact_estimates || item.original?.template_impact_estimates;
  if (Array.isArray(estimates)) {
    const qualified = estimates.filter(value => value?.is_extrapolation === true
      && Number.isInteger(value.checked_sample_count) && value.checked_sample_count >= 3
      && value.observed_affected_count === value.checked_sample_count
      && Number.isInteger(value.inventory_count) && value.inventory_count > value.checked_sample_count
      && value.estimated_affected_page_count === value.inventory_count
      && typeof value.qualification === "string" && value.qualification.trim());
    if (qualified.length) card.templateImpactEstimates = qualified.slice(0, 10);
  }
  return hasStage3PresentationSignal(item)
    ? markStage3PresentationOrigin(card)
    : card;
}

/**
 * Current Stage-3 rows arrive in Python-owned rank order after the authenticated
 * V8 reader. Do not merge or re-rank them in the browser. If one Stage-3 row is
 * malformed, degrade that row only: valid neighbouring rows must keep their
 * authenticated Stage-3 presentation fields and source order. Historical
 * batches with no Stage-3 signal retain the existing repair-fingerprint merge
 * behavior unchanged. A non-enumerable origin marker survives local planning
 * without becoming customer-visible payload truth.
 */
export function buildRepairCards(items = []) {
  const source = Array.isArray(items) ? items.filter((item) => item && typeof item === "object") : [];
  if (source.length > 0 && source.some((item) => hasStage3PresentationSignal(item))) {
    return source.map((item) => buildRepairCard(item));
  }
  return legacy.buildRepairCards(items);
}
