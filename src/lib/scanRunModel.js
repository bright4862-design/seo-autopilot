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

const MODE_PAGE_LIMITS = { basic: 25, quick: 40, deep: 85, advanced: 150 };
const CURRENT_SCANNER_VERSION = "python_scanner_v3_bounded_request";
const CURRENT_SCANNER_BUILD_REVISION = "hard_page_cap_response_v1";
const CURRENT_ARCHETYPE_CLASSIFIER_VERSION = "archetype_classifier_v6_saas_business_identity";
const CURRENT_REVIEW_VERSION = "python_review_v2_structural_marketplace";
const CURRENT_CALIBRATION_VERSION = "review_evidence_calibration_v5_utility_redirect";
const CURRENT_BETA_REVISION_FINGERPRINT = "fa1bfae405d970fa";

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

function modePageLimit(scanMode) {
  return MODE_PAGE_LIMITS[toStr(scanMode).toLowerCase()] || MODE_PAGE_LIMITS.advanced;
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
  };
}

// Compact diagnostics and JSON exports use the same marker names as the
// merged record. Missing markers remain missing; no historical fingerprint is
// inferred because that would misidentify the code that produced the scan.
export function buildDiagnosticAuthorityMarkers(record = {}) {
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

export function buildScanRunFields(record = {}, { status } = {}) {
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
  const inferredReleaseGateEligible = advancedScanBackend === "python_scanner_api"
    && !denoFallbackUsed
    && scannerVersion === CURRENT_SCANNER_VERSION
    && authorityMarkers.scanner_build_revision === CURRENT_SCANNER_BUILD_REVISION
    && authorityMarkers.archetype_classifier_version === CURRENT_ARCHETYPE_CLASSIFIER_VERSION
    && aiReviewBackend === "python_review_api"
    && !pythonReviewFallbackUsed
    && reviewVersion === CURRENT_REVIEW_VERSION
    && calibrationVersion === CURRENT_CALIBRATION_VERSION
    && authorityMarkers.beta_revision_fingerprint === CURRENT_BETA_REVISION_FINGERPRINT;
  const releaseGateEligible = record.release_gate_eligible !== false && inferredReleaseGateEligible;
  return {
    status: status || deriveTerminalStatus(record),
    status_detail: toStr(record.scan_status),
    scanner_version: scannerVersion,
    scanner_build_revision: authorityMarkers.scanner_build_revision,
    advanced_scan_backend: advancedScanBackend,
    deno_fallback_used: denoFallbackUsed,
    review_version: reviewVersion,
    review_evidence_calibration_version: calibrationVersion,
    ai_review_backend: aiReviewBackend,
    python_review_fallback_used: pythonReviewFallbackUsed,
    release_gate_eligible: releaseGateEligible,
    beta_revision_fingerprint: authorityMarkers.beta_revision_fingerprint,
    pages_found: Number(record.pages_found || 0),
    pages_crawled: Math.min(pageLimit, Number(record.pages_crawled || 0)),
    queued_remaining: Number(record.queued_remaining || 0),
    sampling_evidence: record.sampling_evidence || {},
    scan_status: toStr(record.scan_status),
    review_confidence_state: toStr(record.review_confidence_state),
    score_is_provisional: record.score_is_provisional === true,
    access_evidence_state: toStr(record.access_evidence_state),
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

export function buildFixListFields(record = {}, fixes = getFixRecommendations(record)) {
  const counts = { critical: 0, high: 0, medium: 0, low: 0 };
  const releaseGateEligible = buildScanRunFields(record).release_gate_eligible;
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
    affected_pages: toArr(fix.affected_pages).map(toStr).slice(0, 50),
    source_pages: toArr(fix.source_pages).map(toStr).slice(0, 50),
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
