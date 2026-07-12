import React, { useEffect, useRef, useState } from "react";
import { base44 } from "@/api/base44Client";
import { trackEvent } from "@/lib/analytics";
import { selectFinalReviewFixes } from "@/lib/reviewContract";
import ScanWebsiteForm from "@/components/scan/ScanWebsiteForm";
import { Button } from "@/components/ui/button";
import { AlertTriangle, CheckCircle2, Circle, Loader2 } from "lucide-react";

/**
 * IMPORTANT:
 * Change this only if your existing backend scan function has a different name.
 *
 * Common names:
 * - runRealScan
 * - startCrawl
 * - scanWebsite
 * - crawlWebsite
 */
const SCAN_FUNCTION_NAME = "runAdvancedScan";

/**
 * If aiReviewScan does not exist, leave this as-is.
 * The code will try it, and if it fails, it will save crawler recommendations directly.
 */
const AI_REVIEW_FUNCTION_NAME = "aiReviewScan";

const QUICK_SCAN_STEPS = [
  { key: "queued", label: "Finding pages" },
  { key: "crawling_html", label: "Reading website content" },
  { key: "checking_metadata", label: "Checking search appearance" },
  { key: "checking_canonicals", label: "Reviewing website setup" },
  { key: "generating_recommendations", label: "Preparing recommendations" },
  { key: "complete", label: "Complete" },
];

const DEEP_SCAN_STEPS = [
  { key: "queued", label: "Finding pages" },
  { key: "reading_sitemap", label: "Reading sitemap" },
  { key: "crawling_html", label: "Reading website content" },
  { key: "checking_links", label: "Checking internal links" },
  { key: "finding_competitors", label: "Finding competitor pages" },
  { key: "benchmarking_competitors", label: "Comparing competitors" },
  { key: "generating_recommendations", label: "Preparing recommendations" },
  { key: "complete", label: "Complete" },
];

const CATEGORY_MAP = {
  broken_page: "404_error",
  page_heading: "thin_content",
  placeholder_text: "web_dev",
  faq_gap: "thin_content",
  cta_gap: "thin_content",
  trust_signal_gap: "schema",
  duplicate_search_titles: "duplicate_content",
  image_alt_text: "web_dev",
  content: "thin_content",
};

const VALID_CATEGORIES = new Set([
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
]);

const VALID_STATUSES = new Set([
  "open",
  "auto_fixed",
  "needs_approval",
  "approved",
  "rejected",
  "needs_developer",
  "in_progress",
  "completed",
]);

const VALID_PRIORITIES = new Set(["critical", "high", "medium", "low"]);
const VALID_DIFFICULTIES = new Set(["easy", "moderate", "developer"]);

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const withTimeout = (promise, ms, label = "Operation") => {
  let timeoutId;

  const timeoutPromise = new Promise((_, reject) => {
    timeoutId = setTimeout(() => {
      reject(
        new Error(`${label} timed out after ${Math.round(ms / 1000)} seconds.`)
      );
    }, ms);
  });

  return Promise.race([promise, timeoutPromise]).finally(() => {
    clearTimeout(timeoutId);
  });
};

function getScanSteps(scanMode) {
  return scanMode === "deep" ? DEEP_SCAN_STEPS : QUICK_SCAN_STEPS;
}

function getScanMode(projectOrForm) {
  return projectOrForm?.scan_mode === "deep" ? "deep" : "quick";
}

function getSafeStatus(item = {}) {
  if (VALID_STATUSES.has(item.status)) return item.status;
  if (item.requires_developer) return "needs_developer";
  if (item.requires_approval) return "needs_approval";
  if (item.can_auto_fix) return "auto_fixed";
  return "needs_approval";
}

function getSafeCategory(category) {
  const mapped = CATEGORY_MAP[category] || category || "web_dev";
  return VALID_CATEGORIES.has(mapped) ? mapped : "web_dev";
}

function normalizePageUrl(item = {}) {
  if (item.page_url) return cleanPath(item.page_url);
  if (item.url) return cleanPath(item.url);
  if (item.page) return cleanPath(item.page);

  if (Array.isArray(item.affected_pages) && item.affected_pages[0]) {
    return cleanPath(item.affected_pages[0]);
  }

  return "/";
}

function cleanPath(input) {
  try {
    const parsed = new URL(input, window.location.origin);
    const path = parsed.pathname || "/";
    return path !== "/" && path.endsWith("/") ? path.slice(0, -1) : path;
  } catch {
    const value = String(input || "/").split("?")[0].split("#")[0];
    if (!value || value === "/") return "/";
    return value.endsWith("/") && value !== "/" ? value.slice(0, -1) : value;
  }
}

function getAffectedPages(item = {}) {
  if (Array.isArray(item.affected_pages)) {
    return item.affected_pages.filter(Boolean).map(cleanPath);
  }

  if (Array.isArray(item.pages)) {
    return item.pages.filter(Boolean).map(cleanPath);
  }

  if (item.page_url) return [cleanPath(item.page_url)];
  if (item.url) return [cleanPath(item.url)];

  return [];
}

function mapFindingToSeoIssue(item = {}) {
  const status = getSafeStatus(item);
  const category = getSafeCategory(item.category);
  const affectedPages = getAffectedPages(item);

  const recommendation =
    item.ai_recommendation ||
    item.recommended_value ||
    item.recommendation ||
    item.suggested_fix ||
    item.fix ||
    "Review this recommendation and decide whether to update the page.";

  return {
    page_url: normalizePageUrl(item),
    affected_pages: affectedPages,
    details: {
      ...(item.details || {}),
      original_category: item.category || "",
      scan_source: SCAN_FUNCTION_NAME,
      grouped: item.type === "site_level" || affectedPages.length > 1,
    },
    category,
    customer_category:
      item.customer_category || friendlyCategory(category) || "Website improvement",
    priority: VALID_PRIORITIES.has(item.priority) ? item.priority : "medium",
    status,
    difficulty: VALID_DIFFICULTIES.has(item.difficulty)
      ? item.difficulty
      : status === "needs_developer"
        ? "developer"
        : "easy",
    issue_title:
      item.issue_title ||
      item.title ||
      item.name ||
      getDefaultIssueTitle(category),
    plain_english_explanation:
      item.plain_english_explanation ||
      item.explanation ||
      item.description ||
      item.evidence ||
      "This recommendation was found during the website scan.",
    why_it_matters:
      item.why_it_matters ||
      item.why ||
      "Improving this can help visitors and search engines understand the website more clearly.",
    current_value: item.current_value || item.current || "",
    recommended_value: item.recommended_value || recommendation,
    ai_recommendation: recommendation,
    confidence_score:
      typeof item.confidence_score === "number" ? item.confidence_score : 90,
    can_auto_fix: item.can_auto_fix === true || status === "auto_fixed",
    requires_approval:
      item.requires_approval === true || status === "needs_approval",
    requires_developer:
      item.requires_developer === true || status === "needs_developer",
  };
}

function friendlyCategory(category) {
  const map = {
    meta_title: "Search appearance",
    meta_description: "Search appearance",
    canonical: "Website setup",
    schema: "Trust signals",
    thin_content: "Page content",
    duplicate_content: "Search appearance",
    "404_error": "Broken page",
    redirect: "Page redirect",
    internal_link: "Internal links",
    performance: "Website performance",
    web_dev: "Website setup",
  };

  return map[category] || "Website improvement";
}

function getDefaultIssueTitle(category) {
  const map = {
    meta_title: "Improve search titles",
    meta_description: "Add helpful search descriptions",
    canonical: "Review preferred-page settings",
    thin_content: "Improve important page content",
    duplicate_content: "Review duplicate page content",
    schema: "Add more trust signals",
    "404_error": "Fix pages that may not be loading",
    redirect: "Review page redirects",
    internal_link: "Review internal links",
    performance: "Review website performance",
    web_dev: "Review website setup",
  };

  return map[category] || "Review this website recommendation";
}

function mapCrawledPageForStorage(page = {}) {
  return {
    url: page.url || page.final_url || page.original_url || "",
    status_code: page.status_code || page.status || 0,
    title: page.title || "",
    meta_description: page.meta_description || page.metaDesc || "",
    h1: page.h1 || "",
    canonical_url: page.canonical_url || page.canonical || "",
    word_count: page.word_count || page.wordCount || 0,
    indexable:
      typeof page.indexable === "boolean"
        ? page.indexable
        : !/noindex/i.test(page.robots_meta || ""),
    in_sitemap: Boolean(page.in_sitemap),
    rendered_title: "",
    rendered_meta_description: "",
    rendered_canonical: "",
    js_difference_detected: false,
  };
}

function normalizeSeoIssueForSave(fix, project, job, user) {
  const status = getSafeStatus(fix);
  const category = getSafeCategory(fix.category);

  return {
    project_id: project.id,
    crawl_job_id: job.id,
    owner_user_id: user.id,
    page_url: fix.page_url || "/",
    category,
    customer_category: fix.customer_category || "Website improvement",
    priority: VALID_PRIORITIES.has(fix.priority) ? fix.priority : "medium",
    status,
    difficulty: VALID_DIFFICULTIES.has(fix.difficulty)
      ? fix.difficulty
      : status === "needs_developer"
        ? "developer"
        : "easy",
    issue_title: fix.issue_title || "Review this website recommendation",
    plain_english_explanation:
      fix.plain_english_explanation ||
      "This recommendation was found during the website scan.",
    why_it_matters:
      fix.why_it_matters ||
      "Improving this can help visitors and search engines understand the website more clearly.",
    current_value: fix.current_value || "",
    recommended_value:
      fix.recommended_value ||
      fix.ai_recommendation ||
      "Review this recommendation.",
    ai_recommendation:
      fix.ai_recommendation ||
      fix.recommended_value ||
      "Review this recommendation.",
    confidence_score:
      typeof fix.confidence_score === "number" ? fix.confidence_score : 90,
    can_auto_fix: fix.can_auto_fix === true || status === "auto_fixed",
    requires_approval:
      fix.requires_approval === true || status === "needs_approval",
    requires_developer:
      fix.requires_developer === true || status === "needs_developer",

    /**
     * These are helpful if your SeoIssue entity supports them.
     * If Base44 rejects them, saveSeoIssuesSafely retries without them.
     */
    affected_pages: Array.isArray(fix.affected_pages) ? fix.affected_pages : [],
    details: fix.details && typeof fix.details === "object" ? fix.details : {},
  };
}

function stripExtendedSeoFields(issue) {
  const { affected_pages, details, ...safe } = issue;
  return safe;
}

async function saveSeoIssuesSafely(issues) {
  if (!issues.length) return;

  try {
    await base44.entities.SeoIssue.bulkCreate(issues);
  } catch (error) {
    console.warn(
      "SeoIssue save failed with affected_pages/details. Retrying without them.",
      error
    );

    await base44.entities.SeoIssue.bulkCreate(
      issues.map(stripExtendedSeoFields)
    );
  }
}

function buildDeveloperRecommendation(fix, project, user) {
  let category = "technical_seo";

  if (fix.category === "thin_content") category = "content_pages";
  if (fix.category === "performance") category = "speed_mobile";
  if (fix.category === "web_dev") category = "website_structure";
  if (fix.category === "schema") category = "cms_seo_setup";
  if (fix.category === "duplicate_content" || fix.category === "canonical") {
    category = "technical_seo";
  }

  const estimated_complexity =
    fix.difficulty === "developer" ? "moderate" : "simple";

  return {
    project_id: project.id,
    owner_user_id: user.id,
    title: fix.issue_title,
    description: fix.plain_english_explanation,
    category,
    priority: fix.priority,
    business_impact: fix.why_it_matters,
    estimated_complexity,
    recommended_package:
      estimated_complexity === "moderate" ? "500_cleanup" : "diy",
    status: "open",
  };
}

function getCompetitorUrlsFromForm(form) {
  return (form?.competitor_urls || [])
    .map((url) => String(url || "").trim())
    .filter(Boolean);
}

function normalizeScore(value, fallback = 80) {
  const number = Number(value);

  if (!Number.isFinite(number) || number <= 0) {
    const fallbackNumber = Number(fallback);

    if (Number.isFinite(fallbackNumber) && fallbackNumber > 0) {
      return Math.max(45, Math.min(100, Math.round(fallbackNumber)));
    }

    return 80;
  }

  return Math.max(45, Math.min(100, Math.round(number)));
}

function getAuthoritativeHealthScore(source = {}) {
  const report = source.website_health_report || {};
  const summary = source.scan_summary || {};
  const candidates = [
    source.health_score,
    source.seo_score,
    report.health_score,
    report.score,
    summary.health_score,
    summary.score,
  ];

  for (const value of candidates) {
    const number = Number(value);
    if (Number.isFinite(number) && number >= 0 && number <= 100) {
      return Math.round(number);
    }
  }

  return null;
}

function computeSimpleHealthScore(fixes, scanData = {}) {
  if (!Array.isArray(fixes) || fixes.length === 0) {
    return normalizeScore(scanData.health_score || scanData.seo_score || 92);
  }

  let score = 92;

  for (const fix of fixes) {
    if (fix.priority === "critical" || fix.priority === "high") {
      score -= 6;
    } else if (fix.priority === "medium") {
      score -= 4;
    } else {
      score -= 1;
    }
  }

  return normalizeScore(score);
}

function summarizeFixes(fixes) {
  const summary = {
    we_can_fix: 0,
    needs_approval: 0,
    needs_developer: 0,
  };

  for (const fix of fixes || []) {
    if (fix.status === "needs_developer" || fix.requires_developer) {
      summary.needs_developer += 1;
    } else if (fix.status === "needs_approval" || fix.requires_approval) {
      summary.needs_approval += 1;
    } else if (fix.status === "auto_fixed" || fix.can_auto_fix) {
      summary.we_can_fix += 1;
    } else {
      summary.needs_approval += 1;
    }
  }

  return summary;
}

function extractFindings(scanData = {}) {
  const groupedFindings = Array.isArray(scanData.grouped_findings)
    ? scanData.grouped_findings
    : [];

  const rawFindings = Array.isArray(scanData.raw_findings)
    ? scanData.raw_findings
    : [];

  const legacyFixes = Array.isArray(scanData.fixes) ? scanData.fixes : [];
  const legacyIssues = Array.isArray(scanData.issues) ? scanData.issues : [];
  const recommendations = Array.isArray(scanData.recommendations)
    ? scanData.recommendations
    : [];

  if (groupedFindings.length > 0) return groupedFindings;
  if (legacyFixes.length > 0) return legacyFixes;
  if (legacyIssues.length > 0) return legacyIssues;
  if (recommendations.length > 0) return recommendations;
  return rawFindings;
}

export default function CrawlStatus() {
  const [crawlJob, setCrawlJob] = useState(null);
  const [project, setProject] = useState(null);
  const [competitors, setCompetitors] = useState([]);
  const [scanStarted, setScanStarted] = useState(false);
  const [loading, setLoading] = useState(true);
  const [simulating, setSimulating] = useState(false);
  const [error, setError] = useState(null);
  const [scanResult, setScanResult] = useState(null);
  const [activeScanMode, setActiveScanMode] = useState("quick");

  const didAutoStart = useRef(false);
  const progressRunIdRef = useRef(0);

  useEffect(() => {
    trackEvent("scan_page_viewed");

    const load = async () => {
      try {
        const user = await base44.auth.me();
        const activeProjectId = window.localStorage.getItem("active_project_id");
        let activeProject = null;

        if (activeProjectId) {
          try {
            activeProject =
              await base44.entities.BusinessProject.get(activeProjectId);
          } catch {}
        }

        if (!activeProject) {
          const projects = await base44.entities.BusinessProject.list(
            "-last_crawl_at",
            10
          );

          activeProject =
            projects.find(
              (item) =>
                item.owner_user_id === user.id || item.created_by_id === user.id
            ) ||
            projects[0] ||
            null;
        }

        if (activeProject) {
          setProject(activeProject);
          setActiveScanMode(getScanMode(activeProject));

          try {
            const comps = await base44.entities.Competitor.filter({
              project_id: activeProject.id,
            });

            setCompetitors(comps || []);
          } catch {
            setCompetitors([]);
          }

          try {
            const jobs = await base44.entities.CrawlJob.filter(
              { project_id: activeProject.id },
              "-created_date",
              1
            );

            if (jobs.length > 0) setCrawlJob(jobs[0]);
          } catch {}
        }
      } catch (err) {
        console.warn("Could not load scan page data.", err);
      } finally {
        setLoading(false);
      }
    };

    load();
  }, []);

  useEffect(() => {
    if (didAutoStart.current || !project) return;

    const params = new URLSearchParams(window.location.search);

    if (params.get("autostart") === "1") {
      didAutoStart.current = true;
      simulateScan(crawlJob, project);
    }
  }, [project, crawlJob]);

  const runProgressSteps = async (job, scanMode, runId) => {
    const stepsBeforeComplete = getScanSteps(scanMode).filter(
      (step) => step.key !== "complete"
    );

    for (const step of stepsBeforeComplete) {
      await sleep(scanMode === "deep" ? 1200 : 700);

      if (progressRunIdRef.current !== runId) return;

      try {
        const updated = await base44.entities.CrawlJob.update(job.id, {
          status: step.key,
        });

        if (progressRunIdRef.current !== runId) return;

        setCrawlJob(updated);
      } catch (err) {
        console.warn("Could not update scan progress.", err);
      }
    }
  };

  const simulateScan = async (existingJob = null, projectOverride = null) => {
    const activeProject = projectOverride || project;
    if (!activeProject) return;

    const scanMode = getScanMode(activeProject);
    setActiveScanMode(scanMode);

    setScanStarted(true);
    setSimulating(true);
    setError(null);
    setScanResult(null);

    const runId = Date.now();
    progressRunIdRef.current = runId;

    let job = existingJob;

    try {
      const user = await base44.auth.me();

      trackEvent("scan_started", {
        project_id: activeProject.id,
        existing_job: Boolean(existingJob),
        scan_mode: scanMode,
      });

      if (!job) {
        job = await base44.entities.CrawlJob.create({
          project_id: activeProject.id,
          status: "queued",
          crawl_type: scanMode === "deep" ? "deep" : "full",
          started_at: new Date().toISOString(),
          owner_user_id: user.id,
        });
      } else {
        job = await base44.entities.CrawlJob.update(job.id, {
          status: "queued",
          crawl_type: scanMode === "deep" ? "deep" : "full",
          started_at: new Date().toISOString(),
          completed_at: "",
          error_message: "",
          owner_user_id: user.id,
        });
      }

      setCrawlJob(job);

      try {
        await base44.entities.SeoIssue.deleteMany({
          project_id: activeProject.id,
        });
      } catch (err) {
        console.warn("Could not clear previous recommendations.", err);
      }

      try {
        await base44.entities.CrawledPage.deleteMany({
          project_id: activeProject.id,
        });
      } catch (err) {
        console.warn("Could not clear previous crawled pages.", err);
      }

      runProgressSteps(job, scanMode, runId);

      const scanResponse = await withTimeout(
        base44.functions.invoke(SCAN_FUNCTION_NAME, {
          website_url: activeProject.website_url,
          business_name: activeProject.business_name,
          business_type: activeProject.business_type,
          city: activeProject.city,
          project_id: activeProject.id,
          crawl_job_id: job.id,
          important_keywords: activeProject.important_keywords || [],
          competitor_urls: activeProject.competitor_urls || [],
          scan_mode: scanMode,
        }),
        scanMode === "deep" ? 100000 : 70000,
        "Website scan"
      );

      const scanData = scanResponse?.data || {};

      if (scanData.error || scanData.success === false) {
        throw new Error(scanData.error || "Scan failed.");
      }

      const crawledPagesData = Array.isArray(scanData.crawled_pages)
        ? scanData.crawled_pages
        : Array.isArray(scanData.pages)
          ? scanData.pages
          : [];

      const findingsForMapping = extractFindings(scanData);
      const mappedSeoIssues = findingsForMapping.map(mapFindingToSeoIssue);

      let finalFixes = mappedSeoIssues;
      let authoritativeHealthScore = getAuthoritativeHealthScore(scanData);
      let topActions = [];
      let aiSummary = "";
      let positiveFindings = Array.isArray(scanData.site_summary?.positives)
        ? scanData.site_summary.positives
        : [];

      const createdCompetitors = Array.isArray(scanData.created_competitors)
        ? scanData.created_competitors
        : [];

      const discoveredCompetitors = Array.isArray(scanData.discovered_competitors)
        ? scanData.discovered_competitors
        : [];

      if (createdCompetitors.length > 0) {
        setCompetitors(createdCompetitors);
      }

      let competitorResultsForReview = Array.isArray(scanData.competitor_results)
        ? scanData.competitor_results
        : [];

      if (
        competitorResultsForReview.length === 0 &&
        discoveredCompetitors.length > 0
      ) {
        competitorResultsForReview = discoveredCompetitors;
      }

      /**
       * Optional AI review.
       * If the function does not exist, this catches the error and continues.
       */
      try {
        const aiReviewRes = await withTimeout(
          base44.functions.invoke(AI_REVIEW_FUNCTION_NAME, {
            scan: {
              ...scanData,
              business_name: activeProject.business_name,
              business_type: activeProject.business_type,
              city: activeProject.city,
              website_url: activeProject.website_url,
              project_id: activeProject.id,
              crawl_job_id: job.id,
              crawled_pages: crawledPagesData,
              competitor_results: competitorResultsForReview,
              discovered_competitors: discoveredCompetitors,
              scan_mode: scanMode,
              crawl_warnings: scanData.crawl_warnings || [],
            },
          }),
          125000,
          "AI review"
        );

        const aiData = aiReviewRes?.data || {};
        const aiFixes = Array.isArray(aiData.cleaned_fixes)
          ? aiData.cleaned_fixes
          : [];

        if (aiData.success) {
          finalFixes = selectFinalReviewFixes({
            aiData,
            aiFixes,
            scannerFixes: findingsForMapping,
            slimFix: mapFindingToSeoIssue,
          });

          const reviewScore = getAuthoritativeHealthScore(aiData);
          if (reviewScore !== null) authoritativeHealthScore = reviewScore;

          topActions = Array.isArray(aiData.top_recommended_actions)
            ? aiData.top_recommended_actions
            : [];
          positiveFindings = Array.isArray(aiData.positive_findings)
            ? aiData.positive_findings
            : positiveFindings;
          aiSummary =
            typeof aiData.plain_english_summary === "string"
              ? aiData.plain_english_summary
              : "";
        } else {
          finalFixes = mappedSeoIssues;
        }
      } catch (err) {
        console.warn(
          "AI review not available. Saving crawler recommendations.",
          err
        );
        finalFixes = mappedSeoIssues;
      }


      progressRunIdRef.current = 0;

      const pagesCrawled =
        typeof scanData.pages_crawled === "number"
          ? scanData.pages_crawled
          : crawledPagesData.length;

      const finalSummary = summarizeFixes(finalFixes);
      const finalHealthScore =
        authoritativeHealthScore ??
        computeSimpleHealthScore(finalFixes, scanData);

      if (crawledPagesData.length > 0) {
        await base44.entities.CrawledPage.bulkCreate(
          crawledPagesData.map((page) => ({
            ...mapCrawledPageForStorage(page),
            project_id: activeProject.id,
            crawl_job_id: job.id,
            owner_user_id: user.id,
          }))
        );
      }

      if (finalFixes.length > 0) {
        const seoIssues = finalFixes.map((fix) =>
          normalizeSeoIssueForSave(fix, activeProject, job, user)
        );

        await saveSeoIssuesSafely(seoIssues);
      }

      try {
        await base44.entities.DeveloperRecommendation.deleteMany({
          project_id: activeProject.id,
        });
      } catch (err) {
        console.warn("Could not clear previous website improvements.", err);
      }

      const developerFixes = finalFixes.filter(
        (fix) =>
          fix.requires_developer === true || fix.status === "needs_developer"
      );

      if (developerFixes.length > 0) {
        await base44.entities.DeveloperRecommendation.bulkCreate(
          developerFixes.map((fix) =>
            buildDeveloperRecommendation(fix, activeProject, user)
          )
        );
      }

      try {
        await base44.entities.ScanDiagnostic.create({
          project_id: activeProject.id,
          crawl_job_id: job.id,
          owner_user_id: user.id,
          scan_source: SCAN_FUNCTION_NAME,
          scan_mode: scanMode,
          raw_findings_count: Array.isArray(scanData.raw_findings)
            ? scanData.raw_findings.length
            : 0,
          grouped_findings_count: Array.isArray(scanData.grouped_findings)
            ? scanData.grouped_findings.length
            : 0,
          cleaned_fixes_count: finalFixes.length,
          saved_seo_issue_count: finalFixes.length,
          pages_crawled: pagesCrawled,
          pages_found:
            typeof scanData.pages_found === "number"
              ? scanData.pages_found
              : pagesCrawled,
          health_score: finalHealthScore,
          discovered_competitor_count: discoveredCompetitors.length,
          competitor_result_count: competitorResultsForReview.length,
          crawl_warnings: Array.isArray(scanData.crawl_warnings)
            ? scanData.crawl_warnings
            : [],
          site_summary: scanData.site_summary || {},
          created_at: new Date().toISOString(),
        });
      } catch (err) {
        console.warn("Could not save scan diagnostic.", err);
      }

      const completedJob = await base44.entities.CrawlJob.update(job.id, {
        status: "complete",
        completed_at: new Date().toISOString(),
        pages_found:
          typeof scanData.pages_found === "number"
            ? scanData.pages_found
            : pagesCrawled,
        pages_crawled: pagesCrawled,
        seo_score: finalHealthScore,
        issues_found: finalFixes.length,
        error_message: "",
      });

      setCrawlJob(completedJob);

      const updatedProject = await base44.entities.BusinessProject.update(
        activeProject.id,
        {
          last_crawl_at: new Date().toISOString(),
          seo_score: finalHealthScore,
          status: "active",
          scan_mode: scanMode,
        }
      );

      setProject(updatedProject);

      const result = {
        fixes: finalFixes,
        health_score: finalHealthScore,
        pages_crawled: pagesCrawled,
        issues_found: finalFixes.length,
        summary: finalSummary,
        top_actions: topActions,
        positive_findings: positiveFindings,
        ai_summary: aiSummary,
        competitor_result: {
          discovered_competitors: discoveredCompetitors,
          created_competitors: createdCompetitors,
          competitor_results: competitorResultsForReview,
        },
        discovered_competitors_count: discoveredCompetitors.length,
        crawl_warnings: scanData.crawl_warnings || [],
      };

      setScanResult(result);

      trackEvent("scan_completed", {
        project_id: activeProject.id,
        pages_crawled: pagesCrawled,
        issues_found: finalFixes.length,
        health_score: finalHealthScore,
        scan_mode: scanMode,
        scan_function: SCAN_FUNCTION_NAME,
      });
    } catch (err) {
      console.error("Scan failed.", err);

      progressRunIdRef.current = 0;

      if (job) {
        try {
          const failedJob = await base44.entities.CrawlJob.update(job.id, {
            status: "failed",
            completed_at: new Date().toISOString(),
            error_message: err.message || "Scan failed",
          });

          setCrawlJob(failedJob);
        } catch {}
      }

      setError(
        err.message ||
          "The scan could not complete. Please check the website URL and try again."
      );

      trackEvent("scan_failed", {
        project_id: activeProject.id,
        message: err.message || "Scan failed",
        scan_mode: scanMode,
        scan_function: SCAN_FUNCTION_NAME,
      });
    } finally {
      setSimulating(false);
    }
  };

  const handleScan = async (form) => {
    setSimulating(true);
    setError(null);

    try {
      const user = await base44.auth.me();
      let activeProject = project;

      const scanMode = form.scan_mode === "deep" ? "deep" : "quick";
      const competitorUrls = getCompetitorUrlsFromForm(form);

      const projectData = {
        business_name: form.business_name,
        website_url: form.website_url,
        important_keywords: form.important_keywords || [],
        scan_mode: scanMode,
      };

      if (activeProject) {
        activeProject = await base44.entities.BusinessProject.update(
          activeProject.id,
          projectData
        );
      } else {
        activeProject = await base44.entities.BusinessProject.create({
          ...projectData,
          status: "active",
          seo_score: 0,
          subscription_plan: "free",
          cms_platform: "Unknown",
          owner_user_id: user.id,
        });
      }

      const projectForScan = {
        ...activeProject,
        important_keywords: form.important_keywords || [],
        competitor_urls: competitorUrls,
        scan_mode: scanMode,
      };

      setProject(projectForScan);
      setActiveScanMode(scanMode);
      setCompetitors([]);
      window.localStorage.setItem("active_project_id", activeProject.id);

      await simulateScan(null, projectForScan);
    } catch (err) {
      setError(err.message || "Could not start the scan. Please try again.");
      setSimulating(false);
    }
  };

  const scanSteps = getScanSteps(activeScanMode);

  const currentIndex = crawlJob
    ? scanSteps.findIndex((step) => step.key === crawlJob.status)
    : -1;

  const showProgress =
    scanStarted ||
    (crawlJob && !["complete", "failed"].includes(crawlJob.status));

  const hasNoRecommendations = (scanResult?.issues_found ?? 0) === 0;

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-slate-200 border-t-blue-600" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#F7F8FA]">
      <div className="mx-auto w-full max-w-4xl px-5 py-10 sm:px-6 lg:py-12">
        <div className="mb-8">
          <p className="text-sm font-medium text-blue-600">Start a review</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">
            Scan Website
          </h1>
          <p className="mt-2 text-base leading-7 text-slate-500">
            SEO Autopilot scans your website, reviews important pages, looks for
            competitor opportunities when possible, and prepares a simple Fix
            List.
          </p>
        </div>

        <ScanWebsiteForm
          project={project}
          competitors={competitors}
          saving={simulating}
          onScan={handleScan}
        />

        {error && (
          <div className="mt-6 rounded-3xl border border-red-100 bg-white p-5 shadow-sm">
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-0.5 h-4 w-4 text-red-500" />
              <div>
                <p className="text-sm font-medium text-slate-950">
                  Scan failed
                </p>
                <p className="mt-1 text-sm leading-6 text-slate-600">
                  {error}
                </p>

                <p className="mt-3 text-xs leading-5 text-slate-400">
                  This page is currently calling the backend function:{" "}
                  <span className="font-mono">{SCAN_FUNCTION_NAME}</span>
                </p>
              </div>
            </div>
          </div>
        )}

        {showProgress && crawlJob && (
          <div className="mt-6 rounded-3xl border border-slate-200/80 bg-white p-6 shadow-sm">
            <h2 className="text-base font-semibold text-slate-950">
              Scan progress
            </h2>

            <div className="mt-5 space-y-4">
              {scanSteps.map((step, index) => {
                const isComplete =
                  crawlJob.status === "complete" || index < currentIndex;
                const isCurrent =
                  index === currentIndex && crawlJob.status !== "complete";

                return (
                  <div key={step.key} className="flex items-center gap-3">
                    <div
                      className={`flex h-6 w-6 items-center justify-center rounded-full ${
                        isComplete
                          ? "bg-slate-950"
                          : isCurrent
                            ? "bg-blue-600"
                            : "bg-slate-100"
                      }`}
                    >
                      {isComplete ? (
                        <CheckCircle2 className="h-3.5 w-3.5 text-white" />
                      ) : isCurrent ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin text-white" />
                      ) : (
                        <Circle className="h-3.5 w-3.5 text-slate-300" />
                      )}
                    </div>

                    <span
                      className={`text-sm ${
                        isComplete || isCurrent
                          ? "font-medium text-slate-950"
                          : "text-slate-500"
                      }`}
                    >
                      {step.label}
                    </span>
                  </div>
                );
              })}
            </div>

            <p className="mt-5 text-xs leading-5 text-slate-400">
              This scan reviews website content we can access directly. Some
              websites may need a deeper manual review.
            </p>
          </div>
        )}

        {scanStarted && crawlJob?.status === "complete" && scanResult && (
          <div className="mt-6 rounded-3xl border border-slate-200/80 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-slate-950">
              Your scan is complete.
            </h2>

            <p className="mt-2 text-sm leading-6 text-slate-600">
              We reviewed {scanResult.pages_crawled ?? 0} pages and prepared{" "}
              {scanResult.issues_found ?? 0} recommended{" "}
              {(scanResult.issues_found ?? 0) === 1
                ? "improvement"
                : "improvements"}
              {scanResult.discovered_competitors_count > 0
                ? `, plus ${scanResult.discovered_competitors_count} competitor ${
                    scanResult.discovered_competitors_count === 1
                      ? "opportunity"
                      : "opportunities"
                  }`
                : ""}
              .
            </p>

            {scanResult.ai_summary && (
              <p className="mt-4 text-sm leading-6 text-slate-600">
                {scanResult.ai_summary}
              </p>
            )}

            {scanResult.positive_findings?.length > 0 && (
              <div className="mt-5">
                <p className="text-xs font-medium uppercase tracking-wide text-slate-400">
                  What’s working well
                </p>

                <div className="mt-3 space-y-2">
                  {scanResult.positive_findings.map((finding, index) => (
                    <p key={index} className="text-sm leading-6 text-slate-600">
                      {finding}
                    </p>
                  ))}
                </div>
              </div>
            )}

            <div className="mt-5 grid gap-3 md:grid-cols-3">
              <div className="rounded-xl bg-slate-50 p-4">
                <div className="text-2xl font-semibold text-slate-950">
                  {scanResult.summary?.we_can_fix ?? 0}
                </div>
                <div className="text-sm text-slate-500">Prepared</div>
              </div>

              <div className="rounded-xl bg-slate-50 p-4">
                <div className="text-2xl font-semibold text-slate-950">
                  {scanResult.summary?.needs_approval ?? 0}
                </div>
                <div className="text-sm text-slate-500">Needs review</div>
              </div>

              <div className="rounded-xl bg-slate-50 p-4">
                <div className="text-2xl font-semibold text-slate-950">
                  {scanResult.summary?.needs_developer ?? 0}
                </div>
                <div className="text-sm text-slate-500">May need help</div>
              </div>
            </div>

            {Array.isArray(scanResult.crawl_warnings) &&
              scanResult.crawl_warnings.length > 0 && (
                <p className="mt-4 text-xs leading-5 text-slate-400">
                  Some parts of the site could not be reviewed automatically.
                  Your Fix List is based on the pages we could access.
                </p>
              )}

            <div className="mt-6">
              <Button
                asChild
                className="rounded-full bg-blue-600 px-5 py-2.5 text-sm font-medium text-white shadow-none hover:bg-blue-700"
              >
                <a href="/dashboard">View Fix List</a>
              </Button>
            </div>

            {hasNoRecommendations && (
              <p className="mt-4 text-sm text-slate-500">
                No major recommendations found based on the website content we
                could access.
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}