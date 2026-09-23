import assert from "node:assert/strict";
import test from "node:test";

import {
  SCAN_COMPARISON_PANEL_MODEL_VERSION,
  TRUSTED_SCAN_COMPARISON_PRESENTATION_VERSION,
  buildScanComparisonPanelModel,
} from "../../src/lib/scanComparisonPanelModel.js";

function funbookerPresentation() {
  return {
    version: TRUSTED_SCAN_COMPARISON_PRESENTATION_VERSION,
    previous_scan_id: "6ab272fc6dfa7f9faf97a90f",
    current_scan_id: "6ab314008da962a9f8c58929",
    headline: "What changed since the previous scan",
    score_line: "Health score changed from 75 to 72.",
    sample_line: "The assessed sample was 126 pages before and 139 pages now.",
    score_caution: "Because the assessed sample size changed, the score difference alone does not prove the site improved or regressed. Repair-level states below use comparable repair evidence.",
    counts: {
      fixed: 0,
      still_detected: 0,
      new_or_came_back: 1,
      came_back: 0,
      could_not_verify: 6,
    },
    new_or_came_back_label: "New or returned candidate",
    new_or_came_back_is_verified_claim: false,
    score_direction_claim_allowed: false,
    overall_improvement_or_regression_claim: null,
  };
}

test("Funbooker panel preserves exact lineage and fail-closed comparison counts", () => {
  const model = buildScanComparisonPanelModel(funbookerPresentation());

  assert.equal(model.version, SCAN_COMPARISON_PANEL_MODEL_VERSION);
  assert.equal(model.state, "ready");
  assert.equal(model.previousScanId, "6ab272fc6dfa7f9faf97a90f");
  assert.equal(model.currentScanId, "6ab314008da962a9f8c58929");
  assert.deepEqual(model.counts, {
    fixed: 0,
    still_detected: 0,
    new_or_came_back: 1,
    came_back: 0,
    could_not_verify: 6,
  });
});

test("Funbooker score decrease is descriptive only when the assessed sample changed", () => {
  const model = buildScanComparisonPanelModel(funbookerPresentation());
  const rendered = JSON.stringify(model);

  assert.equal(model.scoreLine, "Health score changed from 75 to 72.");
  assert.equal(model.sampleLine, "The assessed sample was 126 pages before and 139 pages now.");
  assert.match(model.sampleScopeWarning, /sample size changed/i);
  assert.match(model.sampleScopeWarning, /does not prove/i);
  assert.equal(model.comparisonClaimAllowed, false);
  assert.equal(model.scoreDirectionClaimAllowed, false);
  assert.equal(model.overallImprovementOrRegressionClaim, null);
  assert.doesNotMatch(rendered, /worse by 3|3 points worse|regressed by 3|improved by -3/i);
});

test("new H1 remains a new-or-returned candidate rather than a verified historical claim", () => {
  const model = buildScanComparisonPanelModel(funbookerPresentation());
  const candidate = model.metrics.find((metric) => metric.key === "unmatched_current");

  assert.deepEqual(candidate, {
    key: "unmatched_current",
    label: "Not matched",
    count: 1,
  });
  assert.equal(model.newOrCameBackIsVerifiedClaim, false);
});

test("panel does not mutate the trusted historical presentation payload", () => {
  const presentation = funbookerPresentation();
  const before = structuredClone(presentation);

  buildScanComparisonPanelModel(presentation);

  assert.deepEqual(presentation, before);
});

test("raw scan comparison contracts are not accepted as presentation authority", () => {
  const model = buildScanComparisonPanelModel({
    ...funbookerPresentation(),
    version: "scan_comparison_v1",
  });

  assert.equal(model.state, "unavailable");
  assert.equal(model.reasonCode, "unsupported_presentation_version");
  assert.equal(model.comparisonClaimAllowed, false);
});

test("directional score copy fails closed even if claim flags pretend to be safe", () => {
  const model = buildScanComparisonPanelModel({
    ...funbookerPresentation(),
    score_line: "Health score is worse by 3 points.",
  });

  assert.equal(model.state, "unavailable");
  assert.equal(model.reasonCode, "directional_score_copy_not_allowed");
  assert.equal(model.comparisonClaimAllowed, false);
});

test("directional or verified-candidate flags fail closed", () => {
  for (const patch of [
    { score_direction_claim_allowed: true },
    { overall_improvement_or_regression_claim: "regressed" },
    { new_or_came_back_is_verified_claim: true },
  ]) {
    const model = buildScanComparisonPanelModel({ ...funbookerPresentation(), ...patch });
    assert.equal(model.state, "unavailable");
    assert.equal(model.reasonCode, "directional_or_verification_claim_not_allowed");
  }
});

test("missing score/sample caution context fails closed instead of silently comparing", () => {
  for (const field of ["score_line", "sample_line", "score_caution"]) {
    const presentation = funbookerPresentation();
    presentation[field] = "";
    const model = buildScanComparisonPanelModel(presentation);
    assert.equal(model.state, "unavailable");
    assert.equal(model.reasonCode, "missing_customer_context");
  }
});

test("invalid counts fail closed", () => {
  for (const badValue of [-1, 1.5, "6", null]) {
    const presentation = funbookerPresentation();
    presentation.counts = { ...presentation.counts, could_not_verify: badValue };
    const model = buildScanComparisonPanelModel(presentation);
    assert.equal(model.state, "unavailable");
    assert.equal(model.reasonCode, "invalid_counts");
  }
});

test("invalid or self-referential scan lineage fails closed", () => {
  const badWhitespace = buildScanComparisonPanelModel({
    ...funbookerPresentation(),
    previous_scan_id: " scan-old ",
  });
  assert.equal(badWhitespace.state, "unavailable");
  assert.equal(badWhitespace.reasonCode, "invalid_scan_lineage");

  const sameId = buildScanComparisonPanelModel({
    ...funbookerPresentation(),
    previous_scan_id: "same-scan",
    current_scan_id: "same-scan",
  });
  assert.equal(sameId.state, "unavailable");
  assert.equal(sameId.reasonCode, "invalid_scan_lineage");
});

test("unavailable models keep comparison and historical mutation claims disabled", () => {
  const model = buildScanComparisonPanelModel(null);

  assert.equal(model.state, "unavailable");
  assert.equal(model.comparisonClaimAllowed, false);
  assert.equal(model.historicalRowsMutable, false);
});

test("verified returned findings are not counted again as unmatched current findings", () => {
  const data = funbookerPresentation();
  data.counts.came_back = 2;
  data.counts.new_or_came_back = 3;
  const model = buildScanComparisonPanelModel(data);
  assert.equal(model.state, "ready");
  assert.equal(model.metrics.find((item) => item.key === "came_back")?.count, 2);
  assert.equal(model.metrics.find((item) => item.key === "unmatched_current")?.count, 1);
  assert.equal(model.counts.new_or_came_back, 3);
});

test("contradictory returned and candidate totals cannot become customer counts", () => {
  const data = funbookerPresentation();
  data.counts.came_back = 2;
  data.counts.new_or_came_back = 1;
  assert.equal(buildScanComparisonPanelModel(data).state, "unavailable");
});
