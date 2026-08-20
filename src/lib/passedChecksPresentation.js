export const PASSED_CHECKS_PRESENTATION_VERSION = "passed_checks_presentation_v1_explicit_evidence";
export const SUPPORTED_RULE_EVALUATION_CONTRACT = "rule_evaluation_v1_explicit";

const CHECK_DEFINITIONS = Object.freeze([
  {
    key: "broken_pages",
    rules: ["404_error", "broken_page"],
    label: "No broken pages found in the pages we checked",
  },
  {
    key: "search_titles",
    rules: ["meta_title"],
    label: "Search titles look good on the pages we checked",
  },
  {
    key: "search_descriptions",
    rules: ["meta_description"],
    label: "Search descriptions look good on the pages we checked",
  },
  {
    key: "canonicals",
    rules: ["canonical"],
    label: "Canonical settings look right on the pages we checked",
  },
  {
    key: "image_descriptions",
    rules: ["image_alt_text", "alt_text"],
    label: "Images have text descriptions on the pages we checked",
  },
  {
    key: "structured_data",
    rules: ["schema"],
    label: "No missing trust signals on the pages we checked",
  },
  {
    key: "duplicate_search_text",
    rules: ["duplicate_content"],
    label: "No duplicate search text found in the pages we checked",
  },
  {
    key: "internal_links",
    rules: ["internal_link"],
    label: "No internal link problems found in the pages we checked",
  },
  {
    key: "indexability",
    rules: ["indexability"],
    label: "Google can index the pages we checked",
  },
]);

function clean(value = "") {
  return String(value || "").trim().toLowerCase();
}

function evaluationContractOf(scan = {}) {
  return String(
    scan.rule_evaluation_contract_version
      || scan.ruleEvaluationContractVersion
      || "",
  ).trim();
}

function evaluationsOf(scan = {}) {
  const value = scan.rule_evaluations || scan.ruleEvaluations || [];
  return Array.isArray(value) ? value.filter(Boolean) : [];
}

function ruleOf(evaluation = {}) {
  return clean(evaluation.rule || evaluation.rule_id || evaluation.category);
}

function explicitPass(evaluation = {}) {
  return evaluation.evaluated === true
    && evaluation.applicable === true
    && evaluation.passed === true;
}

function explicitNonPass(evaluation = {}) {
  return evaluation.evaluated === false
    || evaluation.applicable === false
    || evaluation.passed === false;
}

function evaluationsByRule(scan = {}) {
  const grouped = new Map();
  for (const evaluation of evaluationsOf(scan)) {
    const rule = ruleOf(evaluation);
    if (!rule) continue;
    const rows = grouped.get(rule) || [];
    rows.push(evaluation);
    grouped.set(rule, rows);
  }
  return grouped;
}

/**
 * Build customer-facing "Already good" claims only from explicit evaluation
 * evidence. Absence of a repair/finding is never interpreted as a pass.
 *
 * Fail-closed rules:
 * - unsupported/missing evaluation contract -> no claims
 * - rule not evaluated -> no claim
 * - rule not applicable -> no claim
 * - mixed/failed evaluation rows -> no claim
 * - only evaluated=true + applicable=true + passed=true may support a claim
 *
 * A definition with multiple rule aliases is considered passed when at least
 * one alias has an explicit pass and none of its observed aliases explicitly
 * reports non-pass. This supports historical naming aliases without treating
 * missing aliases as failures or successes.
 */
export function buildExplicitPassedChecks(scan = {}) {
  if (evaluationContractOf(scan) !== SUPPORTED_RULE_EVALUATION_CONTRACT) return [];

  const grouped = evaluationsByRule(scan);
  const claims = [];

  for (const definition of CHECK_DEFINITIONS) {
    const observed = definition.rules.flatMap((rule) => grouped.get(rule) || []);
    if (observed.length === 0) continue;
    if (observed.some(explicitNonPass)) continue;
    if (!observed.some(explicitPass)) continue;

    claims.push({
      key: definition.key,
      label: definition.label,
      presentation_version: PASSED_CHECKS_PRESENTATION_VERSION,
      evidence: {
        evaluation_contract_version: SUPPORTED_RULE_EVALUATION_CONTRACT,
        evaluated_rules: Array.from(new Set(observed.map(ruleOf).filter(Boolean))),
      },
    });
  }

  return claims;
}
