import { RELEASE_FINGERPRINT } from "./generatedReleaseContract.js";
const ENCODER = new TextEncoder();

export const ACCESS_APP_ID = "6a498732ec779dfaaeab0e53";
export const ACCESS_PLAN_ID = "standard150_lifetime";
export const OWNER_TEST_EMAIL = "bright4862@gmail.com";
export const OWNER_TEST_USER_ID = "6a498da58ef5cec1f5cd4486";
// Versions the customer projection itself. Declared in
// data/cross-runtime-release-components.json so a projection behavior change
// moves the release fingerprint like any Python change would.
export const CUSTOMER_PROJECTION_VERSION = "customer_projection_v5_focused_scope_lineage";
export const REPAIR_CONTRACT_V2 = "repair_contract_v2_shadow_calibrated";
export const REPAIR_PRIORITY_MODEL_V2 = "repair_priority_v2_technical_severity";

const PUBLIC_RUN_FIELDS = [
  "id",
  "project_id",
  "website_url",
  "submitted_url",
  "final_url",
  "normalized_domain",
  "path_prefix",
  "scope_type",
  "parent_scan_id",
  "requested_origin",
  "requested_path_prefix",
  "discovered_from",
  "user_confirmed",
  "scan_mode",
  "status",
  "status_detail",
  "pages_found",
  "pages_crawled",
  "pages_retained",
  "queued_remaining",
  "queued_at",
  "started_at",
  "reviewing_at",
  "completed_at",
  "created_date",
  "updated_date",
  "error_code",
];

// History is intentionally narrower than the progress projection used for one
// exact ScanRun. It must remain safe before entitlement is checked and never
// carry score, evidence, request identity, release identity, or authority data.
export function buildScanHistoryProjection(rows = []) {
  return uniqueRows(rows).map((run) => ({
    id: text(run?.id, 160),
    project_id: text(run?.project_id, 160),
    website_url: text(run?.website_url || run?.submitted_url, 2_000),
    normalized_domain: domain(run?.normalized_domain || run?.website_url || run?.submitted_url),
    scope_type: text(run?.scope_type, 40),
    parent_scan_id: text(run?.parent_scan_id, 160),
    requested_origin: text(run?.requested_origin, 2_000),
    requested_path_prefix: text(run?.requested_path_prefix || run?.path_prefix, 1_000),
    discovered_from: text(run?.discovered_from, 80),
    user_confirmed: run?.user_confirmed === true,
    status: text(run?.status, 80),
    pages_found: nonNegativeInteger(run?.pages_found),
    pages_crawled: nonNegativeInteger(run?.pages_crawled),
    queued_at: text(run?.queued_at, 80),
    started_at: text(run?.started_at, 80),
    reviewing_at: text(run?.reviewing_at, 80),
    completed_at: text(run?.completed_at, 80),
  })).filter((run) => run.id && run.project_id);
}

export function recordOwnedByUser(record, userIdValue) {
  const userId = text(userIdValue, 160);
  if (!userId) return false;
  const explicitOwner = text(record?.owner_user_id, 160);
  if (explicitOwner) return explicitOwner === userId;
  return text(record?.created_by_id, 160) === userId;
}

const DETAILED_RUN_FIELDS = [
  "scanner_version",
  "scanner_build_revision",
  "scanner_wrapper_version",
  "release_id",
  "advanced_scan_backend",
  "deno_fallback_used",
  "archetype_classifier_version",
  "review_version",
  "review_evidence_calibration_version",
  "ai_review_backend",
  "python_review_fallback_used",
  "release_gate_eligible",
  "beta_revision_fingerprint",
  "metadata_evidence_version",
  "title_evidence_version",
  "local_cache_complete",
  "sampling_evidence",
  "crawl_timing",
  "scan_status",
  "review_confidence_state",
  "score_is_provisional",
  "access_evidence_state",
  "evidence_quality_state",
  "evidence_quality_score",
  "evidence_quality_reasons",
  "discovery_quality_state",
  "representative_html_page_count",
  "usable_html_page_count",
  "default_route_page_count",
  "evidence_quality_blocking",
  "evidence_quality_gate_version",
  "coverage_authority_evidence",
  "classification_integrity",
  "classification_verdict",
  "peak_memory_bytes",
  "worker_peak_memory_bytes",
  "no_high_confidence_findings",
  "limitation",
  "render_evidence",
  "health_score",
  "health_grade",
  "customer_summary",
  "next_best_step",
  "fix_list_id",
];

const FIX_LIST_FIELDS = [
  "id",
  "scan_run_id",
  "project_id",
  "website_url",
  "ai_review_backend",
  "python_review_fallback_used",
  "is_authoritative",
  "health_score",
  "health_grade",
  "scan_status",
  "score_is_provisional",
  "no_high_confidence_findings",
  "total_fixes",
  "critical_count",
  "high_count",
  "medium_count",
  "low_count",
  "completed_count",
  "top_action_fix_ids",
  "repair_contract_version",
  "repair_snapshot_contract_version",
  "repair_snapshot_contract_complete",
  "repair_priority_model_version",
  "canonical_action_fix_ids",
  "generated_at",
  "created_date",
  "updated_date",
];

const FIX_ITEM_FIELDS = [
  "id",
  "fix_list_id",
  "scan_run_id",
  "project_id",
  "fix_id",
  "rule",
  "category",
  "customer_category",
  "issue_title",
  "plain_english_explanation",
  "why_it_matters",
  "current_value",
  "recommended_value",
  "simple_next_step",
  "page_scope",
  "page_template_family",
  "page_url",
  "affected_pages",
  "source_pages",
  "evidence_status",
  "verification_state",
  "limitation_code",
  "confidence_score",
  "priority",
  "difficulty",
  "who_can_do_this",
  "requires_developer",
  "requires_approval",
  "can_auto_fix",
  "estimated_time",
  "user_status",
  "completed_at",
  "completed_by_user_id",
  "first_seen_scan_run_id",
  "carried_over",
  "page_count",
  "family_breakdown",
  "representative_pages_by_family",
  "what_to_do_steps",
  "metadata_state_counts",
  "combined_rules",
  "grouping_explanation",
  "repair_contract_version",
  "repair_snapshot_contract_version",
  "repair_snapshot_contract_complete",
  "repair_priority_model_version",
  "base_severity",
  "technical_severity_source",
  "evidence_class",
  "action_priority",
  "action_priority_score",
  "priority_reason",
  "coverage_context_validity",
  "coverage_context_note",
  "canonical_action_rank",
  "repair_identity_version",
  "repair_fingerprint",
  "repair_identity_state",
  "repair_identity_stable",
  "repair_surface",
  "remediation_family",
  "shared_repair_confirmed",
  "priority_context",
  "repair_verification_state",
  "rule_definition_version",
  "comparison_profile_version",
  "created_date",
  "updated_date",
];

export function evaluatePaidAccess({ rows, user }) {
  const records = uniqueRows(rows);
  if (records.length !== 1) return { ok: false, failureCode: records.length > 1 ? "paid_access_conflict" : "paid_access_required" };

  const row = records[0];
  const email = normalizedEmail(user?.email);
  const userId = text(user?.id, 160);
  const paidAt = Date.parse(text(row?.paid_at, 80));
  const grantedAt = Date.parse(text(row?.granted_at, 80));
  const identityMatches = Boolean(
    email
    && userId
    && normalizedEmail(row?.user_email) === email
    && text(row?.owner_user_id, 160) === userId
  );
  const activeGrant = Boolean(
    row?.has_full_access === true
    && row?.access_status === "active"
    && row?.plan_id === ACCESS_PLAN_ID
    && row?.app_id === ACCESS_APP_ID
  );
  const paidGrant = Boolean(
    activeGrant
    && row?.grant_source === "stripe_checkout"
    && text(row?.stripe_checkout_session_id, 200)
    && Number.isFinite(paidAt)
  );
  const ownerGrant = Boolean(
    activeGrant
    && row?.grant_source === "owner_test"
    && email === OWNER_TEST_EMAIL
    && userId === OWNER_TEST_USER_ID
    && Number.isFinite(grantedAt)
  );
  const manualGrant = Boolean(
    activeGrant
    && row?.grant_source === "manual_grant"
    && Number.isFinite(grantedAt)
  );
  return identityMatches && (paidGrant || ownerGrant || manualGrant)
    ? { ok: true, record: row }
    : { ok: false, failureCode: "paid_access_required" };
}

export function buildCustomerProjection({ run, fixList, fixItems, fullAccess, authorityVerified, resultIntegrityVerified }) {
  // A verified limited result is readable and is never authoritative. The two
  // flags stay separate all the way to the customer so nothing downstream can
  // mistake "we verified this provisional record" for "this is authoritative".
  const limitedVerified = fullAccess === true && resultIntegrityVerified === true;
  const canReadResult = fullAccess === true && (authorityVerified === true || limitedVerified);
  const customerHealthScoreStatus = authorityVerified === true
    ? "authoritative"
    : limitedVerified ? "insufficient_evidence" : "";
  const canonical = fullAccess === true && authorityVerified === true
    && fixList?.repair_contract_version === REPAIR_CONTRACT_V2
    && fixList?.repair_snapshot_contract_version === REPAIR_CONTRACT_V2
    && fixList?.repair_snapshot_contract_complete === true;
  const customerFixItems = canReadResult ? (fixItems || []).map(sanitizeFixItem) : [];
  if (canonical) {
    customerFixItems.sort((left, right) => number(left.canonical_action_rank) - number(right.canonical_action_rank));
  }
  return {
    success: true,
    access: fullAccess === true ? "full" : "locked",
    authority_verified: fullAccess === true && authorityVerified === true,
    result_integrity_verified: limitedVerified,
    release_contract_current: canReadResult && run?.beta_revision_fingerprint === RELEASE_FINGERPRINT,
    scan_id: text(run?.id, 160),
    fix_list_id: canReadResult ? text(fixList?.id, 160) : "",
    run: sanitizeRun(run, { detailed: canReadResult, healthScoreStatus: customerHealthScoreStatus }),
    fixList: canReadResult ? pickFields(fixList, FIX_LIST_FIELDS) : null,
    fixItems: customerFixItems,
  };
}

export function authoritySnapshotFromRows({ run, fixList, fixItems, userId }) {
  const canonical = fixList?.repair_contract_version === REPAIR_CONTRACT_V2
    && fixList?.repair_snapshot_contract_version === REPAIR_CONTRACT_V2
    && fixList?.repair_snapshot_contract_complete === true
    && fixList?.repair_priority_model_version === REPAIR_PRIORITY_MODEL_V2;
  const recommendations = (fixItems || []).map((item) => authorityFixFromRow(item, { canonical }));
  if (canonical) {
    recommendations.sort((left, right) => number(left.canonical_action_rank) - number(right.canonical_action_rank));
  } else {
    recommendations.sort((left, right) => left.fix_id.localeCompare(right.fix_id));
  }

  return {
    version: text(run?.authority_seal_version, 160),
    sealed_at: text(run?.authority_sealed_at, 80),
    owner_user_id: text(userId, 160),
    scan_id: text(run?.id, 160),
    project_id: text(run?.project_id, 160),
    normalized_domain: domain(run?.normalized_domain || run?.website_url),
    release_fingerprint: text(run?.beta_revision_fingerprint, 160),
    scan: {
      status: text(run?.status, 80),
      release_gate_eligible: run?.release_gate_eligible === true,
      score_is_provisional: run?.score_is_provisional === true,
      evidence_quality_blocking: run?.evidence_quality_blocking === true,
      website_url: text(run?.website_url, 2_000),
      normalized_domain: domain(run?.normalized_domain || run?.website_url),
      ...scopeSnapshotFields(run),
      scanner_version: text(run?.scanner_version, 160),
      scanner_build_revision: text(run?.scanner_build_revision, 160),
      scanner_wrapper_version: text(run?.scanner_wrapper_version, 160),
      advanced_scan_backend: text(run?.advanced_scan_backend, 160),
      deno_fallback_used: run?.deno_fallback_used === true,
      archetype_classifier_version: text(run?.archetype_classifier_version, 160),
      review_version: text(run?.review_version, 160),
      review_evidence_calibration_version: text(run?.review_evidence_calibration_version, 160),
      ai_review_backend: text(run?.ai_review_backend, 160),
      python_review_fallback_used: run?.python_review_fallback_used === true,
      beta_revision_fingerprint: text(run?.beta_revision_fingerprint, 160),
      metadata_evidence_version: text(run?.metadata_evidence_version, 160),
      title_evidence_version: text(run?.title_evidence_version, 160),
      pages_found: number(run?.pages_found),
      pages_crawled: number(run?.pages_crawled),
      scan_status: text(run?.scan_status, 120),
      review_confidence_state: text(run?.review_confidence_state, 120),
      evidence_quality_state: text(run?.evidence_quality_state, 120),
      evidence_quality_score: number(run?.evidence_quality_score),
      evidence_quality_reasons: textArray(run?.evidence_quality_reasons, 12, 500),
      // Coverage/inventory diagnostics, present in v2 and carried forward by v3.
      // A row sealed under v1 must be rebuilt exactly as v1 or its stored
      // proof stops verifying and an intact result reads as tampered.
      ...coverageSnapshotFields(run),
      ...acceptanceEvidenceSnapshotFields(run),
      health_score: number(run?.health_score),
      health_grade: text(run?.health_grade, 80),
      customer_summary: text(run?.customer_summary, 4_000),
      next_best_step: text(run?.next_best_step, 2_000),
      no_high_confidence_findings: run?.no_high_confidence_findings === true,
      completed_at: text(run?.completed_at, 80),
    },
    fix_list: {
      website_url: text(fixList?.website_url, 2_000),
      ai_review_backend: text(fixList?.ai_review_backend, 160),
      python_review_fallback_used: fixList?.python_review_fallback_used === true,
      is_authoritative: fixList?.is_authoritative === true,
      health_score: number(fixList?.health_score),
      health_grade: text(fixList?.health_grade, 80),
      scan_status: text(fixList?.scan_status, 120),
      score_is_provisional: fixList?.score_is_provisional === true,
      no_high_confidence_findings: fixList?.no_high_confidence_findings === true,
      total_fixes: number(fixList?.total_fixes),
      critical_count: number(fixList?.critical_count),
      high_count: number(fixList?.high_count),
      medium_count: number(fixList?.medium_count),
      low_count: number(fixList?.low_count),
      completed_count: number(fixList?.completed_count),
      top_action_fix_ids: textArray(fixList?.top_action_fix_ids, 3, 160),
      ...(canonical ? {
        repair_contract_version: REPAIR_CONTRACT_V2,
        repair_snapshot_contract_version: REPAIR_CONTRACT_V2,
        repair_snapshot_contract_complete: true,
        repair_priority_model_version: REPAIR_PRIORITY_MODEL_V2,
        canonical_action_fix_ids: textArray(fixList?.canonical_action_fix_ids, 100, 160),
      } : {}),
      generated_at: text(fixList?.generated_at, 80),
    },
    recommendations,
  };
}

export async function createAuthoritySeal(payload, secret, cryptoImpl = globalThis.crypto) {
  const key = await importHmacKey(secret, cryptoImpl, ["sign"]);
  const signature = await cryptoImpl.subtle.sign(
    "HMAC",
    key,
    ENCODER.encode(stableSerialize(payload)),
  );
  return bytesToHex(new Uint8Array(signature));
}

export async function verifyAuthoritySeal(payload, secret, proof, cryptoImpl = globalThis.crypto) {
  const cleanProof = typeof proof === "string" ? proof.trim().toLowerCase() : "";
  if (!/^[a-f0-9]{64}$/.test(cleanProof)) return false;
  try {
    const key = await importHmacKey(secret, cryptoImpl, ["verify"]);
    return await cryptoImpl.subtle.verify(
      "HMAC",
      key,
      hexToBytes(cleanProof),
      ENCODER.encode(stableSerialize(payload)),
    );
  } catch {
    return false;
  }
}

export function stableSerialize(value) {
  return JSON.stringify(canonicalize(value));
}

function authorityFixFromRow(item, { canonical = false } = {}) {
  const raw = item?.raw_finding && typeof item.raw_finding === "object" ? item.raw_finding : {};
  const base = {
    fix_id: text(item?.fix_id, 160),
    rule: text(item?.rule, 200),
    category: text(item?.category, 200),
    customer_category: text(item?.customer_category, 200),
    issue_title: text(item?.issue_title, 500),
    plain_english_explanation: text(item?.plain_english_explanation, 2_000),
    why_it_matters: text(item?.why_it_matters, 2_000),
    current_value: text(item?.current_value, 2_000),
    recommended_value: text(item?.recommended_value, 2_000),
    simple_next_step: text(item?.simple_next_step, 2_000),
    page_scope: text(item?.page_scope, 80),
    page_template_family: text(item?.page_template_family, 200),
    page_url: text(item?.page_url, 2_000),
    affected_pages: textArray(item?.affected_pages, 150, 2_000),
    source_pages: textArray(item?.source_pages, 150, 2_000),
    evidence_status: text(item?.evidence_status, 120),
    verification_state: text(item?.verification_state, 120),
    confidence_score: number(item?.confidence_score),
    priority: text(item?.priority, 40),
    difficulty: text(item?.difficulty, 120),
    who_can_do_this: text(item?.who_can_do_this, 120),
    requires_developer: item?.requires_developer === true,
    requires_approval: item?.requires_approval === true,
    can_auto_fix: false,
    estimated_time: text(item?.estimated_time, 120),
    user_status: text(item?.user_status, 80),
    what_to_do_steps: textArray(item?.what_to_do_steps, 12, 1_000),
  };
  if (!canonical) {
    return {
      ...base,
      raw_finding: { verified_urls: verifiedUrls(raw.verified_urls || raw.url_evidence) },
    };
  }
  return {
    ...base,
    repair_contract_version: text(item?.repair_contract_version, 160),
    repair_snapshot_contract_version: text(item?.repair_snapshot_contract_version, 160),
    repair_snapshot_contract_complete: item?.repair_snapshot_contract_complete === true,
    repair_priority_model_version: text(item?.repair_priority_model_version, 160),
    base_severity: text(item?.base_severity, 40),
    technical_severity_source: text(item?.technical_severity_source, 120),
    evidence_class: text(item?.evidence_class, 80),
    action_priority: text(item?.action_priority, 80),
    action_priority_score: number(item?.action_priority_score),
    priority_reason: text(item?.priority_reason, 1_000),
    canonical_action_rank: number(item?.canonical_action_rank),
    repair_identity_version: text(item?.repair_identity_version, 160),
    repair_fingerprint: text(item?.repair_fingerprint, 160),
    repair_identity_state: text(item?.repair_identity_state, 80),
    repair_identity_stable: item?.repair_identity_stable === true,
    repair_surface: text(item?.repair_surface, 160),
    remediation_family: text(item?.remediation_family, 200),
    shared_repair_confirmed: item?.shared_repair_confirmed === true,
    priority_context: canonicalPriorityContext(item?.priority_context),
    ...(text(item?.repair_verification_state, 120) ? { repair_verification_state: text(item?.repair_verification_state, 120) } : {}),
    ...(text(item?.rule_definition_version, 160) ? { rule_definition_version: text(item?.rule_definition_version, 160) } : {}),
    ...(text(item?.comparison_profile_version, 160) ? { comparison_profile_version: text(item?.comparison_profile_version, 160) } : {}),
    raw_finding: {
      verified_urls: verifiedUrls(raw.verified_urls || raw.url_evidence),
      ...(canonicalRepairEvidenceGroups(raw.repair_evidence_groups).length > 0
        ? { repair_evidence_groups: canonicalRepairEvidenceGroups(raw.repair_evidence_groups) }
        : {}),
    },
  };
}

function canonicalRepairEvidenceGroups(value) {
  const groups = Array.isArray(value) ? value : [];
  return groups.slice(0, 100).map((group) => ({
    fix_id: text(group?.fix_id, 160),
    family: text(group?.family, 160),
    locale: text(group?.locale, 40),
    representative_url: text(group?.representative_url, 2_000),
    affected_urls: textArray(group?.affected_urls, 150, 2_000),
    count: Math.max(0, number(group?.count)),
    priority: text(group?.priority, 40),
    action_priority: text(group?.action_priority, 80),
    evidence_class: text(group?.evidence_class, 80),
    evidence_status: text(group?.evidence_status, 120),
    verification_state: text(group?.verification_state, 120),
    repair_verification_state: text(group?.repair_verification_state, 120),
  }));
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

function sanitizeRun(run, { detailed, healthScoreStatus = "" }) {
  const result = pickFields(run, detailed ? [...PUBLIC_RUN_FIELDS, ...DETAILED_RUN_FIELDS] : PUBLIC_RUN_FIELDS);
  result.id = text(run?.id, 160);
  result.scan_id = result.id;
  if (detailed && healthScoreStatus) {
    result.health_score_status = text(healthScoreStatus, 80);
  }
  if (detailed && usesAcceptanceEvidenceContract(run) && !hasCompleteAcceptanceEvidence(run)) {
    delete result.coverage_authority_evidence;
    delete result.classification_integrity;
    delete result.classification_verdict;
    delete result.peak_memory_bytes;
    delete result.worker_peak_memory_bytes;
  }
  if (!detailed) {
    result.release_gate_eligible = false;
    result.is_authoritative = false;
  }
  return result;
}

function usesAcceptanceEvidenceContract(run) {
  return ["standard_review_snapshot_hmac_v3_acceptance_evidence", "standard_review_snapshot_hmac_v4_focused_scope"].includes(text(run?.authority_seal_version, 160))
    || text(run?.result_integrity_version, 160) === "standard_limited_result_integrity_v2_acceptance_evidence";
}

function hasCompleteAcceptanceEvidence(run) {
  const coverage = plainObject(run?.coverage_authority_evidence);
  const classification = plainObject(run?.classification_integrity);
  const state = text(classification.state, 120);
  const verdict = text(classification.verdict, 120);
  const usablePages = acceptanceFiniteNonNegativeNumber(classification.usable_pages);
  const workerPeak = acceptancePositiveNumber(run?.worker_peak_memory_bytes ?? run?.peak_memory_bytes);
  return Boolean(
    text(coverage.coverage_authority_evidence_version, 160)
    && text(coverage.assessment, 120)
    && text(classification.version, 160)
    && state
    && verdict
    && state === verdict
    && text(classification.classifier_version, 160)
    && text(classification.evidence_sufficiency, 120)
    && usablePages !== null
    && typeof classification.complete_small_site_inventory === "boolean"
    && workerPeak !== null
  );
}

function acceptanceFiniteNonNegativeNumber(value) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
}

function acceptancePositiveNumber(value) {
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? value : null;
}

const COVERAGE_UNAVAILABLE_NOTE = "Coverage detail unavailable for this saved scan.";

/**
 * Count copy agrees with its count.
 *
 * A count and the words around it are one sentence, so the noun and the verb
 * have to move together. Pluralizing the noun alone produced "1 checked page
 * are affected." on every single-page result in production.
 *
 * Base44 functions are self-contained deployables and cannot import the
 * frontend's copy helpers, so `count_copy_version` is a shared contract
 * implemented per runtime rather than a shared module.
 */
export function pluralNoun(count, singular, plural = `${singular}s`) {
  return Number(count) === 1 ? singular : plural;
}

// English verbs whose plural is not formed by any rule worth guessing at. A
// verb that is not listed is returned unchanged rather than mangled.
const VERB_PLURALS = { is: "are", was: "were", has: "have", does: "do" };

export function agreeingVerb(count, singular) {
  return Number(count) === 1 ? singular : (VERB_PLURALS[singular] || singular);
}

/**
 * Whether a saved repair's coverage arithmetic can be true.
 *
 * Records already sealed in production carry 126/1, 35/30 and 47/6. Their seal
 * covers those numbers, so they cannot be corrected in place, and the browser
 * must not recompute an authority it does not hold. What the server can do is
 * decline to render an impossible ratio and state the absolute count instead.
 *
 *   valid       numerator and denominator can be counted over one universe
 *   invalid     they cannot; the ratio is suppressed
 *   unmeasured  there is no denominator, so there was never a ratio to show
 */
function coverageContextValidity(item) {
  // The counts live in priority_context; the top-level fallback keeps this
  // honest for any older row that carried them flat.
  const context = item?.priority_context && typeof item.priority_context === "object" ? item.priority_context : item || {};
  const affected = number(context.affected_checked ?? item?.affected_checked ?? item?.page_count);
  const eligible = context.checked_eligible === null || context.checked_eligible === undefined
    ? null
    : number(context.checked_eligible);
  const indexableAffected = number(context.indexable_affected);
  const indexableEligible = context.indexable_checked_eligible === null || context.indexable_checked_eligible === undefined
    ? null
    : number(context.indexable_checked_eligible);

  if (eligible === null && indexableEligible === null) return "unmeasured";
  if (eligible !== null && (eligible <= 0 || affected > eligible)) return "invalid";
  if (indexableEligible !== null && (indexableEligible <= 0 || indexableAffected > indexableEligible)) return "invalid";
  return "valid";
}

/** Absolute count wording, used wherever a ratio cannot honestly be shown. */
function neutralCoverageReason(item) {
  const context = item?.priority_context && typeof item.priority_context === "object" ? item.priority_context : item || {};
  const affected = number(context.affected_checked ?? item?.affected_checked ?? item?.page_count);
  if (affected <= 0) return COVERAGE_UNAVAILABLE_NOTE;
  return `${affected} checked ${pluralNoun(affected, "page")} ${agreeingVerb(affected, "is")} affected.`;
}

function applyCoverageValidity(result) {
  const validity = coverageContextValidity(result);
  result.coverage_context_validity = validity;
  if (validity !== "invalid") return result;
  // Suppressed, not corrected: the sealed record keeps its numbers, and the
  // signed prose stays intact in owner diagnostics rather than being parsed
  // apart here.
  if (result.priority_context && typeof result.priority_context === "object") {
    result.priority_context = { ...result.priority_context, checked_coverage: null, searchable_coverage: null };
  }
  result.checked_coverage = null;
  result.searchable_coverage = null;
  result.priority_reason = neutralCoverageReason(result);
  result.coverage_context_note = COVERAGE_UNAVAILABLE_NOTE;
  return result;
}

function sanitizeFixItem(item) {
  const result = pickFields(item, FIX_ITEM_FIELDS);
  const raw = item?.raw_finding && typeof item.raw_finding === "object" ? item.raw_finding : {};
  const evidenceGroups = canonicalRepairEvidenceGroups(raw.repair_evidence_groups);
  result.raw_finding = {
    verified_urls: verifiedUrls(raw.verified_urls || raw.url_evidence),
    ...(evidenceGroups.length > 0 ? { repair_evidence_groups: evidenceGroups } : {}),
  };
  return applyCoverageValidity(result);
}

function pickFields(value, fields) {
  const source = value && typeof value === "object" ? value : {};
  return fields.reduce((result, field) => {
    if (source[field] !== undefined) result[field] = source[field];
    return result;
  }, {});
}

function uniqueRows(rows) {
  return Array.from(new Map(
    (Array.isArray(rows) ? rows : [])
      .filter((row) => row && text(row.id, 160))
      .map((row) => [text(row.id, 160), row]),
  ).values());
}

function normalizedEmail(value) {
  return text(value, 320).toLowerCase();
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

function plainObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

const REVIEW_ATTESTATION_VERSION_V2 = "standard_review_snapshot_hmac_v2_coverage";
const REVIEW_ATTESTATION_VERSION_V3 = "standard_review_snapshot_hmac_v3_acceptance_evidence";
const REVIEW_ATTESTATION_VERSION_V4 = "standard_review_snapshot_hmac_v4_focused_scope";

/**
 * Reconstruction is version-dispatched, never inferred from which fields the
 * row happens to carry: a v2 row whose coverage evidence is genuinely absent
 * must still rebuild the v2 shape, and a v1 row must never gain a field its
 * seal did not cover. The row's own authority_seal_version is the authority.
 */
function scopeSnapshotFields(row) {
  if (text(row?.authority_seal_version, 160) !== REVIEW_ATTESTATION_VERSION_V4) return {};
  return {
    scope_type: text(row?.scope_type, 40),
    parent_scan_id: text(row?.parent_scan_id, 160),
    requested_origin: text(row?.requested_origin, 2_000),
    requested_path_prefix: text(row?.requested_path_prefix || row?.path_prefix, 1_000),
    discovered_from: text(row?.discovered_from, 80),
    user_confirmed: row?.user_confirmed === true,
  };
}
function coverageSnapshotFields(row) {
  if (![REVIEW_ATTESTATION_VERSION_V2, REVIEW_ATTESTATION_VERSION_V3, REVIEW_ATTESTATION_VERSION_V4].includes(
    text(row?.authority_seal_version, 160),
  )) return {};
  return {
    pages_retained: number(row?.pages_retained),
    usable_html_page_count: number(row?.usable_html_page_count),
    representative_html_page_count: number(row?.representative_html_page_count),
    default_route_page_count: number(row?.default_route_page_count),
    discovery_quality_state: text(row?.discovery_quality_state, 120),
    evidence_quality_gate_version: text(row?.evidence_quality_gate_version, 160),
    crawl_timing: plainObject(row?.crawl_timing),
    sampling_evidence: plainObject(row?.sampling_evidence),
    ...coverageAuthorityFields(row?.coverage_authority_evidence),
  };
}

function acceptanceEvidenceSnapshotFields(row) {
  if (![REVIEW_ATTESTATION_VERSION_V3, REVIEW_ATTESTATION_VERSION_V4].includes(text(row?.authority_seal_version, 160))) return {};
  const source = plainObject(row?.classification_integrity);
  const state = text(source.state, 120);
  const verdict = text(source.verdict, 120);
  const usablePages = acceptanceFiniteNonNegativeNumber(source.usable_pages);
  const workerPeak = acceptancePositiveNumber(row?.worker_peak_memory_bytes ?? row?.peak_memory_bytes);
  if (
    !text(row?.coverage_authority_evidence?.coverage_authority_evidence_version, 160)
    || !text(row?.coverage_authority_evidence?.assessment, 120)
    || !text(source.version, 160)
    || !state
    || !verdict
    || state !== verdict
    || !text(source.classifier_version, 160)
    || !text(source.evidence_sufficiency, 120)
    || usablePages === null
    || typeof source.complete_small_site_inventory !== "boolean"
    || workerPeak === null
  ) return {};
  return {
    classification_integrity: {
      version: text(source.version, 160),
      state,
      verdict,
      classifier_version: text(source.classifier_version, 160),
      evidence_sufficiency: text(source.evidence_sufficiency, 120),
      usable_pages: usablePages,
      complete_small_site_inventory: source.complete_small_site_inventory,
    },
    classification_verdict: verdict,
    peak_memory_bytes: workerPeak,
    worker_peak_memory_bytes: workerPeak,
  };
}

function finiteNonNegativeNumber(value) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
}

function positiveNumber(value) {
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? value : null;
}

/** Mirrors coverageAuthorityFields in persistDurableScanAuthority/authoritySnapshot.js. */
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

function nonNegativeInteger(value) {
  return Math.max(0, Math.trunc(number(value)));
}

function domain(value) {
  const raw = text(value, 2_000);
  if (!raw) return "";
  try {
    const parsed = new URL(/^https?:\/\//i.test(raw) ? raw : `https://${raw}`);
    return ["http:", "https:"].includes(parsed.protocol)
      ? parsed.hostname.toLowerCase().replace(/^www\./, "").replace(/\.$/, "")
      : "";
  } catch {
    return "";
  }
}

function canonicalize(value) {
  if (value === null || typeof value === "string" || typeof value === "boolean") return value;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (Array.isArray(value)) return value.map((item) => canonicalize(item));
  if (value && typeof value === "object") {
    return Object.keys(value).sort().reduce((result, key) => {
      const item = value[key];
      if (!["undefined", "function", "symbol"].includes(typeof item)) result[key] = canonicalize(item);
      return result;
    }, {});
  }
  return null;
}

async function importHmacKey(secret, cryptoImpl, usages) {
  const cleanSecret = typeof secret === "string" ? secret : "";
  if (!cleanSecret || !cryptoImpl?.subtle) throw new Error("Authority seal key is unavailable.");
  return cryptoImpl.subtle.importKey(
    "raw",
    ENCODER.encode(cleanSecret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    usages,
  );
}

function bytesToHex(bytes) {
  return [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function hexToBytes(value) {
  const bytes = new Uint8Array(value.length / 2);
  for (let index = 0; index < value.length; index += 2) {
    bytes[index / 2] = Number.parseInt(value.slice(index, index + 2), 16);
  }
  return bytes;
}
