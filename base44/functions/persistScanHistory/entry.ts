import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";

const VERSION = "persistScanHistory_v1";
const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

const ISSUE_CATEGORIES = new Set([
  "meta_title",
  "meta_description",
  "404_error",
  "redirect",
  "canonical",
  "sitemap",
  "robots_txt",
  "js_rendering",
  "internal_link",
  "thin_content",
  "duplicate_content",
  "schema",
  "performance",
  "web_dev",
  "image_alt_text",
]);
const ISSUE_PRIORITIES = new Set(["critical", "high", "medium", "low"]);
const ISSUE_STATUSES = new Set([
  "open",
  "auto_fixed",
  "needs_approval",
  "approved",
  "rejected",
  "needs_developer",
  "in_progress",
  "completed",
]);
const ISSUE_DIFFICULTIES = new Set(["easy", "moderate", "developer"]);
const MAX_PAGES = 150;
const MAX_ISSUES = 120;
const WRITE_BATCH_SIZE = 20;

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: CORS_HEADERS });
  }
  if (req.method !== "POST") {
    return jsonResponse({ success: false, version: VERSION, error: "Method not allowed" }, 405);
  }

  let crawlJobId = "";
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me().catch(() => null);
    if (!user) {
      return jsonResponse({ success: false, version: VERSION, error: "Unauthorized" }, 401);
    }

    const rawBody = await req.json().catch(() => ({}));
    const body = unwrapRequestBody(rawBody);
    const record = asObject(body.scan_record || body.scan || body.record || body);
    const websiteUrl = normalizeWebsiteUrl(
      record.website_url || body.website_url || body.url || "",
    );
    if (!websiteUrl) {
      return jsonResponse(
        { success: false, version: VERSION, error: "Missing or invalid website_url." },
        400,
      );
    }

    const service = base44.asServiceRole.entities;
    const completedAt = asString(record.completed_at || record.created_at) || new Date().toISOString();
    const startedAt = asString(record.started_at) || completedAt;
    const scanMode = normalizeScanMode(record.scan_mode || body.scan_mode);
    const healthScore = boundedScore(
      record.health_score,
      record.seo_score,
      record.website_health_report?.health_score,
      record.website_health_report?.score,
    );
    const pages = getPages(record).slice(0, MAX_PAGES);
    const issues = getIssues(record).slice(0, MAX_ISSUES);
    const project = await upsertProject({
      service,
      user,
      record,
      websiteUrl,
      scanMode,
      healthScore,
      completedAt,
      requestedProjectId: asString(body.project_id || record.project_id),
    });

    const job = await service.CrawlJob.create({
      project_id: project.id,
      status: "generating_recommendations",
      crawl_type: scanMode === "quick" ? "full" : "deep",
      pages_found: nonNegativeNumber(record.pages_found, pages.length),
      pages_crawled: nonNegativeNumber(record.pages_crawled, pages.length),
      js_pages_rendered: nonNegativeNumber(
        record.js_pages_rendered,
        record.technical_audit_summary?.js_pages_rendered,
        0,
      ),
      started_at: startedAt,
      completed_at: "",
      error_message: "",
      seo_score: healthScore,
      issues_found: issues.length,
      owner_user_id: user.id,
    });
    crawlJobId = job.id;

    try {
      const pageRows = pages
        .map((page) => toCrawledPage({ page, projectId: project.id, crawlJobId, ownerUserId: user.id }))
        .filter(Boolean);
      const issueRows = issues
        .map((issue) =>
          toSeoIssue({
            issue,
            projectId: project.id,
            crawlJobId,
            ownerUserId: user.id,
            websiteUrl,
          }),
        )
        .filter(Boolean);

      await writeInBatches(service.CrawledPage, pageRows);
      await writeInBatches(service.SeoIssue, issueRows);

      const siteSummary = buildSiteSummary(record, {
        websiteUrl,
        scanMode,
        healthScore,
        pagesFound: nonNegativeNumber(record.pages_found, pages.length),
        pagesCrawled: nonNegativeNumber(record.pages_crawled, pages.length),
        issueCount: issueRows.length,
      });
      const summary = firstString(
        record.customer_summary,
        record.simple_summary,
        record.plain_english_summary,
        record.website_health_report?.overall_explanation,
        record.scan_summary?.plain_english_summary,
      );
      const nextSteps = firstString(
        record.next_best_step,
        record.website_health_report?.next_best_step,
      );
      const bucketCounts = countIssueBuckets(issueRows);

      await service.ScanDiagnostic.create({
        owner_user_id: user.id,
        project_id: project.id,
        crawl_job_id: crawlJobId,
        scan_source: firstString(record.debug?.scanner_function, "runAdvancedScan"),
        scan_mode: scanMode,
        raw_findings_count: nonNegativeNumber(
          record.raw_findings_count,
          record.technical_audit_summary?.raw_findings_count,
          issues.length,
        ),
        grouped_findings_count: issueRows.length,
        broken_links_count: issueRows.filter((issue) => issue.category === "404_error").length,
        pages_crawled: nonNegativeNumber(record.pages_crawled, pages.length),
        pages_found: nonNegativeNumber(record.pages_found, pages.length),
        health_score: healthScore,
        discovered_competitor_count: nonNegativeNumber(record.discovered_competitor_count, 0),
        competitor_result_count: nonNegativeNumber(record.competitor_result_count, 0),
        crawl_warnings: stringArray(record.crawl_warnings).slice(0, 20),
        site_summary: siteSummary,
        created_at: completedAt,
      });

      await service.Report.create({
        project_id: project.id,
        crawl_job_id: crawlJobId,
        summary,
        fixed_count: bucketCounts.auto_fixed,
        approval_count: bucketCounts.needs_approval,
        developer_count: bucketCounts.needs_developer,
        competitor_summary: firstString(record.competitor_summary),
        next_steps: nextSteps,
        seo_score: healthScore,
        owner_user_id: user.id,
      });

      await service.CrawlJob.update(crawlJobId, {
        status: "complete",
        pages_found: nonNegativeNumber(record.pages_found, pages.length),
        pages_crawled: nonNegativeNumber(record.pages_crawled, pages.length),
        js_pages_rendered: nonNegativeNumber(
          record.js_pages_rendered,
          record.technical_audit_summary?.js_pages_rendered,
          0,
        ),
        completed_at: completedAt,
        error_message: "",
        seo_score: healthScore,
        issues_found: issueRows.length,
      });

      await service.BusinessProject.update(project.id, {
        status: "active",
        seo_score: healthScore,
        last_crawl_at: completedAt,
      });

      return jsonResponse({
        success: true,
        version: VERSION,
        project_id: project.id,
        crawl_job_id: crawlJobId,
        pages_persisted: pageRows.length,
        issues_persisted: issueRows.length,
        health_score: healthScore,
        completed_at: completedAt,
      });
    } catch (writeError) {
      await service.CrawlJob.update(crawlJobId, {
        status: "failed",
        completed_at: new Date().toISOString(),
        error_message: clampString(writeError?.message || String(writeError), 500),
      }).catch(() => null);
      throw writeError;
    }
  } catch (error) {
    console.error("persistScanHistory failed", error);
    return jsonResponse(
      {
        success: false,
        version: VERSION,
        crawl_job_id: crawlJobId,
        error: "The scan completed, but its database history could not be saved.",
        detail: clampString(error?.message || String(error || "unknown"), 500),
      },
      500,
    );
  }
});

async function upsertProject({
  service,
  user,
  record,
  websiteUrl,
  scanMode,
  healthScore,
  completedAt,
  requestedProjectId,
}) {
  let project = null;
  if (requestedProjectId) {
    project = await service.BusinessProject.get(requestedProjectId).catch(() => null);
    if (project?.owner_user_id && project.owner_user_id !== user.id) project = null;
  }

  if (!project) {
    const matches = await service.BusinessProject.filter(
      { website_url: websiteUrl, owner_user_id: user.id },
      "-last_crawl_at",
      10,
    ).catch(() => []);
    project = Array.isArray(matches) ? matches[0] : null;
  }

  const payload = {
    business_name: firstString(record.business_name, hostnameLabel(websiteUrl), "Website"),
    website_url: websiteUrl,
    business_type: firstString(record.business_type),
    city: firstString(record.city),
    service_area: firstString(record.service_area),
    main_services: firstString(record.main_services),
    important_keywords: stringArray(record.important_keywords).slice(0, 50),
    scan_mode: scanMode,
    cms_platform: normalizeCms(record.cms_platform || record.cms_name),
    status: "active",
    seo_score: healthScore,
    last_crawl_at: completedAt,
    owner_user_id: user.id,
  };

  if (project?.id) {
    return await service.BusinessProject.update(project.id, payload);
  }
  return await service.BusinessProject.create(payload);
}

function toCrawledPage({ page, projectId, crawlJobId, ownerUserId }) {
  const url = normalizeWebsiteUrl(page?.url || page?.final_url || "");
  if (!url) return null;
  return {
    project_id: projectId,
    crawl_job_id: crawlJobId,
    url,
    status_code: nonNegativeNumber(page.status_code, 0),
    title: clampString(page.title, 1000),
    meta_description: clampString(page.meta_description, 2000),
    h1: clampString(page.h1, 1000),
    canonical_url: clampString(page.canonical_url || page.canonical, 2000),
    word_count: nonNegativeNumber(page.word_count, 0),
    indexable: typeof page.indexable === "boolean" ? page.indexable : true,
    in_sitemap: Boolean(page.in_sitemap),
    rendered_title: clampString(page.rendered_title, 1000),
    rendered_meta_description: clampString(page.rendered_meta_description, 2000),
    rendered_canonical: clampString(page.rendered_canonical, 2000),
    js_difference_detected: Boolean(page.js_difference_detected),
    owner_user_id: ownerUserId,
  };
}

function toSeoIssue({ issue, projectId, crawlJobId, ownerUserId, websiteUrl }) {
  if (!issue || typeof issue !== "object") return null;
  const affectedPages = uniqueStrings([
    ...stringArray(issue.affected_pages),
    ...stringArray(issue.pages),
    ...stringArray(issue.page_urls),
    firstString(issue.page_url, issue.url),
  ]).slice(0, 150);
  const pageUrl = firstString(issue.page_url, issue.url, affectedPages[0], websiteUrl);
  const category = normalizeCategory(issue.category, issue.rule || issue.issue_type);
  const requiresDeveloper =
    typeof issue.requires_developer === "boolean"
      ? issue.requires_developer
      : firstString(issue.who_can_do_this).toLowerCase() === "your_web_person";
  const status = ISSUE_STATUSES.has(String(issue.status || ""))
    ? String(issue.status)
    : requiresDeveloper
      ? "needs_developer"
      : issue.can_auto_fix
        ? "auto_fixed"
        : "needs_approval";
  const difficulty = ISSUE_DIFFICULTIES.has(String(issue.difficulty || ""))
    ? String(issue.difficulty)
    : requiresDeveloper
      ? "developer"
      : "easy";

  return {
    project_id: projectId,
    crawl_job_id: crawlJobId,
    page_url: pageUrl,
    affected_pages: affectedPages.length ? affectedPages : [pageUrl],
    details: sanitizeJsonObject({
      ...issue,
      persistence_version: VERSION,
      persisted_source_pages: stringArray(issue.source_pages).slice(0, 30),
    }),
    category,
    customer_category: clampString(issue.customer_category, 300),
    priority: ISSUE_PRIORITIES.has(String(issue.priority || ""))
      ? String(issue.priority)
      : "medium",
    status,
    difficulty,
    issue_title: clampString(
      firstString(issue.issue_title, issue.title, issue.name, "Review this recommendation"),
      1000,
    ),
    plain_english_explanation: clampString(
      firstString(
        issue.plain_english_explanation,
        issue.plain_english_summary,
        issue.explanation,
        issue.description,
        "This recommendation was found during the website scan.",
      ),
      5000,
    ),
    why_it_matters: clampString(
      firstString(
        issue.why_it_matters,
        issue.reason,
        issue.impact,
        "Improving this can help visitors and search engines understand the website more clearly.",
      ),
      5000,
    ),
    current_value: clampString(issue.current_value || issue.current, 5000),
    recommended_value: clampString(
      firstString(
        issue.recommended_value,
        issue.recommendation,
        issue.ai_recommendation,
        issue.simple_next_step,
        "Review this recommendation.",
      ),
      5000,
    ),
    ai_recommendation: clampString(
      firstString(
        issue.ai_recommendation,
        issue.recommendation,
        issue.recommended_value,
        issue.simple_next_step,
        "Review this recommendation.",
      ),
      5000,
    ),
    confidence_score: nonNegativeNumber(issue.confidence_score, 90),
    can_auto_fix: Boolean(issue.can_auto_fix),
    requires_approval:
      typeof issue.requires_approval === "boolean"
        ? issue.requires_approval
        : !requiresDeveloper,
    requires_developer: requiresDeveloper,
    owner_user_id: ownerUserId,
  };
}

function buildSiteSummary(record, counts) {
  const healthReport = asObject(record.website_health_report);
  return sanitizeJsonObject({
    persistence_version: VERSION,
    scan_record_id: firstString(record.id),
    persisted_at: new Date().toISOString(),
    website_url: counts.websiteUrl,
    scan_mode: counts.scanMode,
    health_score: counts.healthScore,
    pages_found: counts.pagesFound,
    pages_crawled: counts.pagesCrawled,
    issue_count: counts.issueCount,
    scan_status: firstString(record.scan_status, healthReport.scan_status, "complete"),
    review_confidence_state: firstString(
      record.review_confidence_state,
      healthReport.review_confidence_state,
    ),
    score_is_provisional: Boolean(
      record.score_is_provisional ?? healthReport.score_is_provisional,
    ),
    access_evidence_state: firstString(
      record.access_evidence_state,
      healthReport.access_evidence_state,
    ),
    no_high_confidence_findings: Boolean(record.no_high_confidence_findings),
    scanner_version: firstString(
      record.scanner_version,
      record.debug?.scanner_version,
      record.technical_audit_summary?.scanner_version,
    ),
    review_version: firstString(
      record.review_version,
      record.ai_review_version,
      record.debug?.review_version,
    ),
    advanced_scan_backend: firstString(record.advanced_scan_backend),
    ai_review_backend: firstString(record.ai_review_backend, record.debug?.ai_review_backend),
    python_review_fallback_used: Boolean(
      record.python_review_fallback_used ?? record.debug?.python_review_fallback_used,
    ),
    ai_summary: firstString(record.customer_summary, record.simple_summary),
    next_best_step: firstString(record.next_best_step, healthReport.next_best_step),
    top_actions: arrayValue(record.top_recommended_actions).slice(0, 10),
    positive_findings: stringArray(record.positive_findings).slice(0, 30),
    website_health_report: healthReport,
    technical_audit_summary: asObject(record.technical_audit_summary),
    url_evidence_summary: asObject(record.url_evidence_summary),
    sampling_version: firstString(record.sampling_version),
    sampling_evidence: asObject(record.sampling_evidence),
    crawl_policy_source: firstString(record.crawl_policy_source),
    crawl_policy: asObject(record.crawl_policy),
    limitation: firstString(record.limitation),
    cms_platform: firstString(record.cms_platform),
    review: {
      scan_status: firstString(record.scan_status, healthReport.scan_status, "complete"),
      review_confidence_state: firstString(
        record.review_confidence_state,
        healthReport.review_confidence_state,
      ),
      score_is_provisional: Boolean(
        record.score_is_provisional ?? healthReport.score_is_provisional,
      ),
      access_evidence_state: firstString(
        record.access_evidence_state,
        healthReport.access_evidence_state,
      ),
      no_high_confidence_findings: Boolean(record.no_high_confidence_findings),
      ai_review_backend: firstString(record.ai_review_backend, record.debug?.ai_review_backend),
      python_review_fallback_used: Boolean(
        record.python_review_fallback_used ?? record.debug?.python_review_fallback_used,
      ),
      website_health_report: healthReport,
      top_recommended_actions: arrayValue(record.top_recommended_actions).slice(0, 10),
      positive_findings: stringArray(record.positive_findings).slice(0, 30),
    },
  });
}

async function writeInBatches(entity, rows) {
  for (let index = 0; index < rows.length; index += WRITE_BATCH_SIZE) {
    const batch = rows.slice(index, index + WRITE_BATCH_SIZE);
    await Promise.all(batch.map((row) => entity.create(row)));
  }
}

function countIssueBuckets(issues) {
  return issues.reduce(
    (counts, issue) => {
      if (issue.status === "auto_fixed") counts.auto_fixed += 1;
      else if (issue.status === "needs_developer") counts.needs_developer += 1;
      else counts.needs_approval += 1;
      return counts;
    },
    { auto_fixed: 0, needs_approval: 0, needs_developer: 0 },
  );
}

function normalizeCategory(categoryValue, ruleValue) {
  const category = String(categoryValue || "").toLowerCase();
  if (ISSUE_CATEGORIES.has(category)) return category;
  const text = `${category} ${String(ruleValue || "").toLowerCase()}`;
  if (/404|broken_page|failed_page|http_4\d\d|http_5\d\d/.test(text)) return "404_error";
  if (/redirect/.test(text)) return "redirect";
  if (/canonical/.test(text)) return "canonical";
  if (/sitemap/.test(text)) return "sitemap";
  if (/robots|noindex|indexab/.test(text)) return "robots_txt";
  if (/javascript|client_render|js_render/.test(text)) return "js_rendering";
  if (/internal_link|orphan/.test(text)) return "internal_link";
  if (/duplicate/.test(text)) return "duplicate_content";
  if (/thin|missing_h1|content/.test(text)) return "thin_content";
  if (/schema|structured/.test(text)) return "schema";
  if (/performance|speed|core_web/.test(text)) return "performance";
  if (/image_alt|alt_text/.test(text)) return "image_alt_text";
  if (/description/.test(text)) return "meta_description";
  if (/title/.test(text)) return "meta_title";
  return "web_dev";
}

function normalizeScanMode(value) {
  return String(value || "").toLowerCase() === "quick" ? "quick" : "deep";
}

function normalizeCms(value) {
  const text = String(value || "").trim().toLowerCase();
  const map = {
    wordpress: "WordPress",
    shopify: "Shopify",
    wix: "Wix",
    webflow: "Webflow",
    squarespace: "Squarespace",
    custom: "Custom",
    "custom / not sure": "Custom",
    unknown: "Unknown",
  };
  return map[text] || "Unknown";
}

function getPages(record) {
  return firstArray([
    record.crawled_pages,
    record.pages,
    record.scanned_pages,
    record.raw?.scanner?.pages,
    record.raw?.scanner?.crawled_pages,
    record.raw?.scanner?.pages_preview,
  ]);
}

function getIssues(record) {
  return firstArray([
    record.recommendations,
    record.fixes,
    record.findings,
    record.cleaned_fixes,
    record.raw_fixes,
    record.issues,
  ]);
}

function normalizeWebsiteUrl(value) {
  try {
    const text = String(value || "").trim();
    if (!text) return "";
    const candidate = /^https?:\/\//i.test(text) ? text : `https://${text}`;
    const url = new URL(candidate);
    if (!/^https?:$/.test(url.protocol)) return "";
    url.hash = "";
    return url.toString();
  } catch {
    return "";
  }
}

function hostnameLabel(value) {
  try {
    return new URL(value).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

function boundedScore(...values) {
  for (const value of values) {
    const number = Number(value);
    if (Number.isFinite(number) && number >= 0 && number <= 100) return Math.round(number);
  }
  return 0;
}

function nonNegativeNumber(...values) {
  for (const value of values) {
    const number = Number(value);
    if (Number.isFinite(number) && number >= 0) return number;
  }
  return 0;
}

function firstString(...values) {
  for (const value of values) {
    const text = asString(value);
    if (text) return text;
  }
  return "";
}

function asString(value) {
  return typeof value === "string" ? value.trim() : "";
}

function asObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function arrayValue(value) {
  return Array.isArray(value) ? value : [];
}

function firstArray(values) {
  for (const value of values || []) {
    if (Array.isArray(value) && value.length > 0) return value;
  }
  return [];
}

function stringArray(value) {
  return arrayValue(value)
    .map((item) => String(item || "").trim())
    .filter(Boolean);
}

function uniqueStrings(values) {
  return Array.from(
    new Set((values || []).map((value) => String(value || "").trim()).filter(Boolean)),
  );
}

function clampString(value, max = 1000) {
  const text = String(value || "");
  return text.length <= max ? text : text.slice(0, max);
}

function sanitizeJsonObject(value) {
  try {
    return JSON.parse(JSON.stringify(value || {}));
  } catch {
    return {};
  }
}

function unwrapRequestBody(raw) {
  if (!raw || typeof raw !== "object") return {};
  if (raw.data && typeof raw.data === "object") return raw.data;
  if (raw.body && typeof raw.body === "object") return raw.body;
  if (raw.payload && typeof raw.payload === "object") return raw.payload;
  return raw;
}

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json", ...CORS_HEADERS },
  });
}
