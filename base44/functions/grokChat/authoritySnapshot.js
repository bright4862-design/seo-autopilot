export function authoritySnapshotFromRows({ scan, fixList, fixItems, userId }) {
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
      generated_at: text(fixList?.generated_at, 80),
    },
    recommendations: (fixItems || []).map(authorityFixFromRow)
      .sort((left, right) => left.fix_id.localeCompare(right.fix_id)),
  };
}

function authorityFixFromRow(item) {
  const raw = item?.raw_finding && typeof item.raw_finding === "object" ? item.raw_finding : {};
  return {
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
