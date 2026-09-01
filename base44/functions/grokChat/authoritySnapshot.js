export const REPAIR_CONTRACT_V2 = "repair_contract_v2_shadow_calibrated";
export const REPAIR_PRIORITY_MODEL_V2 = "repair_priority_v2_technical_severity";

export function authoritySnapshotFromRows({ scan, fixList, fixItems, userId }) {
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
    version: text(scan?.authority_seal_version, 160),
    sealed_at: text(scan?.authority_sealed_at, 80),
    owner_user_id: text(userId, 160),
    scan_id: text(scan?.id, 160),
    project_id: text(scan?.project_id, 160),
    normalized_domain: domain(scan?.normalized_domain || scan?.website_url),
    release_fingerprint: text(scan?.beta_revision_fingerprint, 160),
    scan: {
      status: text(scan?.status, 80),
      release_gate_eligible: scan?.release_gate_eligible === true,
      score_is_provisional: scan?.score_is_provisional === true,
      evidence_quality_blocking: scan?.evidence_quality_blocking === true,
      website_url: text(scan?.website_url, 2_000),
      normalized_domain: domain(scan?.normalized_domain || scan?.website_url),
      ...scopeSnapshotFields(scan),
      scanner_version: text(scan?.scanner_version, 160),
      scanner_build_revision: text(scan?.scanner_build_revision, 160),
      scanner_wrapper_version: text(scan?.scanner_wrapper_version, 160),
      advanced_scan_backend: text(scan?.advanced_scan_backend, 160),
      deno_fallback_used: scan?.deno_fallback_used === true,
      archetype_classifier_version: text(scan?.archetype_classifier_version, 160),
      review_version: text(scan?.review_version, 160),
      review_evidence_calibration_version: text(scan?.review_evidence_calibration_version, 160),
      ai_review_backend: text(scan?.ai_review_backend, 160),
      python_review_fallback_used: scan?.python_review_fallback_used === true,
      beta_revision_fingerprint: text(scan?.beta_revision_fingerprint, 160),
      metadata_evidence_version: text(scan?.metadata_evidence_version, 160),
      title_evidence_version: text(scan?.title_evidence_version, 160),
      pages_found: number(scan?.pages_found),
      pages_crawled: number(scan?.pages_crawled),
      scan_status: text(scan?.scan_status, 120),
      review_confidence_state: text(scan?.review_confidence_state, 120),
      evidence_quality_state: text(scan?.evidence_quality_state, 120),
      evidence_quality_score: number(scan?.evidence_quality_score),
      evidence_quality_reasons: textArray(scan?.evidence_quality_reasons, 12, 500),
      // Coverage/inventory diagnostics, present in v2 and carried forward by v3.
      // A row sealed under v1 must be rebuilt exactly as v1 or its stored
      // proof stops verifying and an intact result reads as tampered.
      ...coverageSnapshotFields(scan),
      ...acceptanceEvidenceSnapshotFields(scan),
      health_score: number(scan?.health_score),
      health_grade: text(scan?.health_grade, 80),
      customer_summary: text(scan?.customer_summary, 4_000),
      next_best_step: text(scan?.next_best_step, 2_000),
      no_high_confidence_findings: scan?.no_high_confidence_findings === true,
      completed_at: text(scan?.completed_at, 80),
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
    raw_finding: { verified_urls: verifiedUrls(raw.verified_urls || raw.url_evidence) },
  };
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
  if (![REVIEW_ATTESTATION_VERSION_V3, REVIEW_ATTESTATION_VERSION_V4].includes(
    text(row?.authority_seal_version, 160),
  )) return {};
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

function acceptanceFiniteNonNegativeNumber(value) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
}

function acceptancePositiveNumber(value) {
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
