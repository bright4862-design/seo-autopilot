export const REVIEW_ATTESTATION_VERSION = "standard_review_snapshot_hmac_v1";
export const MAX_AUTHORITY_FIXES = 100;

export const AUTHORITY_CONTRACT = Object.freeze({
  scanner_version: "python_scanner_v3_bounded_request",
  scanner_build_revision: "authenticated_health_probe_v1",
  archetype_classifier_version: "archetype_classifier_v9_local_business_hospitality",
  review_version: "python_review_v2_structural_marketplace",
  review_evidence_calibration_version: "review_evidence_calibration_v5_utility_redirect",
  beta_revision_fingerprint: "5caec7fdcabceee7",
});

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
  ];
  return predicates.find(([, passed]) => !passed)?.[0] || "";
}

export function isAuthorityEligible(scan, review) {
  return firstFailedAuthorityPredicate(scan, review) === "";
}

export function buildAuthoritySnapshot({ scan, review, identity, userId, now = new Date().toISOString() }) {
  const firstPage = firstArray([scan?.crawled_pages, scan?.pages, scan?.scanned_pages])[0] || {};
  const fixes = firstArray([
    review?.recommendations,
    review?.fixes,
    review?.findings,
    review?.cleaned_fixes,
    review?.recommended_actions,
  ]).slice(0, MAX_AUTHORITY_FIXES).map(toAuthorityFix)
    .sort((left, right) => left.fix_id.localeCompare(right.fix_id));
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
      generated_at: String(now),
    },
    recommendations: fixes,
  };
}

function toAuthorityFix(fix, index) {
  const priority = ["critical", "high", "medium", "low"].includes(String(fix?.priority || "").toLowerCase())
    ? String(fix.priority).toLowerCase()
    : "medium";
  const scope = ["page", "family", "cross_cutting", "sitewide"].includes(String(fix?.page_scope || ""))
    ? String(fix.page_scope)
    : "page";
  const affectedPages = textArray(fix?.affected_pages, 150, 2_000);
  const raw = fix?.raw_finding && typeof fix.raw_finding === "object" ? fix.raw_finding : {};
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
    raw_finding: { verified_urls: verifiedUrls(raw.verified_urls || raw.url_evidence) },
  };
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
