const COMPLETE = "complete";
const REPRESENTATIVE_SAMPLE = "representative_sample";
const INCOMPLETE_EVIDENCE = "incomplete_evidence";
const ACCESS_LIMITED = "access_limited";
const METADATA_ONLY = "metadata_only";

export function getEvidenceQuality(scanRecord = {}, pages = [], recommendations = []) {
  const safePages = Array.isArray(pages) ? pages : [];
  const safeRecommendations = Array.isArray(recommendations) ? recommendations : [];

  const pagesCrawled = firstNumber([
    scanRecord?.pages_crawled,
    scanRecord?.scan_coverage?.pages_crawled,
    scanRecord?.technical_audit_summary?.pages_crawled,
    safePages.length,
  ]);
  const pagesFound = firstNumber([
    scanRecord?.pages_found,
    scanRecord?.scan_coverage?.pages_found,
    scanRecord?.technical_audit_summary?.pages_found,
    pagesCrawled,
  ]);
  const queuedRemaining = firstNumber([
    scanRecord?.queued_remaining,
    scanRecord?.scan_coverage?.queued_remaining,
    scanRecord?.technical_audit_summary?.queued_remaining,
  ]);
  const pagesReceived = safePages.length || firstNumber([
    scanRecord?.site_fingerprint?.sampled_pages_sent_to_ai,
    scanRecord?.review_input_quality?.pages_received,
    scanRecord?.review_input_quality?.sampled_pages_sent_to_ai,
  ]);
  const blockedPages = countBlockedPages(safePages, safeRecommendations, scanRecord);
  const evidenceComplete = scanRecord?.evidence_complete ?? scanRecord?.review_input_quality?.evidence_complete;
  const scanStatus = String(scanRecord?.scan_status || scanRecord?.review_input_quality?.scan_status || "").toLowerCase();
  const fallbackUsed = Boolean(scanRecord?.python_review_fallback_used || scanRecord?.deno_fallback_used);
  const contractVersion = scanRecord?.review_evidence_contract_version || scanRecord?.deno_fallback_evidence_contract || "";

  const metadataOnly = pagesCrawled > 0 && pagesReceived === 0;
  const accessLimited = blockedPages >= Math.max(2, Math.ceil(Math.max(pagesReceived, pagesCrawled, 1) * 0.25)) || hasAny(scanStatus, ["blocked", "rate", "access_limited"]);
  const incomplete = evidenceComplete === false || hasAny(scanStatus, ["incomplete", "metadata_only"]) || metadataOnly;
  const representative = pagesFound > pagesCrawled || queuedRemaining > 0;

  if (metadataOnly) {
    return buildEvidenceState({
      state: METADATA_ONLY,
      severity: "danger",
      label: "Metadata-only review",
      message: "FixList received scan metadata, but page evidence did not fully reach AI Review. Rerun the scan before changing page content.",
      pagesCrawled,
      pagesFound,
      pagesReceived,
      queuedRemaining,
      blockedPages,
      fallbackUsed,
      contractVersion,
      showHealthScore: false,
    });
  }

  if (accessLimited) {
    return buildEvidenceState({
      state: ACCESS_LIMITED,
      severity: "warning",
      label: "Access limited",
      message: "FixList could not inspect enough pages because access was blocked or rate limited. Ask your web person to check crawler access before changing page content.",
      pagesCrawled,
      pagesFound,
      pagesReceived,
      queuedRemaining,
      blockedPages,
      fallbackUsed,
      contractVersion,
      showHealthScore: false,
    });
  }

  if (incomplete) {
    return buildEvidenceState({
      state: INCOMPLETE_EVIDENCE,
      severity: "warning",
      label: "Scan incomplete",
      message: "FixList understood part of the website, but the page evidence was incomplete. Rerun the scan before making content changes.",
      pagesCrawled,
      pagesFound,
      pagesReceived,
      queuedRemaining,
      blockedPages,
      fallbackUsed,
      contractVersion,
      showHealthScore: false,
    });
  }

  if (representative) {
    return buildEvidenceState({
      state: REPRESENTATIVE_SAMPLE,
      severity: "info",
      label: "Representative sample",
      message: "FixList checked a representative sample of this larger site. Repeated issues are grouped by page type.",
      pagesCrawled,
      pagesFound,
      pagesReceived,
      queuedRemaining,
      blockedPages,
      fallbackUsed,
      contractVersion,
      showHealthScore: true,
    });
  }

  return buildEvidenceState({
    state: COMPLETE,
    severity: "success",
    label: "Evidence complete",
    message: "FixList inspected page evidence and produced recommendations from the crawl.",
    pagesCrawled,
    pagesFound,
    pagesReceived,
    queuedRemaining,
    blockedPages,
    fallbackUsed,
    contractVersion,
    showHealthScore: true,
  });
}

export function shouldShowHealthScore(evidenceQuality) {
  return Boolean(evidenceQuality?.showHealthScore);
}

export function getSiteUnderstanding(scanRecord = {}, pages = []) {
  const fingerprint = scanRecord?.site_fingerprint || scanRecord?.scan_summary?.site_fingerprint || {};
  const safePages = Array.isArray(pages) ? pages : [];
  const pagesCrawled = firstNumber([fingerprint.pages_crawled, scanRecord?.pages_crawled, safePages.length]);
  const pagesFound = firstNumber([fingerprint.pages_found, scanRecord?.pages_found, pagesCrawled]);
  const archetype = fingerprint.primary_archetype || fingerprint.vertical || "general";
  const businessModel = fingerprint.business_model || "content_or_general_business";
  const priorityPages = firstArray([fingerprint.archetype_priority_pages, fingerprint.priority_pages]);
  const priorityIssues = firstArray([fingerprint.archetype_priority_issues, fingerprint.priority_issues]);

  return {
    archetype,
    archetypeLabel: fingerprint.archetype_label || fingerprint.vertical_label || humanize(archetype),
    businessModel,
    businessModelLabel: humanize(businessModel),
    pagesCrawled,
    pagesFound,
    sizeBand: fingerprint.size_band || sizeBandFromPages(Math.max(pagesFound, pagesCrawled)),
    priorityPages,
    priorityIssues,
    blockedAccessPages: firstNumber([fingerprint.blocked_access_pages]),
    routeBoundaryRisk: fingerprint.route_boundary_risk || "low",
  };
}

export function normalizeFixEvidence(fix = {}) {
  const affectedPages = unique(firstArray([fix.affected_pages, fix.pages, fix.page_urls, fix.urls]).map(cleanPath).filter(Boolean));
  const pageUrl = cleanPath(fix.page_url || fix.url || affectedPages[0] || "");
  const sourcePages = unique(firstArray([fix.source_pages, fix.evidence?.source_pages]).map(cleanPath).filter(Boolean));
  const linkTextSamples = unique(firstArray([fix.link_text_samples, fix.evidence?.link_text_samples]).map(String).filter(Boolean));

  return {
    affectedPages: affectedPages.length ? affectedPages : pageUrl ? [pageUrl] : [],
    sourcePages: sourcePages.length ? sourcePages : affectedPages,
    linkTextSamples,
    currentValue: fix.current_value || fix.current || fix.detected_value || evidenceCurrentValue(affectedPages, sourcePages),
    pageTemplateFamily: fix.page_template_family || fix.template_family || "",
    defectClass: fix.primary_defect_class || "",
  };
}

function buildEvidenceState(values) {
  return {
    ...values,
    isComplete: values.state === COMPLETE || values.state === REPRESENTATIVE_SAMPLE,
    isRepresentativeSample: values.state === REPRESENTATIVE_SAMPLE,
    isBlockedOrLimited: values.state === ACCESS_LIMITED,
    isMetadataOnly: values.state === METADATA_ONLY,
  };
}

function countBlockedPages(pages, recommendations, scanRecord) {
  const fromPages = pages.filter((page) => {
    const status = Number(page?.status_code || page?.status || 0);
    const text = `${page?.fetch_error || ""} ${page?.error || ""} ${page?.title || ""} ${page?.content_type || ""}`.toLowerCase();
    return status === 429 || hasAny(text, ["rate limit", "too many requests", "bot protection", "connection verification", "access denied", "cloudflare"]);
  }).length;

  const fromRecommendations = recommendations.filter((item) => {
    const text = `${item?.rule || ""} ${item?.category || ""} ${item?.title || ""} ${item?.current_value || ""}`.toLowerCase();
    return hasAny(text, ["429", "blocked", "rate limit", "too many requests", "bot protection", "connection verification"]);
  }).length;

  return Math.max(fromPages, fromRecommendations, firstNumber([scanRecord?.site_fingerprint?.blocked_access_pages, scanRecord?.technical_audit_summary?.blocked_access_pages]));
}

function evidenceCurrentValue(affectedPages, sourcePages) {
  const affected = unique((affectedPages || []).map(cleanPath).filter(Boolean));
  const sources = unique((sourcePages || []).map(cleanPath).filter(Boolean));
  const basis = affected.length ? affected : sources;
  if (!basis.length) return "No affected pages recorded.";
  const more = basis.length > 3 ? ` (+${basis.length - 3} more)` : "";
  return `${basis.length} affected ${basis.length === 1 ? "page" : "pages"}: ${basis.slice(0, 3).join(", ")}${more}`;
}

function sizeBandFromPages(count) {
  if (count >= 1000) return "enterprise";
  if (count >= 150) return "mid_market";
  if (count >= 30) return "smb";
  return "micro";
}

function firstArray(values) {
  for (const value of values || []) {
    if (Array.isArray(value) && value.length > 0) return value;
  }
  return [];
}

function firstNumber(values) {
  for (const value of values || []) {
    const number = Number(value);
    if (Number.isFinite(number) && number >= 0) return number;
  }
  return 0;
}

function cleanPath(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  try {
    const url = new URL(raw);
    return `${url.pathname || "/"}${url.search || ""}` || "/";
  } catch {
    return raw.startsWith("/") ? raw : `/${raw}`;
  }
}

function hasAny(text, needles) {
  const haystack = String(text || "").toLowerCase();
  return (needles || []).some((needle) => haystack.includes(String(needle || "").toLowerCase()));
}

function humanize(value) {
  return String(value || "")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^./, (char) => char.toUpperCase());
}

function unique(items) {
  return Array.from(new Set((items || []).filter(Boolean)));
}
