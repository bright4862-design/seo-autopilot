import { base44 } from "@/api/base44Client";

const SCAN_RECORD_PREFIX = "seo_autopilot:scan:";
const DASHBOARD_LAST_SCAN_KEY = "seo_autopilot:last_scan";
const DASHBOARD_HISTORY_KEY = "seo_autopilot:scan_history";
const LEGACY_LAST_SCAN_KEY = "SEO_AUTOPILOT_LAST_SCAN";
const LEGACY_HISTORY_KEY = "SEO_AUTOPILOT_SCAN_HISTORY";
const SCAN_DEBUG_KEY = "seo_autopilot:scan_debug";

const CURRENT_SCANNER_VERSION = "python_scanner_v3_bounded_request";
const CURRENT_SCANNER_BUILD_REVISION = "hard_page_cap_response_v1";
const CURRENT_ARCHETYPE_CLASSIFIER_VERSION = "archetype_classifier_v8_platform_product_routes";
const CURRENT_REVIEW_VERSION = "python_review_v2_structural_marketplace";
const CURRENT_CALIBRATION_VERSION = "review_evidence_calibration_v5_utility_redirect";
const CURRENT_BETA_REVISION_FINGERPRINT = "52348dd1f3b77700";
const PAGE_LIMITS = { basic: 25, quick: 40, deep: 85, advanced: 150 };
const SCAN_CACHE_KEYS = new Set([
  DASHBOARD_LAST_SCAN_KEY,
  DASHBOARD_HISTORY_KEY,
  LEGACY_LAST_SCAN_KEY,
  LEGACY_HISTORY_KEY,
  SCAN_DEBUG_KEY,
]);

let latestAuthority = {};
let installed = false;

function pageLimit(scanMode) {
  return PAGE_LIMITS[String(scanMode || "advanced").toLowerCase()] || PAGE_LIMITS.advanced;
}

function firstArray(source, keys) {
  for (const key of keys) {
    if (Array.isArray(source?.[key]) && source[key].length > 0) return source[key];
  }
  return [];
}

function finiteNumber(...values) {
  for (const value of values) {
    const number = Number(value);
    if (Number.isFinite(number) && number >= 0) return number;
  }
  return 0;
}

function compactFix(fix = {}) {
  const affectedPages = firstArray(fix, ["affected_pages", "pages", "page_urls"])
    .map(String)
    .slice(0, 50);
  const pageUrl = String(fix.page_url || fix.url || affectedPages[0] || "");
  return {
    id: fix.id || fix.fix_id || "",
    fix_id: fix.fix_id || fix.id || "",
    rule: fix.rule || "",
    category: fix.category || "",
    customer_category: fix.customer_category || "",
    priority: fix.priority || "medium",
    difficulty: fix.difficulty || "",
    status: fix.status || "",
    issue_title: fix.issue_title || fix.title || "",
    title: fix.title || fix.issue_title || "",
    plain_english_explanation: fix.plain_english_explanation || fix.explanation || "",
    why_it_matters: fix.why_it_matters || "",
    recommendation: fix.recommendation || fix.recommended_value || "",
    recommended_value: fix.recommended_value || fix.recommendation || "",
    simple_next_step: fix.simple_next_step || "",
    page_url: pageUrl,
    affected_pages: affectedPages,
    source_pages: firstArray(fix, ["source_pages"]).map(String).slice(0, 30),
    evidence_status: fix.evidence_status || "",
    verification_state: fix.verification_state || "",
    limitation_code: fix.limitation_code || "",
    who_can_do_this: fix.who_can_do_this || "",
    requires_developer: fix.requires_developer === true,
    requires_approval: fix.requires_approval === true,
    can_auto_fix: fix.can_auto_fix === true,
    confidence_score: finiteNumber(fix.confidence_score),
    page_scope: fix.page_scope || "",
    page_template_family: fix.page_template_family || "",
    metadata_state_counts: fix.metadata_state_counts && typeof fix.metadata_state_counts === "object"
      ? {
          missing: finiteNumber(fix.metadata_state_counts.missing),
          empty: finiteNumber(fix.metadata_state_counts.empty, fix.metadata_state_counts.present_empty),
          malformed: finiteNumber(fix.metadata_state_counts.malformed),
        }
      : {},
    combined_rules: firstArray(fix, ["combined_rules"]).map(String).slice(0, 8),
    grouping_explanation: String(fix.grouping_explanation || "").slice(0, 600),
    page_count: finiteNumber(fix.page_count, affectedPages.length),
  };
}

function compactPage(page = {}) {
  return {
    url: page.url || page.final_url || "",
    final_url: page.final_url || page.url || "",
    path: page.path || "",
    status_code: finiteNumber(page.status_code),
    fetch_error: page.fetch_error || "",
    title: String(page.title || "").slice(0, 180),
    title_pixel_width_estimate: finiteNumber(page.title_pixel_width_estimate),
    title_width_state: page.title_width_state || "",
    title_is_generic_fallback: page.title_is_generic_fallback === true,
    title_evidence_version: page.title_evidence_version || "",
    meta_description: String(page.meta_description || "").slice(0, 260),
    meta_description_state: page.meta_description_state || "",
    meta_description_element_count: finiteNumber(page.meta_description_element_count),
    meta_description_values: firstArray(page, ["meta_description_values"])
      .map((value) => String(value).slice(0, 260))
      .slice(0, 4),
    meta_description_duplicate: page.meta_description_duplicate === true,
    metadata_evidence_version: page.metadata_evidence_version || "",
    h1: String(page.h1 || "").slice(0, 180),
    h1_count: finiteNumber(page.h1_count),
    canonical: page.canonical || page.canonical_url || "",
    robots: page.robots || page.robots_meta || "",
    word_count: finiteNumber(page.word_count),
    image_count: finiteNumber(page.image_count),
    image_missing_alt_count: finiteNumber(page.image_missing_alt_count, page.missing_alt_image_count),
    schema_count: finiteNumber(page.schema_count),
    indexable: page.indexable !== false,
    in_sitemap: page.in_sitemap === true,
    client_rendering_suspected: page.client_rendering_suspected === true,
    page_template_family: page.page_template_family || "",
    estimated_page_intent: page.estimated_page_intent || "",
  };
}

function authorityFor(record = {}) {
  const scannerVersion = record.scanner_version
    || record.technical_audit_summary?.scanner_version
    || record.debug?.scanner_version
    || latestAuthority.scanner_version
    || "";
  const scannerBuildRevision = record.scanner_build_revision
    || record.technical_audit_summary?.scanner_build_revision
    || latestAuthority.scanner_build_revision
    || "";
  const scannerBackend = record.advanced_scan_backend
    || record.technical_audit_summary?.advanced_scan_backend
    || latestAuthority.advanced_scan_backend
    || (String(scannerVersion).startsWith("python_scanner_") ? "python_scanner_api" : "");
  const denoFallback = record.deno_fallback_used === true
    || record.technical_audit_summary?.deno_fallback_used === true
    || latestAuthority.deno_fallback_used === true;
  const reviewBackend = record.ai_review_backend
    || record.debug?.ai_review_backend
    || latestAuthority.ai_review_backend
    || "";
  const reviewFallback = record.python_review_fallback_used === true
    || record.debug?.python_review_fallback_used === true
    || latestAuthority.python_review_fallback_used === true;
  const reviewVersion = record.review_version
    || record.ai_review_version
    || latestAuthority.review_version
    || (reviewBackend === "python_review_api" ? CURRENT_REVIEW_VERSION : "");
  const calibrationVersion = record.review_evidence_calibration_version
    || latestAuthority.review_evidence_calibration_version
    || (reviewBackend === "python_review_api" ? CURRENT_CALIBRATION_VERSION : "");
  const classifierVersion = record.archetype_classifier_version
    || record.site_fingerprint?.classification?.classifier_version
    || latestAuthority.archetype_classifier_version
    || "";
  const betaRevisionFingerprint = record.beta_revision_fingerprint
    || record.component_versions?.fingerprint
    || latestAuthority.beta_revision_fingerprint
    || "";
  const metadataEvidenceVersion = record.metadata_evidence_version
    || record.component_versions?.metadata_evidence_version
    || latestAuthority.metadata_evidence_version
    || "";
  const titleEvidenceVersion = record.title_evidence_version
    || record.component_versions?.title_evidence_version
    || latestAuthority.title_evidence_version
    || "";
  const inferredReleaseGateEligible = scannerBackend === "python_scanner_api"
    && !denoFallback
    && scannerVersion === CURRENT_SCANNER_VERSION
    && scannerBuildRevision === CURRENT_SCANNER_BUILD_REVISION
    && classifierVersion === CURRENT_ARCHETYPE_CLASSIFIER_VERSION
    && reviewBackend === "python_review_api"
    && !reviewFallback
    && reviewVersion === CURRENT_REVIEW_VERSION
    && calibrationVersion === CURRENT_CALIBRATION_VERSION
    && betaRevisionFingerprint === CURRENT_BETA_REVISION_FINGERPRINT;
  const releaseGateEligible = record.release_gate_eligible === false
    ? false
    : inferredReleaseGateEligible;
  return {
    scanner_version: scannerVersion,
    scanner_build_revision: scannerBuildRevision,
    advanced_scan_backend: scannerBackend,
    deno_fallback_used: denoFallback,
    archetype_classifier_version: classifierVersion,
    review_version: reviewVersion,
    review_evidence_calibration_version: calibrationVersion,
    ai_review_backend: reviewBackend,
    python_review_fallback_used: reviewFallback,
    beta_revision_fingerprint: betaRevisionFingerprint,
    metadata_evidence_version: metadataEvidenceVersion,
    title_evidence_version: titleEvidenceVersion,
    release_gate_eligible: releaseGateEligible,
  };
}

function compactScanRecord(record = {}, { emergency = false } = {}) {
  if (!record || typeof record !== "object") return record;
  const limit = pageLimit(record.scan_mode);
  const pagePreviewLimit = emergency ? 12 : limit;
  const fixPreviewLimit = emergency ? 12 : 100;
  const pages = firstArray(record, ["crawled_pages", "pages", "scanned_pages", "crawl_pages"])
    .slice(0, pagePreviewLimit)
    .map(compactPage);
  const recommendations = firstArray(record, [
    "cleaned_fixes",
    "recommendations",
    "fixes",
    "findings",
    "raw_fixes",
    "grouped_findings",
    "issues",
  ]).slice(0, fixPreviewLimit).map(compactFix);
  const reportedPages = finiteNumber(
    record.pages_crawled,
    record.pages_scanned,
    record.technical_audit_summary?.pages_crawled,
    pages.length,
  );
  const pagesCrawled = Math.min(limit, reportedPages || pages.length);
  const authority = authorityFor(record);
  const output = {
    id: record.id || record.scan_id || record.scan_run_id || "",
    scan_id: record.scan_id || record.scan_run_id || record.id || "",
    scan_run_id: record.scan_run_id || record.scan_id || record.id || "",
    fix_list_id: record.fix_list_id || "",
    created_at: record.created_at || new Date().toISOString(),
    website_url: record.website_url || "",
    website_key: record.website_key || "",
    business_name: record.business_name || "",
    cms_platform: record.cms_platform || "custom",
    cms_name: record.cms_name || "Custom / Not sure",
    scan_mode: record.scan_mode || "quick",
    health_score: finiteNumber(record.health_score, record.seo_score),
    seo_score: finiteNumber(record.seo_score, record.health_score),
    health_grade: record.health_grade || record.website_health_report?.health_grade || "",
    pages_crawled: pagesCrawled,
    pages_retained: pages.length,
    pages_found: finiteNumber(record.pages_found, record.technical_audit_summary?.pages_found, pagesCrawled),
    scan_status: record.scan_status || "",
    review_confidence_state: record.review_confidence_state || "",
    score_is_provisional: record.score_is_provisional === true,
    access_evidence_state: record.access_evidence_state || "",
    no_high_confidence_findings: record.no_high_confidence_findings === true,
    limitation: record.limitation || "",
    customer_summary: String(record.customer_summary || record.simple_summary || "").slice(0, emergency ? 900 : 4000),
    simple_summary: String(record.simple_summary || record.customer_summary || "").slice(0, emergency ? 900 : 4000),
    next_best_step: String(record.next_best_step || record.website_health_report?.next_best_step || "").slice(0, 600),
    recommendations,
    pages,
    top_recommended_actions: firstArray(record, ["top_recommended_actions"]).slice(0, 5),
    sampling_version: record.sampling_version || "",
    sampling_evidence: emergency ? {} : (record.sampling_evidence || {}),
    site_fingerprint: emergency ? {} : (record.site_fingerprint || record.scan_summary?.site_fingerprint || {}),
    archetype_playbook: emergency ? {} : (record.archetype_playbook || {}),
    url_evidence_summary: emergency ? {} : (record.url_evidence_summary || {}),
    technical_audit_summary: {
      scanner_version: authority.scanner_version,
      scanner_build_revision: authority.scanner_build_revision,
      advanced_scan_backend: authority.advanced_scan_backend,
      deno_fallback_used: authority.deno_fallback_used,
      pages_crawled: pagesCrawled,
      pages_retained: pages.length,
      pages_found: finiteNumber(record.pages_found, record.technical_audit_summary?.pages_found, pagesCrawled),
    },
    local_cache_complete: pages.length >= pagesCrawled,
    ...authority,
  };
  return output;
}

function compactHistoryEntry(record = {}) {
  const compact = compactScanRecord(record, { emergency: true });
  return {
    id: compact.id,
    scan_id: compact.scan_id,
    scan_run_id: compact.scan_run_id,
    fix_list_id: compact.fix_list_id,
    storage_key: compact.scan_id ? `${SCAN_RECORD_PREFIX}${compact.scan_id}` : "",
    created_at: compact.created_at,
    website_url: compact.website_url,
    business_name: compact.business_name,
    scan_mode: compact.scan_mode,
    health_score: compact.health_score,
    health_grade: compact.health_grade,
    pages_crawled: compact.pages_crawled,
    pages_retained: compact.pages_retained,
    pages_found: compact.pages_found,
    local_cache_complete: compact.local_cache_complete,
    scan_status: compact.scan_status,
    beta_revision_fingerprint: compact.beta_revision_fingerprint,
    release_gate_eligible: compact.release_gate_eligible,
  };
}

function parseJson(value) {
  try { return JSON.parse(String(value)); } catch { return null; }
}

function isQuotaError(error) {
  return error?.name === "QuotaExceededError"
    || error?.code === 22
    || error?.code === 1014
    || /quota|storage.*full/i.test(String(error?.message || error || ""));
}

function scanCacheKey(key = "") {
  return key.startsWith(SCAN_RECORD_PREFIX) || SCAN_CACHE_KEYS.has(key);
}

function pruneOldScanRecords(storage, originalRemoveItem, keepKey = "") {
  const keys = [];
  for (let index = 0; index < storage.length; index += 1) {
    const key = storage.key(index) || "";
    if (key.startsWith(SCAN_RECORD_PREFIX) && key !== keepKey) keys.push(key);
  }
  for (const key of keys) originalRemoveItem.call(storage, key);
  for (const key of [DASHBOARD_LAST_SCAN_KEY, DASHBOARD_HISTORY_KEY, LEGACY_LAST_SCAN_KEY, LEGACY_HISTORY_KEY, SCAN_DEBUG_KEY]) {
    originalRemoveItem.call(storage, key);
  }
}

function transformStorageValue(key, value, emergency = false) {
  const parsed = parseJson(value);
  if (!parsed) return value;
  if (key.startsWith(SCAN_RECORD_PREFIX)) return JSON.stringify(compactScanRecord(parsed, { emergency }));
  if (key === DASHBOARD_LAST_SCAN_KEY || key === LEGACY_LAST_SCAN_KEY) {
    return JSON.stringify(compactScanRecord(parsed, { emergency: true }));
  }
  if (key === DASHBOARD_HISTORY_KEY || key === LEGACY_HISTORY_KEY) {
    const entries = Array.isArray(parsed) ? parsed : [];
    return JSON.stringify(entries.slice(0, 20).map(compactHistoryEntry));
  }
  if (key === SCAN_DEBUG_KEY) {
    return JSON.stringify({
      status: parsed.status || "",
      stage: parsed.stage || "",
      updated_at: parsed.updated_at || new Date().toISOString(),
      website_url: parsed.website_url || "",
      scan_mode: parsed.scan_mode || "",
      error: parsed.error || "",
      scanner: parsed.scanner ? compactScanRecord(parsed.scanner, { emergency: true }) : null,
      ai_review: parsed.ai_review ? {
        success: parsed.ai_review.success,
        ai_review_backend: parsed.ai_review.ai_review_backend || "",
        python_review_fallback_used: parsed.ai_review.python_review_fallback_used === true,
        beta_revision_fingerprint: parsed.ai_review.beta_revision_fingerprint || "",
        health_score: finiteNumber(parsed.ai_review.health_score),
      } : null,
      final_record: parsed.final_record ? compactScanRecord(parsed.final_record, { emergency: true }) : null,
    });
  }
  return value;
}

function installStorageBoundary() {
  if (installed || typeof window === "undefined" || !window.localStorage) return;
  installed = true;
  const storage = window.localStorage;
  const originalSetItem = Storage.prototype.setItem;
  const originalRemoveItem = Storage.prototype.removeItem;

  Storage.prototype.setItem = function patchedSetItem(key, value) {
    if (this !== storage || !scanCacheKey(String(key || ""))) return originalSetItem.call(this, key, value);
    const storageKey = String(key || "");
    const keepKey = storageKey.startsWith(SCAN_RECORD_PREFIX) ? storageKey : "";
    const compactValue = transformStorageValue(storageKey, value, false);
    try {
      return originalSetItem.call(this, storageKey, compactValue);
    } catch (error) {
      if (!isQuotaError(error)) {
        console.warn("Could not write optional FixList browser cache.", error);
        return undefined;
      }
      pruneOldScanRecords(this, originalRemoveItem, keepKey);
      try {
        return originalSetItem.call(this, storageKey, transformStorageValue(storageKey, value, true));
      } catch (retryError) {
        console.warn("FixList browser cache is unavailable; durable scan history remains authoritative.", retryError);
        return undefined;
      }
    }
  };

  Storage.prototype.removeItem = function patchedRemoveItem(key) {
    if (this !== storage) return originalRemoveItem.call(this, key);
    const storageKey = String(key || "");
    const result = originalRemoveItem.call(this, storageKey);
    if (storageKey === DASHBOARD_HISTORY_KEY || storageKey === LEGACY_HISTORY_KEY) {
      const prefixedKeys = [];
      for (let index = 0; index < this.length; index += 1) {
        const candidate = this.key(index) || "";
        if (candidate.startsWith(SCAN_RECORD_PREFIX)) prefixedKeys.push(candidate);
      }
      for (const candidate of prefixedKeys) originalRemoveItem.call(this, candidate);
    }
    return result;
  };
}

function findPayload(value, predicate, depth = 0) {
  if (!value || typeof value !== "object" || depth > 6) return null;
  if (predicate(value)) return value;
  for (const key of ["data", "result", "body", "payload"]) {
    const match = findPayload(value[key], predicate, depth + 1);
    if (match) return match;
  }
  return null;
}

function capScannerContainer(container, limit) {
  if (!container || typeof container !== "object") return;
  const pages = firstArray(container, ["crawled_pages", "pages", "scanned_pages", "crawl_pages"]);
  const capped = pages.slice(0, limit);
  const reported = finiteNumber(container.pages_crawled, container.pages_scanned, container.technical_audit_summary?.pages_crawled, capped.length);
  const pagesCrawled = Math.min(limit, reported || capped.length);
  for (const key of ["crawled_pages", "pages", "scanned_pages", "crawl_pages"]) {
    if (Array.isArray(container[key])) container[key] = container[key].slice(0, limit);
  }
  container.pages_crawled = pagesCrawled;
  container.pages_retained = capped.length;
  if (container.technical_audit_summary && typeof container.technical_audit_summary === "object") {
    container.technical_audit_summary.pages_crawled = pagesCrawled;
    container.technical_audit_summary.pages_retained = capped.length;
  }
  if (container.scan_summary && typeof container.scan_summary === "object") {
    if ("pages_scanned" in container.scan_summary) container.scan_summary.pages_scanned = Math.min(limit, finiteNumber(container.scan_summary.pages_scanned, pagesCrawled));
    if ("pages_crawled" in container.scan_summary) container.scan_summary.pages_crawled = Math.min(limit, finiteNumber(container.scan_summary.pages_crawled, pagesCrawled));
  }
  for (const key of ["data", "result", "body", "payload"]) capScannerContainer(container[key], limit);
}

function installFunctionBoundary() {
  if (!base44?.functions?.invoke || base44.functions.invoke.__scanRecoveryWrapped) return;
  const originalInvoke = base44.functions.invoke.bind(base44.functions);
  const wrappedInvoke = async (functionName, payload, ...rest) => {
    const response = await originalInvoke(functionName, payload, ...rest);
    if (functionName === "runAdvancedScan") {
      const limit = pageLimit(payload?.scan_mode);
      capScannerContainer(response, limit);
      const scan = findPayload(response, (value) => Boolean(value.scanner_version || value.advanced_scan_backend));
      if (scan) {
        const firstPage = firstArray(scan, ["crawled_pages", "pages", "scanned_pages", "crawl_pages"])[0] || {};
        latestAuthority = {
          ...latestAuthority,
          scanner_version: scan.scanner_version || scan.version || "",
          scanner_build_revision: scan.scanner_build_revision || scan.technical_audit_summary?.scanner_build_revision || "",
          advanced_scan_backend: scan.advanced_scan_backend || scan.technical_audit_summary?.advanced_scan_backend || "",
          deno_fallback_used: scan.deno_fallback_used === true || scan.technical_audit_summary?.deno_fallback_used === true,
          beta_revision_fingerprint: scan.beta_revision_fingerprint || scan.fingerprint || "",
          metadata_evidence_version: scan.metadata_evidence_version || scan.component_versions?.metadata_evidence_version || firstPage.metadata_evidence_version || "",
          title_evidence_version: scan.title_evidence_version || scan.component_versions?.title_evidence_version || firstPage.title_evidence_version || "",
        };
      }
    }
    if (functionName === "aiReviewScan") {
      const review = findPayload(response, (value) => Boolean(value.ai_review_backend || value.review_version || value.ai_review_version));
      if (review) {
        latestAuthority = {
          ...latestAuthority,
          archetype_classifier_version: review.archetype_classifier_version || review.site_fingerprint?.classification?.classifier_version || "",
          review_version: review.review_version || review.ai_review_version || "",
          review_evidence_calibration_version: review.review_evidence_calibration_version || "",
          ai_review_backend: review.ai_review_backend || "",
          python_review_fallback_used: review.python_review_fallback_used === true,
          beta_revision_fingerprint: review.beta_revision_fingerprint || latestAuthority.beta_revision_fingerprint || "",
          metadata_evidence_version: review.metadata_evidence_version || review.component_versions?.metadata_evidence_version || latestAuthority.metadata_evidence_version || "",
          title_evidence_version: review.title_evidence_version || review.component_versions?.title_evidence_version || latestAuthority.title_evidence_version || "",
        };
      }
    }
    return response;
  };
  wrappedInvoke.__scanRecoveryWrapped = true;
  base44.functions.invoke = wrappedInvoke;
}

installStorageBoundary();
installFunctionBoundary();

export { compactScanRecord, pageLimit };
