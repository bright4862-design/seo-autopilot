import { PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION, publishedEvidenceUrlKey } from "./evidenceUrlIdentity.js";
import { PUBLISHED_REPAIR_INVARIANT_VERSION, firstFailedRepairInvariant } from "./repairInvariants.js";

export const PUBLISHED_REVIEW_ATTESTATION_VERSION = "standard_review_snapshot_hmac_identity_v1";
export const PUBLISHED_REPAIR_COVERAGE_VERSION = "repair_coverage_v5_published_route_identity";

export function publishedIdentityContext(scan, identityVersion = "") {
  if (!identityVersion) return { scanOrigin: "", identityVersion: "" };
  if (identityVersion !== PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION) throw new Error("published identity version unsupported");
  const raw = scan?.requested_origin || scan?.crawl_scope?.requested_origin || scan?.website_url || scan?.submitted_url || scan?.normalized_url;
  const root = publishedEvidenceUrlKey("/", { scanOrigin: raw });
  if (!root) throw new Error("published identity requires trusted scan origin");
  return { scanOrigin: root.slice(0, -1), identityVersion };
}

function count(value) {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) throw new Error("published identity cardinality invalid");
  return value;
}
function record(value) {
  if (!value || typeof value !== "object" || Array.isArray(value) || Object.keys(value).length > 150) throw new Error("published identity partition invalid");
  return value;
}

export function publishedPriorityContext(value, identityVersion = "") {
  if (!identityVersion) return {};
  if (identityVersion !== PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION || value?.evidence_url_identity_version !== identityVersion) throw new Error("published priority identity missing");
  return {
    evidence_url_identity_version: identityVersion,
    affected_observed: count(value.affected_observed),
    affected_eligible: count(value.affected_eligible),
  };
}

// Only the authenticated envelope selects this serializer. Persisted markers
// must exist in raw_finding; a top-level injected/default field cannot upgrade
// old rows or repair missing new evidence during the writer's final re-sign.
export function publishedRepairEvidenceFields(fix, { identityVersion = "", scanOrigin = "", persisted = false } = {}) {
  if (!identityVersion) return { fields: {}, evidence: {} };
  const source = persisted ? fix?.raw_finding?.published_evidence : fix;
  if (identityVersion !== PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION || source?.evidence_url_identity_version !== identityVersion
      || source?.repair_coverage_version !== PUBLISHED_REPAIR_COVERAGE_VERSION
      || (persisted && source?.repair_invariant_version !== PUBLISHED_REPAIR_INVARIANT_VERSION)) {
    throw new Error("published identity evidence missing or unsupported");
  }
  const fields = {
    page_count: count(fix.page_count),
    family_breakdown: Object.fromEntries(Object.entries(record(fix.family_breakdown)).map(([family, value]) => [family, count(value)])),
    representative_pages_by_family: Object.fromEntries(Object.entries(record(fix.representative_pages_by_family)).map(([family, value]) => {
      const values = Array.isArray(value) ? value : [value];
      if (!values.length || values.length > 150 || values.some(url => typeof url !== "string" || url.length > 2000 || !publishedEvidenceUrlKey(url, { scanOrigin }))) throw new Error("published identity representative invalid");
      return [family, Array.isArray(value) ? [...values] : value];
    })),
  };
  if (typeof source.affected_pages_complete !== "boolean") throw new Error("published identity completeness missing");
  const evidence = {
    evidence_url_identity_version: identityVersion,
    repair_coverage_version: PUBLISHED_REPAIR_COVERAGE_VERSION,
    repair_invariant_version: PUBLISHED_REPAIR_INVARIANT_VERSION,
    affected_pages_complete: source.affected_pages_complete,
  };
  for (const key of ["affected_reported", "affected_observed", "affected_eligible", "checked_eligible", "indexable_affected", "indexable_checked_eligible"]) {
    if (source[key] !== undefined) evidence[key] = source[key] === null && key.includes("checked_eligible") ? null : count(source[key]);
  }
  const failed = firstFailedRepairInvariant({ ...fix, ...fields, ...evidence }, { scanOrigin, identityVersion });
  if (failed) throw new Error(`published identity invariant: ${failed}`);
  return { fields, evidence };
}
