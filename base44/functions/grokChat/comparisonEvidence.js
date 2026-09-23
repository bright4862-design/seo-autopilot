import { PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION, publishedEvidenceUrlKey } from "./evidenceUrlIdentity.js";

export const MISSING_H1_COMPARISON_EVIDENCE_VERSION = "scan_comparison_evidence_v1_missing_h1";
export const MISSING_H1_RULE = "missing_h1";
export const MISSING_H1_RULE_DEFINITION_VERSION = "missing_h1_rule_v1_usable_html_h1_count_zero";
export const MISSING_H1_COMPARISON_PROFILE_VERSION = "missing_h1_comparison_v1_exact_affected_pages";

const object = (value) => value && typeof value === "object" && !Array.isArray(value) ? value : null;
const text = (value, limit) => typeof value === "string" ? value.trim().slice(0, limit) : "";
const exactKeys = (value, keys) => {
  const source = object(value);
  return Boolean(source && Object.keys(source).length === keys.length && keys.every((key) => Object.hasOwn(source, key)));
};
const nonNegativeInt = (value, maximum = Number.MAX_SAFE_INTEGER) => (
  Number.isInteger(value) && value >= 0 && value <= maximum ? value : null
);

export function sanitizeComparisonEvidence(value, { scanOrigin = "", identityVersion = "" } = {}) {
  const source = object(value);
  if (!source || !source.version) return {};
  const outerKeys = [
    "version", "rule", "rule_definition_version", "comparison_profile_version",
    "evidence_url_identity_version", "observation_count", "evaluated_page_count",
    "finding_present_count", "finding_absent_count", "observations",
  ];
  if (!exactKeys(source, outerKeys)
      || source.version !== MISSING_H1_COMPARISON_EVIDENCE_VERSION
      || source.rule !== MISSING_H1_RULE
      || source.rule_definition_version !== MISSING_H1_RULE_DEFINITION_VERSION
      || source.comparison_profile_version !== MISSING_H1_COMPARISON_PROFILE_VERSION
      || source.evidence_url_identity_version !== PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION
      || identityVersion !== PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION
      || !text(scanOrigin, 2_000)) {
    throw new Error("Missing-H1 comparison evidence contract is invalid");
  }

  const rows = Array.isArray(source.observations) ? source.observations : null;
  if (!rows || rows.length > 150 || nonNegativeInt(source.observation_count, 150) !== rows.length) {
    throw new Error("Missing-H1 comparison observation population is invalid");
  }

  const observationKeys = [
    "page_url", "status_code", "content_type", "page_evidence_class", "indexable",
    "robots", "h1_count", "evaluated", "applicable", "finding_present",
  ];
  const seen = new Set();
  const observations = [];
  let evaluatedCount = 0;
  let presentCount = 0;
  let absentCount = 0;

  for (const row of rows) {
    if (!exactKeys(row, observationKeys)) throw new Error("Missing-H1 comparison observation shape is invalid");
    const pageUrl = text(row.page_url, 2_000);
    if (!pageUrl || !pageUrl.startsWith(`${scanOrigin}/`)
        || publishedEvidenceUrlKey(pageUrl, { scanOrigin }) !== pageUrl || seen.has(pageUrl)) {
      throw new Error("Missing-H1 comparison page identity is invalid");
    }
    seen.add(pageUrl);

    const statusCode = nonNegativeInt(row.status_code, 599);
    const contentType = text(row.content_type, 200);
    const evidenceClass = text(row.page_evidence_class, 80);
    const indexable = row.indexable;
    const robots = text(row.robots, 500);
    const h1Count = row.h1_count === null ? null : nonNegativeInt(row.h1_count, 10_000);
    const evaluated = row.evaluated;
    const applicable = row.applicable;
    const findingPresent = row.finding_present;

    if (statusCode === null || !evidenceClass
        || (indexable !== null && typeof indexable !== "boolean")
        || typeof evaluated !== "boolean" || typeof applicable !== "boolean"
        || (row.h1_count !== null && h1Count === null)) {
      throw new Error("Missing-H1 comparison observation values are invalid");
    }
    if (evaluated) {
      if (!applicable || evidenceClass !== "usable_html" || statusCode !== 200
          || h1Count === null || typeof findingPresent !== "boolean"
          || findingPresent !== (h1Count === 0)) {
        throw new Error("Missing-H1 comparison evaluated state is inconsistent");
      }
      evaluatedCount += 1;
      if (findingPresent) presentCount += 1;
      else absentCount += 1;
    } else if (applicable || findingPresent !== null) {
      throw new Error("Missing-H1 comparison unevaluated state is inconsistent");
    }

    observations.push({
      page_url: pageUrl,
      status_code: statusCode,
      content_type: contentType,
      page_evidence_class: evidenceClass,
      indexable,
      robots,
      h1_count: h1Count,
      evaluated,
      applicable,
      finding_present: findingPresent,
    });
  }
  observations.sort((left, right) => left.page_url.localeCompare(right.page_url));

  if (nonNegativeInt(source.evaluated_page_count, 150) !== evaluatedCount
      || nonNegativeInt(source.finding_present_count, 150) !== presentCount
      || nonNegativeInt(source.finding_absent_count, 150) !== absentCount
      || evaluatedCount !== presentCount + absentCount) {
    throw new Error("Missing-H1 comparison aggregate counts are invalid");
  }

  return {
    version: MISSING_H1_COMPARISON_EVIDENCE_VERSION,
    rule: MISSING_H1_RULE,
    rule_definition_version: MISSING_H1_RULE_DEFINITION_VERSION,
    comparison_profile_version: MISSING_H1_COMPARISON_PROFILE_VERSION,
    evidence_url_identity_version: PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION,
    observation_count: observations.length,
    evaluated_page_count: evaluatedCount,
    finding_present_count: presentCount,
    finding_absent_count: absentCount,
    observations,
  };
}
