import { RELEASE_COMPONENT_VERSIONS, RELEASE_FINGERPRINT } from "./generatedReleaseContract.js";
import { firstFailedRepairInvariant } from "./repairInvariants.js";
// Bumped when the snapshot gained coverage/inventory fields. The authority
// proof is an HMAC over the whole snapshot, so adding a field changes the
// payload for every row -- including rows sealed before it existed. Version
// dispatch on reconstruction keeps those rows verifiable instead of turning
// an intact result into 409 result_authority_invalid.
export const REVIEW_ATTESTATION_VERSION = "standard_review_snapshot_hmac_v2_coverage";
export const REVIEW_ATTESTATION_VERSION_V1 = "standard_review_snapshot_hmac_v1";
export const MAX_AUTHORITY_FIXES = 100;

export const REPAIR_CONTRACT_V2 = "repair_contract_v2_shadow_calibrated";
export const REPAIR_PRIORITY_MODEL_V2 = "repair_priority_v2_technical_severity";

const CANONICAL_ACTION_RANK = Object.freeze({
  fix_first: 4,
  important: 3,
  improve: 2,
  review: 1,
});

export const AUTHORITY_CONTRACT = Object.freeze({
  scanner_version: RELEASE_COMPONENT_VERSIONS.scanner_version,
  scanner_build_revision: RELEASE_COMPONENT_VERSIONS.scanner_build_revision,
  archetype_classifier_version: RELEASE_COMPONENT_VERSIONS.archetype_classifier_version,
  review_version: RELEASE_COMPONENT_VERSIONS.review_version,
  review_evidence_calibration_version: RELEASE_COMPONENT_VERSIONS.review_evidence_calibration_version,
  beta_revision_fingerprint: RELEASE_FINGERPRINT,
});

// The only coverage verdict that can carry authority. Anything else -- and
// anything unrecognised or absent -- is refused here, independently of the
// summary boolean Python derives from the same assessment.
export const AUTHORITATIVE_COVERAGE_STATE = "sufficient";

export function firstFailedAuthorityPredicate(scan, review) {
  const firstPage = firstArray([scan?.crawled_pages, scan?.pages, scan?.scanned_pages])[0] || {};
  const predicates = [
    ["scanner_version", scan?.scanner_version === AUTHORITY_CONTRACT.scanner_version],
    ["scanner_build_revision", text(scan?.scanner_build_revision || scan?.technical_audit_summary?.scanner_build_revision, 160) === AUTHORITY_CONTRACT.scanner_build_revision],
    ["advanced_scan_backend", scan?.advanced_scan_backend === "python_scanner_api"],
    ["deno_fallback_used", scan?.deno_fallback_used !== true],
    ["archetype_classifier_version", text(review?.archetype_classifier_version || review?.site_fingerprint?.classification?.classifier_version, 160) === AUTHORITY_CONTRACT.archetype_classifier_version],
    ["review_version", text(review?.review_version || review?.ai_review_version, 160) === AUTHORITY_CONTRACT.review_version],
    ["review_evidence_calibration_version", text(review?.review_evidence_calibration_version, 160) === AUTHORITY_CONTRACT.review_evidence_calibration_version],
    ["beta_revision_fingerprint", text(review?.beta_revision_fingerprint || scan?.beta_revision_fingerprint, 160) === AUTHORITY_CONTRACT.beta_revision_fingerprint],
    ["metadata_evidence_version", Boolean(text(review?.metadata_evidence_version || scan?.metadata_evidence_version || scan?.component_versions?.metadata_evidence_version || firstPage.metadata_evidence_version, 160))],
    ["title_evidence_version", Boolean(text(review?.title_evidence_version || scan?.title_evidence_version || scan?.component_versions?.title_evidence_version || firstPage.title_evidence_version, 160))],
    ["ai_review_backend", review?.ai_review_backend === "python_review_api"],
    ["python_review_fallback_used", review?.python_review_fallback_used !== true],
    ["release_gate_eligible", review?.release_gate_eligible === true],
    ["score_is_provisional", review?.score_is_provisional !== true],
    ["evidence_quality_blocking", review?.evidence_quality_blocking !== true],
    // Base44 must be able to refuse a thin crawl on the coverage evidence
    // itself. Trusting release_gate_eligible alone leaves the seal one stale
    // worker or hand-built envelope away from covering a limited scan.
    ["coverage_state", coverageAssessment(review).state === AUTHORITATIVE_COVERAGE_STATE],
    ["coverage_authority_version", Boolean(text(coverageAssessment(review).coverage_authority_version, 160))],
    ["canonical_repair_contract", canonicalReviewIsAbsentOrValid(review)],
    // Re-derived here, not trusted. A repair whose own arithmetic cannot be
    // true must not reach a seal, whatever the producer claims about it.
    ["repair_coverage_invariants", firstFailedRepairInvariant_forAll(review) === ""],
  ];
  return predicates.find(([, passed]) => !passed)?.[0] || "";
}

/**
 * The first invariant any repair in this review violates, or "".
 *
 * Named separately so the failure is reportable: the predicate list only says
 * which predicate failed, and "repair_coverage_invariants" alone would not say
 * which repair or which rule.
 */
export function firstFailedRepairInvariant_forAll(review) {
  // Validate the same repair collection that buildAuthoritySnapshot will seal.
  // Canonical v2 deliberately leaves the legacy recommendations untouched, so
  // applying Patch D's stronger arithmetic to that stale legacy list can reject
  // a valid canonical snapshot before persistence ever sees canonical_repairs.
  const canonicalRequested = canonicalReviewRequested(review);
  const canonicalMapped = canonicalRequested
    ? suppressAggregateCoveredPageFixes(
      (Array.isArray(review?.canonical_repairs) ? review.canonical_repairs : [])
        .slice(0, MAX_AUTHORITY_FIXES)
        .map(toAuthorityFix),
    )
    : [];
  const canonical = canonicalRequested && canonicalAuthorityFixesValid(canonicalMapped);
  const fixes = canonical
    ? review.canonical_repairs.slice(0, MAX_AUTHORITY_FIXES)
    : firstArray([review?.recommendations, review?.fixes, review?.cleaned_fixes]);
  for (const fix of fixes) {
    const failed = firstFailedRepairInvariant(fix);
    if (failed) return failed;
  }
  return "";
}

function coverageAssessment(review) {
  const fingerprint = review?.site_fingerprint;
  const assessment = fingerprint && typeof fingerprint === "object" ? fingerprint.coverage_assessment : null;
  return assessment && typeof assessment === "object" ? assessment : {};
}

export function isAuthorityEligible(scan, review) {
  return firstFailedAuthorityPredicate(scan, review) === "";
}

export function buildAuthoritySnapshot({ scan, review, identity, userId, now = new Date().toISOString() }) {
  const firstPage = firstArray([scan?.crawled_pages, scan?.pages, scan?.scanned_pages])[0] || {};
  if (!canonicalReviewIsAbsentOrValid(review)) {
    throw new Error("canonical repair contract is invalid");
  }
  const canonicalRequested = canonicalReviewRequested(review);
  const canonicalMapped = canonicalRequested
    ? suppressAggregateCoveredPageFixes(
      (Array.isArray(review?.canonical_repairs) ? review.canonical_repairs : [])
        .slice(0, MAX_AUTHORITY_FIXES)
        .map(toAuthorityFix),
    )
    : [];
  const canonical = canonicalRequested && canonicalAuthorityFixesValid(canonicalMapped);
  const legacyMapped = canonical
    ? []
    : suppressAggregateCoveredPageFixes(firstArray([
      review?.recommendations,
      review?.fixes,
      review?.findings,
      review?.cleaned_fixes,
      review?.recommended_actions,
    ]).slice(0, MAX_AUTHORITY_FIXES).map(toAuthorityFix));
  const fixes = canonical
    ? canonicalMapped.map((fix, index) => ({
      ...fix,
      repair_snapshot_contract_version: REPAIR_CONTRACT_V2,
      repair_snapshot_contract_complete: true,
      canonical_action_rank: index + 1,
    }))
    : legacyMapped.sort((left, right) => left.fix_id.localeCompare(right.fix_id));
  const counts = { critical: 0, high: 0, medium: 0, low: 0 };
  for (const fix of fixes) counts[fix.priority] += 1;

  const websiteUrl = text(scan?.submitted_url || scan?.website_url || scan?.final_url, 2_000);
  const customerSummary = text(
    review?.customer_summary || review?.plain_english_summary || review?.website_health_report?.overall_explanation,
    4_000,
  );
  const scanStatus = text(review?.scan_status || "complete", 120);
  const healthScore = number(review?.health_score ?? review?.website_health_report?.health_score ?? scan?.health_score);
  const healthGrade = text(review?.health_grade || review?.website_health_report?.health_grade, 80);
  const fingerprint = text(review?.beta_revision_fingerprint || scan?.beta_revision_fingerprint, 160);

  return {
    version: REVIEW_ATTESTATION_VERSION,
    sealed_at: String(now),
    owner_user_id: text(userId, 160),
    scan_id: text(identity?.scan_id, 160),
    project_id: text(identity?.project_id, 160),
    normalized_domain: domain(identity?.normalized_domain),
    release_fingerprint: fingerprint,
    scan: {
      status: "complete",
      release_gate_eligible: true,
      score_is_provisional: false,
      evidence_quality_blocking: false,
      website_url: websiteUrl,
      normalized_domain: domain(identity?.normalized_domain),
      scanner_version: text(scan?.scanner_version, 160),
      scanner_build_revision: text(scan?.scanner_build_revision || scan?.technical_audit_summary?.scanner_build_revision, 160),
      scanner_wrapper_version: text(scan?.scanner_wrapper_version || scan?.version, 160),
      advanced_scan_backend: "python_scanner_api",
      deno_fallback_used: false,
      archetype_classifier_version: text(review?.archetype_classifier_version || review?.site_fingerprint?.classification?.classifier_version, 160),
      review_version: text(review?.review_version || review?.ai_review_version, 160),
      review_evidence_calibration_version: text(review?.review_evidence_calibration_version, 160),
      ai_review_backend: "python_review_api",
      python_review_fallback_used: false,
      beta_revision_fingerprint: fingerprint,
      metadata_evidence_version: text(review?.metadata_evidence_version || scan?.metadata_evidence_version || scan?.component_versions?.metadata_evidence_version || firstPage.metadata_evidence_version, 160),
      title_evidence_version: text(review?.title_evidence_version || scan?.title_evidence_version || scan?.component_versions?.title_evidence_version || firstPage.title_evidence_version, 160),
      pages_found: number(scan?.pages_found),
      pages_crawled: number(scan?.pages_crawled),
      scan_status: scanStatus,
      review_confidence_state: text(review?.review_confidence_state, 120),
      evidence_quality_state: text(review?.evidence_quality_state, 120),
      evidence_quality_score: number(review?.evidence_quality_score),
      evidence_quality_reasons: textArray(review?.evidence_quality_reasons, 12, 500),
      // Coverage and inventory diagnostics. The review already computes all of
      // these; the snapshot used to drop them, so every sealed row defaulted to
      // zero and asserted a quality verdict it could not evidence. Persisted
      // only -- nothing here participates in the authority predicates.
      pages_retained: number(review?.usable_html_page_count),
      usable_html_page_count: number(review?.usable_html_page_count),
      representative_html_page_count: number(review?.representative_html_page_count),
      default_route_page_count: number(review?.default_route_page_count),
      discovery_quality_state: text(review?.discovery_quality_state, 120),
      evidence_quality_gate_version: text(review?.evidence_quality_gate_version, 160),
      crawl_timing: plainObject(scan?.crawl_timing ?? scan?.technical_audit_summary?.crawl_timing),
      sampling_evidence: plainObject(scan?.sampling_evidence),
      ...coverageAuthorityFields(review?.coverage_authority_evidence),
      health_score: healthScore,
      health_grade: healthGrade,
      customer_summary: customerSummary,
      next_best_step: text(review?.next_best_step || review?.website_health_report?.next_best_step, 2_000),
      no_high_confidence_findings: review?.no_high_confidence_findings === true,
      completed_at: String(now),
    },
    fix_list: {
      website_url: websiteUrl,
      ai_review_backend: "python_review_api",
      python_review_fallback_used: false,
      is_authoritative: true,
      health_score: healthScore,
      health_grade: healthGrade,
      scan_status: scanStatus,
      score_is_provisional: false,
      no_high_confidence_findings: review?.no_high_confidence_findings === true,
      total_fixes: fixes.length,
      critical_count: counts.critical,
      high_count: counts.high,
      medium_count: counts.medium,
      low_count: counts.low,
      completed_count: 0,
      top_action_fix_ids: fixes.slice(0, 3).map((fix) => fix.fix_id),
      ...(canonical ? {
        repair_contract_version: REPAIR_CONTRACT_V2,
        repair_snapshot_contract_version: REPAIR_CONTRACT_V2,
        repair_snapshot_contract_complete: true,
        repair_priority_model_version: REPAIR_PRIORITY_MODEL_V2,
        canonical_action_fix_ids: fixes.map((fix) => fix.fix_id),
      } : {}),
      generated_at: String(now),
    },
    recommendations: fixes,
  };
}

function suppressAggregateCoveredPageFixes(fixes) {
  const coverage = new Set();
  for (const fix of fixes) {
    if (!isAggregateFix(fix)) continue;
    const rule = findingKey(fix.rule);
    const family = aggregateFamilyKey(fix);
    if (!rule) continue;
    for (const page of explicitAffectedPageKeys(fix)) {
      coverage.add(coverageKey(rule, family, page));
    }
  }
  if (coverage.size === 0) return fixes;

  return fixes.filter((fix) => {
    if (isAggregateFix(fix) || fix.page_scope !== "page") return true;
    const pages = pageKeys(fix);
    if (pages.length !== 1) return true;
    const rule = findingKey(fix.rule);
    const family = findingKey(fix.page_template_family);
    if (!rule) return true;
    return !coverage.has(coverageKey(rule, family, pages[0]))
      && !coverage.has(coverageKey(rule, "*", pages[0]));
  });
}

function isAggregateFix(fix) {
  return ["family", "cross_cutting", "sitewide"].includes(fix?.page_scope);
}

function aggregateFamilyKey(fix) {
  return fix.page_scope === "sitewide" ? "*" : findingKey(fix.page_template_family);
}

function coverageKey(rule, family, page) {
  return `${rule}\u0000${family}\u0000${page}`;
}

function explicitAffectedPageKeys(fix) {
  return uniquePageKeys(fix?.affected_pages);
}

function pageKeys(fix) {
  const affected = explicitAffectedPageKeys(fix);
  return affected.length > 0 ? affected : uniquePageKeys([fix?.page_url]);
}

function uniquePageKeys(values) {
  const seen = new Set();
  const output = [];
  for (const value of values || []) {
    const key = pageKey(value);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    output.push(key);
  }
  return output;
}

function pageKey(value) {
  const raw = text(value, 2_000);
  if (!raw) return "";
  try {
    const parsed = new URL(raw);
    return normalizedPathAndQuery(parsed.pathname, parsed.search);
  } catch {
    const withoutFragment = raw.split("#", 1)[0];
    const queryIndex = withoutFragment.indexOf("?");
    const path = queryIndex >= 0 ? withoutFragment.slice(0, queryIndex) : withoutFragment;
    const query = queryIndex >= 0 ? withoutFragment.slice(queryIndex) : "";
    return normalizedPathAndQuery(path, query);
  }
}

function normalizedPathAndQuery(pathValue, queryValue) {
  let path = String(pathValue || "/");
  if (!path.startsWith("/")) path = `/${path}`;
  if (path.length > 1) path = path.replace(/\/+$/, "") || "/";
  return `${path}${String(queryValue || "")}`;
}

function findingKey(value) {
  return text(value, 200).toLowerCase();
}

function toAuthorityFix(fix, index) {
  const priority = ["critical", "high", "medium", "low"].includes(String(fix?.priority || "").toLowerCase())
    ? String(fix.priority).toLowerCase()
    : "medium";
  const scope = ["page", "family", "mixed", "cross_cutting", "sitewide"].includes(String(fix?.page_scope || ""))
    ? String(fix.page_scope)
    : "page";
  const affectedPages = textArray(fix?.affected_pages, 150, 2_000);
  const raw = fix?.raw_finding && typeof fix.raw_finding === "object" ? fix.raw_finding : {};
  const canonicalFields = text(fix?.repair_contract_version, 160) === REPAIR_CONTRACT_V2
    ? {
      repair_contract_version: REPAIR_CONTRACT_V2,
      repair_priority_model_version: text(fix?.repair_priority_model_version, 160),
      base_severity: text(fix?.base_severity, 40),
      technical_severity_source: text(fix?.technical_severity_source, 120),
      evidence_class: text(fix?.evidence_class, 80),
      action_priority: text(fix?.action_priority, 80),
      action_priority_score: number(fix?.action_priority_score),
      priority_reason: text(fix?.priority_reason, 1_000),
      canonical_action_rank: number(fix?.canonical_action_rank),
      repair_identity_version: text(fix?.repair_identity_version || fix?.repair_identity?.version, 160),
      repair_fingerprint: text(fix?.repair_fingerprint, 160),
      repair_identity_state: text(fix?.repair_identity_state || fix?.repair_identity?.state, 80),
      repair_identity_stable: fix?.repair_identity_stable === true || fix?.repair_identity?.stable === true,
      repair_surface: text(fix?.repair_surface || fix?.repair_identity?.repair_surface, 160),
      remediation_family: text(fix?.remediation_family || fix?.repair_identity?.remediation_family, 200),
      shared_repair_confirmed: fix?.shared_repair_confirmed === true
        || fix?.repair_leverage_confirmed === true
        || fix?.priority_context?.shared_repair_confirmed === true,
      priority_context: canonicalPriorityContext(fix?.priority_context),
      ...(text(fix?.repair_verification_state, 120) ? { repair_verification_state: text(fix?.repair_verification_state, 120) } : {}),
      ...(text(fix?.rule_definition_version, 160) ? { rule_definition_version: text(fix?.rule_definition_version, 160) } : {}),
      ...(text(fix?.comparison_profile_version, 160) ? { comparison_profile_version: text(fix?.comparison_profile_version, 160) } : {}),
    }
    : {};
  return {
    fix_id: text(fix?.fix_id || fix?.id, 160) || `authority_fix_${index + 1}`,
    rule: text(fix?.rule, 200),
    category: text(fix?.category, 200),
    customer_category: text(fix?.customer_category, 200),
    issue_title: text(fix?.issue_title || fix?.title, 500) || "Review scanner finding",
    plain_english_explanation: text(fix?.plain_english_explanation || fix?.plain_english_summary, 2_000),
    why_it_matters: text(fix?.why_it_matters, 2_000),
    current_value: text(fix?.current_value, 2_000),
    recommended_value: text(fix?.recommended_value || fix?.recommendation, 2_000),
    simple_next_step: text(fix?.simple_next_step, 2_000),
    page_scope: scope,
    page_template_family: text(fix?.page_template_family, 200),
    page_url: text(fix?.page_url || affectedPages[0], 2_000),
    affected_pages: affectedPages,
    source_pages: textArray(fix?.source_pages, 150, 2_000),
    evidence_status: text(fix?.evidence_status, 120),
    verification_state: text(fix?.verification_state, 120),
    confidence_score: number(fix?.confidence_score),
    priority,
    difficulty: text(fix?.difficulty, 120),
    who_can_do_this: text(fix?.who_can_do_this, 120),
    requires_developer: fix?.requires_developer === true,
    requires_approval: fix?.requires_approval === true,
    can_auto_fix: false,
    estimated_time: text(fix?.estimated_time, 120),
    user_status: "open",
    what_to_do_steps: textArray(fix?.what_to_do_steps, 12, 1_000),
    ...canonicalFields,
    raw_finding: { verified_urls: verifiedUrls(raw.verified_urls || raw.url_evidence) },
  };
}

function canonicalReviewRequested(review) {
  return Boolean(
    review?.repair_contract_version === REPAIR_CONTRACT_V2
    && review?.repair_snapshot_contract_version === REPAIR_CONTRACT_V2
    && review?.repair_snapshot_contract_complete === true
    && review?.repair_priority_model_version === REPAIR_PRIORITY_MODEL_V2
    && Array.isArray(review?.canonical_repairs),
  );
}

function canonicalReviewAttempted(review) {
  return Boolean(
    review?.repair_contract_version !== undefined
    || review?.repair_snapshot_contract_version !== undefined
    || review?.repair_snapshot_contract_complete !== undefined
    || review?.repair_priority_model_version !== undefined
    || review?.canonical_repairs !== undefined
  );
}

function canonicalReviewIsAbsentOrValid(review) {
  if (!canonicalReviewAttempted(review)) return true;
  if (!canonicalReviewRequested(review)) return false;
  const mapped = suppressAggregateCoveredPageFixes(
    review.canonical_repairs.slice(0, MAX_AUTHORITY_FIXES).map(toAuthorityFix),
  );
  return canonicalAuthorityFixesValid(mapped);
}

function canonicalAuthorityFixesValid(fixes) {
  const list = Array.isArray(fixes) ? fixes : [];
  const ids = new Set();
  let previousBandRank = Number.POSITIVE_INFINITY;
  for (const fix of list) {
    const id = text(fix?.fix_id, 160);
    const band = text(fix?.action_priority, 80);
    const bandRank = CANONICAL_ACTION_RANK[band] || 0;
    if (
      !id
      || ids.has(id)
      || fix?.repair_contract_version !== REPAIR_CONTRACT_V2
      || fix?.repair_priority_model_version !== REPAIR_PRIORITY_MODEL_V2
      || !["critical", "high", "medium", "low"].includes(text(fix?.base_severity, 40))
      || !["confirmed_problem", "improvement", "opportunity"].includes(text(fix?.evidence_class, 80))
      || !bandRank
      || bandRank > previousBandRank
      || !text(fix?.priority_reason, 1_000)
      || !text(fix?.repair_identity_version, 160)
      || !text(fix?.repair_fingerprint, 160)
      || number(fix?.canonical_action_rank) < 1
    ) return false;
    ids.add(id);
    previousBandRank = bandRank;
  }
  return true;
}

function canonicalPriorityContext(value) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  return {
    version: text(source.version, 160),
    legacy_priority: text(source.legacy_priority, 40),
    base_severity: text(source.base_severity, 40),
    technical_severity_source: text(source.technical_severity_source, 120),
    evidence_class: text(source.evidence_class, 80),
    action_priority: text(source.action_priority, 80),
    action_priority_score: number(source.action_priority_score),
    search_facing: source.search_facing === true,
    affected_checked: number(source.affected_checked),
    checked_eligible: nullableNumber(source.checked_eligible),
    checked_coverage: nullableNumber(source.checked_coverage),
    indexable_affected: number(source.indexable_affected),
    non_indexable_affected: number(source.non_indexable_affected),
    unknown_indexability_affected: number(source.unknown_indexability_affected),
    indexable_checked_eligible: nullableNumber(source.indexable_checked_eligible),
    searchable_coverage: nullableNumber(source.searchable_coverage),
    important_affected: number(source.important_affected),
    shared_repair_confirmed: source.shared_repair_confirmed === true,
    coverage_scope: text(source.coverage_scope, 80),
  };
}

function nullableNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function verifiedUrls(value) {
  if (!Array.isArray(value)) return [];
  return value.slice(0, 25).map((item) => typeof item === "string"
    ? { url: text(item, 2_000) }
    : {
      url: text(item?.url, 2_000),
      final_url: text(item?.final_url, 2_000),
      status_code: number(item?.status_code),
      verification_state: text(item?.verification_state, 120),
    }).filter((item) => item.url || item.final_url);
}

function firstArray(values) {
  for (const value of values || []) if (Array.isArray(value) && value.length > 0) return value;
  return [];
}

function plainObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

/**
 * The coverage assessment is absent-or-whole. A partial record would read as a
 * verdict the scanner never reached, so an unversioned or empty assessment
 * writes nothing rather than a fabricated default.
 */
function coverageAuthorityFields(evidence) {
  const assessment = plainObject(evidence);
  const version = text(assessment.coverage_authority_evidence_version, 160);
  if (!version || !text(assessment.assessment, 120)) return {};
  return {
    coverage_authority_evidence_version: version,
    coverage_authority_evidence: assessment,
  };
}

function text(value, limit) {
  return typeof value === "string" ? value.trim().slice(0, limit) : "";
}

function textArray(value, limit, itemLimit) {
  return Array.isArray(value) ? value.slice(0, limit).map((item) => text(item, itemLimit)).filter(Boolean) : [];
}

function number(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function domain(value) {
  const raw = text(value, 2_000);
  if (!raw) return "";
  try {
    const parsed = new URL(/^https?:\/\//i.test(raw) ? raw : `https://${raw}`);
    return ["http:", "https:"].includes(parsed.protocol) ? parsed.hostname.toLowerCase().replace(/^www\./, "").replace(/\.$/, "") : "";
  } catch {
    return "";
  }
}
