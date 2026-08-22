import { RELEASE_FINGERPRINT } from "./generatedReleaseContract.js";
// Pure mapping logic for the durable scan models (ScanRun / FixList / FixItem).
// No Base44 imports so tests can exercise it directly; persistence lives in
// scanRuns.js. Field names mirror base44/entities/*.jsonc and the
// review-presentation contract — see docs/durable-scan-model.md.

const LIMITED_SCAN_STATUSES = new Set([
  "complete_with_access_limitations",
  "incomplete_evidence",
  "inconclusive_insufficient_evidence",
  "blocked_or_incomplete",
]);

const MODE_PAGE_LIMITS = { standard_150: 150, advanced: 150 };
export const RELEASE_AUTHORITY_CONTRACT = Object.freeze({
  scannerVersion: "python_scanner_v3_bounded_request",
  scannerBuildRevision: "authenticated_health_probe_v1",
  archetypeClassifierVersion: "archetype_classifier_v9_local_business_hospitality",
  reviewVersion: "python_review_v2_structural_marketplace",
  calibrationVersion: "review_evidence_calibration_v6_health_score_v2",
  betaRevisionFingerprint: RELEASE_FINGERPRINT,
});

const {
  scannerVersion: CURRENT_SCANNER_VERSION,
  scannerBuildRevision: CURRENT_SCANNER_BUILD_REVISION,
  archetypeClassifierVersion: CURRENT_ARCHETYPE_CLASSIFIER_VERSION,
  reviewVersion: CURRENT_REVIEW_VERSION,
  calibrationVersion: CURRENT_CALIBRATION_VERSION,
  betaRevisionFingerprint: CURRENT_BETA_REVISION_FINGERPRINT,
} = RELEASE_AUTHORITY_CONTRACT;

export const TERMINAL_SCAN_RUN_STATUSES = new Set(["complete", "limited", "failed", "cancelled"]);

// Python Review decides completeness; the frontend only maps its verdict onto
// the lifecycle. Provisional or limited evidence must never persist as "complete".
export function deriveTerminalStatus(record = {}) {
  if (record?.score_is_provisional === true) return "limited";
  if (LIMITED_SCAN_STATUSES.has(record?.scan_status)) return "limited";
  return "complete";
}

function toStr(value) {
  return typeof value === "string" ? value : value == null ? "" : String(value);
}

function toArr(value) {
  return Array.isArray(value) ? value : [];
}

function normalizeMetadataStateCounts(value = {}) {
  const source = value && typeof value === "object" ? value : {};
  return {
    missing: Math.max(0, Number(source.missing || 0)),
    empty: Math.max(0, Number(source.empty || 0)),
    malformed: Math.max(0, Number(source.malformed || 0)),
  };
}

function modePageLimit(scanMode) {
  return MODE_PAGE_LIMITS[toStr(scanMode).toLowerCase()] || MODE_PAGE_LIMITS.standard_150;
}

function firstPageEvidence(record = {}) {
  return toArr(record.crawled_pages || record.pages || record.scanned_pages || record.crawl_pages)[0] || {};
}

export function getFixRecommendations(record = {}) {
  return toArr(record.recommendations || record.fixes || record.findings).filter(
    (item) => item && typeof item === "object"
  );
}

// Authority markers are copied from the Python response envelopes before the
// merged browser record is compacted. Presentation-only polish/dedup versions
// deliberately do not participate in this mapping.
export function buildAuthorityMarkers(scanData = {}, aiData = {}) {
  const firstPage = firstPageEvidence(scanData);
  return {
    scanner_build_revision: toStr(
      scanData.scanner_build_revision || scanData.technical_audit_summary?.scanner_build_revision
    ),
    archetype_classifier_version: toStr(
      aiData.archetype_classifier_version
      || aiData.site_fingerprint?.classification?.classifier_version
    ),
    review_version: toStr(aiData.review_version || aiData.ai_review_version),
    review_evidence_calibration_version: toStr(aiData.review_evidence_calibration_version),
    beta_revision_fingerprint: toStr(
      aiData.beta_revision_fingerprint || scanData.beta_revision_fingerprint
    ),
    metadata_evidence_version: toStr(
      aiData.metadata_evidence_version
      || scanData.metadata_evidence_version
      || scanData.component_versions?.metadata_evidence_version
      || firstPage.metadata_evidence_version
    ),
    title_evidence_version: toStr(
      aiData.title_evidence_version
      || scanData.title_evidence_version
      || scanData.component_versions?.title_evidence_version
      || firstPage.title_evidence_version
    ),
  };
}

// Compact diagnostics and JSON exports use the same marker names as the
// merged record. Missing markers remain missing; no historical fingerprint is
// inferred because that would misidentify the code that produced the scan.
export function buildDiagnosticAuthorityMarkers(record = {}) {
  const firstPage = firstPageEvidence(record);
  return {
    scanner_build_revision: toStr(
      record.scanner_build_revision || record.technical_audit_summary?.scanner_build_revision
    ),
    archetype_classifier_version: toStr(
      record.archetype_classifier_version
      || record.site_fingerprint?.classification?.classifier_version
    ),
    review_version: toStr(record.review_version || record.ai_review_version),
    review_evidence_calibration_version: toStr(record.review_evidence_calibration_version),
    beta_revision_fingerprint: toStr(record.beta_revision_fingerprint),
    metadata_evidence_version: toStr(
      record.metadata_evidence_version
      || record.component_versions?.metadata_evidence_version
      || firstPage.metadata_evidence_version
    ),
    title_evidence_version: toStr(
      record.title_evidence_version
      || record.component_versions?.title_evidence_version
      || firstPage.title_evidence_version
    ),
  };
}

// Stable identity for matching a finding across scans. rule + scope + family
// covers grouped findings; the representative URL disambiguates page-scoped ones.
export function fixLineageKey(fix = {}) {
  const scope = toStr(fix.page_scope) || "page";
  const url = scope === "page" ? toStr(fix.page_url || toArr(fix.affected_pages)[0]) : "";
  return [toStr(fix.rule) || toStr(fix.issue_title || fix.title), scope, toStr(fix.page_template_family), url]
    .join("|")
    .toLowerCase();
}

const AUTHORITY_PROOF_RE = /^[a-f0-9]{64}$/;

// A durable seal written by persistScanAuthority, which verifies a signed
// review attestation and re-reads every row before reporting success.
// Checked as stored, not normalised: the contract is 64 lowercase hex, so an
// uppercase or mixed-case value is a proof this pipeline did not write and
// must not be silently accepted.
export function hasAuthorityProof(record = {}) {
  return AUTHORITY_PROOF_RE.test(toStr(record.authority_proof));
}

// requireAuthorityProof: pass true on any path that writes the durable record.
// The version markers below are computed in the browser from response fields,
// so they are a necessary precondition for release authority but prove nothing
// on their own -- only the server seal does.
export function buildScanRunFields(record = {}, { status, requireAuthorityProof = false } = {}) {
  const pageLimit = modePageLimit(record.scan_mode);
  const authorityMarkers = buildDiagnosticAuthorityMarkers(record);
  const scannerVersion = toStr(record.scanner_version || record.technical_audit_summary?.scanner_version || record.debug?.scanner_version);
  const advancedScanBackend = toStr(record.advanced_scan_backend || record.technical_audit_summary?.advanced_scan_backend)
    || (scannerVersion.startsWith("python_scanner_") ? "python_scanner_api" : "");
  const denoFallbackUsed = record.deno_fallback_used === true || record.technical_audit_summary?.deno_fallback_used === true;
  const aiReviewBackend = toStr(record.ai_review_backend || record.debug?.ai_review_backend);
  const pythonReviewFallbackUsed = record.python_review_fallback_used === true || record.debug?.python_review_fallback_used === true;
  const reviewVersion = authorityMarkers.review_version;
  const calibrationVersion = authorityMarkers.review_evidence_calibration_version;
  const pagesCrawled = Math.min(pageLimit, Number(record.pages_crawled || 0));
  const pagesRetained = Math.min(
    pageLimit,
    Number(record.pages_retained || record.technical_audit_summary?.pages_retained || toArr(record.pages).length || 0)
  );
  const localCacheComplete = typeof record.local_cache_complete === "boolean"
    ? record.local_cache_complete
    : pagesRetained >= pagesCrawled;
  const terminalStatus = deriveTerminalStatus(record);
  const inferredReleaseGateEligible = terminalStatus === "complete"
    && record.score_is_provisional !== true
    && advancedScanBackend === "python_scanner_api"
    && !denoFallbackUsed
    && scannerVersion === CURRENT_SCANNER_VERSION
    && authorityMarkers.scanner_build_revision === CURRENT_SCANNER_BUILD_REVISION
    && authorityMarkers.archetype_classifier_version === CURRENT_ARCHETYPE_CLASSIFIER_VERSION
    && aiReviewBackend === "python_review_api"
    && !pythonReviewFallbackUsed
    && reviewVersion === CURRENT_REVIEW_VERSION
    && calibrationVersion === CURRENT_CALIBRATION_VERSION
    && record.evidence_quality_blocking !== true
    && authorityMarkers.beta_revision_fingerprint === CURRENT_BETA_REVISION_FINGERPRINT;
  // Durable writes must never claim release authority the server has not
  // sealed. ScanRun 6a7378546447b124a1afd2d5 was written release_gate_eligible
  // with authority_proof null because this value was re-inferred from version
  // strings, silently discarding the explicit false the caller had set.
  const releaseGateEligible = requireAuthorityProof
    ? inferredReleaseGateEligible && hasAuthorityProof(record)
    : inferredReleaseGateEligible;
  return {
    status: status || terminalStatus,
    status_detail: toStr(record.scan_status),
    scanner_version: scannerVersion,
    scanner_build_revision: authorityMarkers.scanner_build_revision,
    advanced_scan_backend: advancedScanBackend,
    deno_fallback_used: denoFallbackUsed,
    archetype_classifier_version: authorityMarkers.archetype_classifier_version,
    review_version: reviewVersion,
    review_evidence_calibration_version: calibrationVersion,
    ai_review_backend: aiReviewBackend,
    python_review_fallback_used: pythonReviewFallbackUsed,
    release_gate_eligible: releaseGateEligible,
    // Limited-result provenance. Carried through so a verified provisional row
    // stays readable, and stays visibly distinct from an authoritative one.
    result_integrity_version: toStr(record.result_integrity_version),
    result_integrity_proof: toStr(record.result_integrity_proof),
    beta_revision_fingerprint: authorityMarkers.beta_revision_fingerprint,
    metadata_evidence_version: authorityMarkers.metadata_evidence_version,
    title_evidence_version: authorityMarkers.title_evidence_version,
    pages_found: Number(record.pages_found || 0),
    pages_crawled: pagesCrawled,
    pages_retained: pagesRetained,
    local_cache_complete: localCacheComplete,
    queued_remaining: Number(record.queued_remaining || 0),
    sampling_evidence: record.sampling_evidence || {},
    crawl_timing: record.crawl_timing || record.technical_audit_summary?.crawl_timing || {},
    scan_status: toStr(record.scan_status),
    review_confidence_state: toStr(record.review_confidence_state),
    score_is_provisional: record.score_is_provisional === true,
    access_evidence_state: toStr(record.access_evidence_state),
    evidence_quality_state: toStr(record.evidence_quality_state),
    evidence_quality_score: Number(record.evidence_quality_score || 0),
    evidence_quality_reasons: toArr(record.evidence_quality_reasons).map(toStr).filter(Boolean).slice(0, 12),
    discovery_quality_state: toStr(record.discovery_quality_state),
    representative_html_page_count: Number(record.representative_html_page_count || 0),
    usable_html_page_count: Number(record.usable_html_page_count || 0),
    default_route_page_count: Number(record.default_route_page_count || 0),
    evidence_quality_blocking: record.evidence_quality_blocking === true,
    evidence_quality_gate_version: toStr(record.evidence_quality_gate_version),
    no_high_confidence_findings: record.no_high_confidence_findings === true,
    limitation: toStr(record.limitation),
    render_evidence: record.render_evidence || {},
    health_score: Number(record.health_score || 0),
    health_grade: toStr(record.health_grade),
    customer_summary: toStr(record.customer_summary || record.simple_summary),
    next_best_step: toStr(record.next_best_step),
    completed_at: toStr(record.created_at) || new Date().toISOString(),
  };
}

export function buildFixListFields(record = {}, fixes = getFixRecommendations(record), { requireAuthorityProof = false } = {}) {
  const counts = { critical: 0, high: 0, medium: 0, low: 0 };
  const releaseGateEligible = buildScanRunFields(record, { requireAuthorityProof }).release_gate_eligible;
  for (const fix of fixes) {
    const priority = toStr(fix.priority).toLowerCase();
    if (priority in counts) counts[priority] += 1;
    else counts.medium += 1;
  }
  return {
    website_url: toStr(record.website_url),
    ai_review_backend: toStr(record.ai_review_backend),
    python_review_fallback_used: record.python_review_fallback_used === true,
    is_authoritative: releaseGateEligible,
    health_score: Number(record.health_score || 0),
    health_grade: toStr(record.health_grade),
    scan_status: toStr(record.scan_status),
    score_is_provisional: record.score_is_provisional === true,
    no_high_confidence_findings: record.no_high_confidence_findings === true,
    total_fixes: fixes.length,
    critical_count: counts.critical,
    high_count: counts.high,
    medium_count: counts.medium,
    low_count: counts.low,
    completed_count: 0,
    top_action_fix_ids: fixes.slice(0, 3).map((fix) => toStr(fix.fix_id || fix.id)).filter(Boolean),
    generated_at: new Date().toISOString(),
  };
}

const FIX_PRIORITIES = new Set(["critical", "high", "medium", "low"]);
const FIX_SCOPES = new Set(["page", "family", "cross_cutting", "sitewide"]);

// previousItems: FixItem rows from the prior completed run, used for lineage.
export function buildFixItemFields(fix = {}, { scanRunId = "", previousItems = [] } = {}) {
  const previousByKey = new Map(previousItems.map((item) => [item.lineage_key || fixLineageKey(item), item]));
  const key = fixLineageKey(fix);
  const previous = previousByKey.get(key);
  const priority = toStr(fix.priority).toLowerCase();
  const scope = toStr(fix.page_scope);
  return {
    fix_id: toStr(fix.fix_id || fix.id),
    rule: toStr(fix.rule),
    category: toStr(fix.category),
    customer_category: toStr(fix.customer_category),
    issue_title: toStr(fix.issue_title || fix.title) || "Untitled finding",
    plain_english_explanation: toStr(fix.plain_english_explanation || fix.plain_english_summary),
    why_it_matters: toStr(fix.why_it_matters),
    current_value: toStr(fix.current_value),
    recommended_value: toStr(fix.recommended_value || fix.recommendation),
    simple_next_step: toStr(fix.simple_next_step),
    page_scope: FIX_SCOPES.has(scope) ? scope : "page",
    page_template_family: toStr(fix.page_template_family),
    page_url: toStr(fix.page_url || toArr(fix.affected_pages)[0]),
    affected_pages: toArr(fix.affected_pages).map(toStr).slice(0, 150),
    source_pages: toArr(fix.source_pages).map(toStr).slice(0, 150),
    page_count: Number(fix.page_count || toArr(fix.affected_pages).length || 0),
    family_breakdown: fix.family_breakdown && typeof fix.family_breakdown === "object" ? fix.family_breakdown : {},
    representative_pages_by_family: fix.representative_pages_by_family && typeof fix.representative_pages_by_family === "object" ? fix.representative_pages_by_family : {},
    what_to_do_steps: toArr(fix.what_to_do_steps || fix.what_to_do || fix.fix_steps).map(toStr).slice(0, 8),
    metadata_state_counts: normalizeMetadataStateCounts(fix.metadata_state_counts),
    combined_rules: toArr(fix.combined_rules).map(toStr).filter(Boolean).slice(0, 8),
    grouping_explanation: toStr(fix.grouping_explanation),
    evidence_status: toStr(fix.evidence_status),
    verification_state: toStr(fix.verification_state),
    limitation_code: toStr(fix.limitation_code),
    confidence_score: Number(fix.confidence_score || 0),
    priority: FIX_PRIORITIES.has(priority) ? priority : "medium",
    difficulty: toStr(fix.difficulty),
    who_can_do_this: toStr(fix.who_can_do_this),
    requires_developer: fix.requires_developer === true,
    requires_approval: fix.requires_approval === true,
    can_auto_fix: fix.can_auto_fix === true,
    estimated_time: toStr(fix.estimated_time || fix.time_estimate),
    user_status: "open",
    carried_over: Boolean(previous),
    first_seen_scan_run_id: previous ? toStr(previous.first_seen_scan_run_id || previous.scan_run_id) : scanRunId,
    raw_finding: fix,
  };
}
