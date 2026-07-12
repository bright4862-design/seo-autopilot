const COMPLETE_STATUS = "complete";
const DEFAULT_JOB_LIMIT = 25;
const DEFAULT_RECORD_LIMIT = 500;

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function asObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function asString(value) {
  return typeof value === "string" ? value.trim() : "";
}

function numericScore(...values) {
  for (const value of values) {
    const number = Number(value);
    if (Number.isFinite(number) && number >= 0 && number <= 100) {
      return Math.round(number);
    }
  }
  return 0;
}

function dateValue(record = {}) {
  const value =
    record.completed_at ||
    record.updated_date ||
    record.created_date ||
    record.started_at ||
    "";
  const timestamp = new Date(value || 0).getTime();
  return Number.isFinite(timestamp) ? timestamp : 0;
}

function sortNewest(records = []) {
  return [...records].sort((left, right) => dateValue(right) - dateValue(left));
}

async function safeEntityQuery(callback, fallback = []) {
  try {
    const result = await callback();
    return Array.isArray(result) ? result : fallback;
  } catch (error) {
    console.warn("Could not load persisted scan history entity.", error);
    return fallback;
  }
}

export async function resolvePersistedScanProject({ base44, activeProjectId = "" } = {}) {
  if (!base44?.entities?.BusinessProject) return null;

  if (activeProjectId) {
    try {
      const active = await base44.entities.BusinessProject.get(activeProjectId);
      if (active?.id) return active;
    } catch (error) {
      console.warn("Could not load active persisted project.", error);
    }
  }

  const projects = await safeEntityQuery(
    () => base44.entities.BusinessProject.list("-last_crawl_at", 25),
    [],
  );
  return projects[0] || null;
}

export async function loadLatestPersistedScanRecord({
  base44,
  activeProjectId = "",
} = {}) {
  const project = await resolvePersistedScanProject({ base44, activeProjectId });
  if (!project?.id || !base44?.entities?.CrawlJob) return null;

  let jobs = await safeEntityQuery(
    () =>
      base44.entities.CrawlJob.filter(
        { project_id: project.id, status: COMPLETE_STATUS },
        "-completed_at",
        DEFAULT_JOB_LIMIT,
      ),
    [],
  );

  if (jobs.length === 0) {
    const projectJobs = await safeEntityQuery(
      () =>
        base44.entities.CrawlJob.filter(
          { project_id: project.id },
          "-created_date",
          DEFAULT_JOB_LIMIT,
        ),
      [],
    );
    jobs = projectJobs.filter((job) => job?.status === COMPLETE_STATUS);
  }

  const job = sortNewest(jobs)[0] || null;
  if (!job?.id) return null;

  return loadPersistedScanRecord({ base44, project, job });
}

export async function loadPersistedScanRecord({ base44, project, job } = {}) {
  if (!base44?.entities || !project?.id || !job?.id) return null;

  const filters = { project_id: project.id, crawl_job_id: job.id };
  const [issues, pages, diagnostics, reports] = await Promise.all([
    safeEntityQuery(
      () => base44.entities.SeoIssue.filter(filters, "-created_date", DEFAULT_RECORD_LIMIT),
      [],
    ),
    safeEntityQuery(
      () => base44.entities.CrawledPage.filter(filters, "url", DEFAULT_RECORD_LIMIT),
      [],
    ),
    safeEntityQuery(
      () => base44.entities.ScanDiagnostic.filter(filters, "-created_date", 10),
      [],
    ),
    base44.entities.Report
      ? safeEntityQuery(
          () => base44.entities.Report.filter(filters, "-created_date", 10),
          [],
        )
      : Promise.resolve([]),
  ]);

  return buildPersistedScanRecord({
    project,
    job,
    issues,
    pages,
    diagnostic: sortNewest(diagnostics)[0] || null,
    report: sortNewest(reports)[0] || null,
  });
}

export function buildPersistedScanRecord({
  project = {},
  job = {},
  issues = [],
  pages = [],
  diagnostic = null,
  report = null,
} = {}) {
  if (!project?.id || !job?.id) return null;

  const siteSummary = asObject(diagnostic?.site_summary);
  const review = asObject(siteSummary.review);
  const websiteHealthReport = asObject(
    siteSummary.website_health_report || review.website_health_report,
  );
  const recommendations = asArray(issues).map(hydratePersistedIssue);
  const crawledPages = asArray(pages);
  const score = numericScore(
    job.seo_score,
    report?.seo_score,
    diagnostic?.health_score,
    websiteHealthReport.health_score,
    websiteHealthReport.score,
  );
  const createdAt =
    job.completed_at || job.updated_date || job.created_date || new Date().toISOString();
  const topActions = asArray(
    siteSummary.top_actions ||
      siteSummary.top_recommended_actions ||
      review.top_recommended_actions,
  );
  const positiveFindings = asArray(
    siteSummary.positive_findings || review.positive_findings,
  );
  const summary =
    asString(report?.summary) ||
    asString(siteSummary.ai_summary) ||
    asString(siteSummary.plain_english_summary) ||
    asString(websiteHealthReport.overall_explanation);
  const nextBestStep =
    asString(report?.next_steps) ||
    asString(siteSummary.next_best_step) ||
    asString(websiteHealthReport.next_best_step);

  return {
    id: job.id,
    crawl_job_id: job.id,
    project_id: project.id,
    storage_source: "base44",
    created_at: createdAt,
    completed_at: job.completed_at || "",
    website_url: project.website_url || "",
    business_name: project.business_name || "",
    cms_platform: project.cms_platform || "Unknown",
    scan_mode: siteSummary.scan_mode || diagnostic?.scan_mode || project.scan_mode || "quick",
    scan_status:
      review.scan_status ||
      siteSummary.scan_status ||
      websiteHealthReport.scan_status ||
      COMPLETE_STATUS,
    review_confidence_state:
      review.review_confidence_state ||
      siteSummary.review_confidence_state ||
      websiteHealthReport.review_confidence_state ||
      "",
    score_is_provisional: Boolean(
      review.score_is_provisional ??
        siteSummary.score_is_provisional ??
        websiteHealthReport.score_is_provisional,
    ),
    access_evidence_state:
      review.access_evidence_state ||
      siteSummary.access_evidence_state ||
      websiteHealthReport.access_evidence_state ||
      "",
    no_high_confidence_findings: Boolean(
      review.no_high_confidence_findings ?? siteSummary.no_high_confidence_findings,
    ),
    scanner_version: siteSummary.scanner_version || diagnostic?.scanner_version || "",
    review_version: siteSummary.review_version || "",
    advanced_scan_backend: siteSummary.advanced_scan_backend || "",
    ai_review_backend: review.ai_review_backend || siteSummary.ai_review_backend || "",
    python_review_fallback_used: Boolean(
      review.python_review_fallback_used ?? siteSummary.python_review_fallback_used,
    ),
    pages_found: Number(job.pages_found || diagnostic?.pages_found || crawledPages.length || 0),
    pages_crawled: Number(job.pages_crawled || diagnostic?.pages_crawled || crawledPages.length || 0),
    issues_found: Number(job.issues_found || recommendations.length || 0),
    health_score: score,
    seo_score: score,
    recommendations,
    fixes: recommendations,
    findings: recommendations,
    crawled_pages: crawledPages,
    pages: crawledPages,
    top_recommended_actions: topActions,
    recommended_actions: topActions,
    positive_findings: positiveFindings,
    customer_summary: summary,
    simple_summary: summary,
    next_best_step: nextBestStep,
    website_health_report: {
      ...websiteHealthReport,
      health_score: numericScore(
        websiteHealthReport.health_score,
        websiteHealthReport.score,
        score,
      ),
      score: numericScore(
        websiteHealthReport.score,
        websiteHealthReport.health_score,
        score,
      ),
      overall_explanation:
        asString(websiteHealthReport.overall_explanation) || summary,
      next_best_step:
        asString(websiteHealthReport.next_best_step) || nextBestStep,
    },
    scan_summary: {
      health_score: score,
      score,
      pages_scanned: Number(job.pages_crawled || crawledPages.length || 0),
      plain_english_summary: summary,
    },
    crawl_warnings: asArray(diagnostic?.crawl_warnings),
    site_summary: siteSummary,
    raw: {
      project,
      job,
      diagnostic,
      report,
    },
  };
}

export function hydratePersistedIssue(issue = {}) {
  const details = asObject(issue.details);
  return {
    ...details,
    ...issue,
    id: issue.id || details.id || details.fix_id || "",
    fix_id: issue.fix_id || details.fix_id || issue.id || "",
    rule: issue.rule || details.rule || details.original_category || "",
    affected_pages: asArray(issue.affected_pages).length
      ? issue.affected_pages
      : asArray(details.affected_pages),
    source_pages: asArray(issue.source_pages).length
      ? issue.source_pages
      : asArray(details.source_pages),
    details,
  };
}
