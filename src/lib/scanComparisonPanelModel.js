export const SCAN_COMPARISON_PANEL_MODEL_VERSION = "scan_comparison_panel_model_v1";
export const TRUSTED_SCAN_COMPARISON_PRESENTATION_VERSION = "scan_comparison_presentation_v1";

const COUNT_KEYS = Object.freeze([
  "fixed",
  "still_detected",
  "new_or_came_back",
  "came_back",
  "could_not_verify",
]);

const DIRECTIONAL_SCORE_COPY = /\b(?:better|worse|improved|improvement|regressed|regression|declined|deteriorated|up by|down by)\b/i;

function unavailable(reasonCode) {
  return Object.freeze({
    version: SCAN_COMPARISON_PANEL_MODEL_VERSION,
    state: "unavailable",
    reasonCode,
    headline: "Comparison unavailable",
    message: "This rescan comparison cannot be shown because its verified comparison presentation is unavailable or invalid.",
    comparisonClaimAllowed: false,
    historicalRowsMutable: false,
  });
}

function exactScanId(value) {
  return typeof value === "string"
    && value.length > 0
    && value.length <= 256
    && value === value.trim();
}

function nonnegativeInteger(value) {
  return Number.isInteger(value) && value >= 0;
}

function nonemptyString(value) {
  return typeof value === "string" && value.trim().length > 0;
}

/**
 * Build a standalone customer panel model from the server-owned, validated
 * scan-comparison presentation contract.
 *
 * This helper is presentation-only. It does not inspect raw FixItems, compare
 * fingerprints, recompute score deltas, infer repair state, or decide whether a
 * site improved/regressed. Those decisions stay behind the canonical Python
 * comparison + integrity boundary. Invalid or directionally unsafe presentation
 * payloads fail closed to an unavailable panel.
 */
export function buildScanComparisonPanelModel(presentation = {}) {
  if (!presentation || typeof presentation !== "object" || Array.isArray(presentation)) {
    return unavailable("presentation_not_object");
  }
  if (presentation.version !== TRUSTED_SCAN_COMPARISON_PRESENTATION_VERSION) {
    return unavailable("unsupported_presentation_version");
  }
  if (!exactScanId(presentation.previous_scan_id) || !exactScanId(presentation.current_scan_id)) {
    return unavailable("invalid_scan_lineage");
  }
  if (presentation.previous_scan_id === presentation.current_scan_id) {
    return unavailable("invalid_scan_lineage");
  }
  if (presentation.score_direction_claim_allowed !== false
      || presentation.overall_improvement_or_regression_claim !== null
      || presentation.new_or_came_back_is_verified_claim !== false) {
    return unavailable("directional_or_verification_claim_not_allowed");
  }
  if (!nonemptyString(presentation.score_line)
      || !nonemptyString(presentation.sample_line)
      || !nonemptyString(presentation.score_caution)) {
    return unavailable("missing_customer_context");
  }
  if (DIRECTIONAL_SCORE_COPY.test(presentation.score_line)) {
    return unavailable("directional_score_copy_not_allowed");
  }

  const counts = presentation.counts;
  if (!counts || typeof counts !== "object" || Array.isArray(counts)) {
    return unavailable("invalid_counts");
  }
  for (const key of COUNT_KEYS) {
    if (!nonnegativeInteger(counts[key])) return unavailable("invalid_counts");
  }

  const safeCounts = Object.freeze(Object.fromEntries(COUNT_KEYS.map((key) => [key, counts[key]])));
  const metrics = Object.freeze([
    Object.freeze({ key: "fixed", label: "Fixed", count: safeCounts.fixed }),
    Object.freeze({ key: "still_detected", label: "Still detected", count: safeCounts.still_detected }),
    Object.freeze({ key: "new_or_came_back", label: "New or returned candidate", count: safeCounts.new_or_came_back }),
    Object.freeze({ key: "could_not_verify", label: "Could not verify", count: safeCounts.could_not_verify }),
  ]);

  return Object.freeze({
    version: SCAN_COMPARISON_PANEL_MODEL_VERSION,
    sourcePresentationVersion: presentation.version,
    state: "ready",
    previousScanId: presentation.previous_scan_id,
    currentScanId: presentation.current_scan_id,
    headline: "What changed since the previous scan",
    scoreLine: presentation.score_line.trim(),
    sampleLine: presentation.sample_line.trim(),
    sampleScopeWarning: presentation.score_caution.trim(),
    counts: safeCounts,
    metrics,
    comparisonClaimAllowed: false,
    scoreDirectionClaimAllowed: false,
    newOrCameBackIsVerifiedClaim: false,
    overallImprovementOrRegressionClaim: null,
    historicalRowsMutable: false,
  });
}
