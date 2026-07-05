import React, { useEffect, useRef, useState } from "react";
import { base44 } from "@/api/base44Client";
import { trackEvent } from "@/lib/analytics";
import { computeHealthScore, summarizeFixes } from "@/lib/aiReview";
import ScanWebsiteForm from "@/components/scan/ScanWebsiteForm";
import { Button } from "@/components/ui/button";
import { AlertTriangle, CheckCircle2, Circle, Loader2 } from "lucide-react";

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
  image_alt_text: "image_alt_text",
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
  "image_alt_text",
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

function normalizePageUrl(finding) {
  if (finding?.page_url) return finding.page_url;

  if (Array.isArray(finding?.affected_pages) && finding.affected_pages[0]) {
    return finding.affected_pages[0];
  }

  try {
    if (finding?.full_url) return new URL(finding.full_url).pathname || "/";
  } catch {}

  return "/";
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

function mapGroupedFindingToSeoIssue(finding) {
  const affectedPages = Array.isArray(finding?.affected_pages)
    ? finding.affected_pages.filter(Boolean)
    : [];

  const status = getSafeStatus(finding);
  const category = getSafeCategory(finding?.category);

  const recommendation =
    finding?.ai_recommendation ||
    finding?.recommended_value ||
    finding?.recommendation ||
    "Review this recommendation.";

  const details = {
    ...(finding?.details || {}),
    original_category: finding?.category || "",
    scan_source: "runAdvancedScan",
    grouped: finding?.type === "site_level",
    html_only_scan: true,
    javascript_rendering_used: false,
  };

  if (affectedPages.length > 0 && !details.affected_count) {
    details.affected_count = affectedPages.length;
  }

  return {
    page_url: normalizePageUrl(finding),
    affected_pages: affectedPages,
    details,
    category,
    customer_category: finding?.customer_category || "Website improvement",
    priority: VALID_PRIORITIES.has(finding?.priority)
      ? finding.priority
      : "medium",
    status,
    difficulty: VALID_DIFFICULTIES.has(finding?.difficulty)
      ? finding.difficulty
      : status === "needs_developer"
        ? "developer"
        : "easy",
    issue_title:
      finding?.issue_title ||
      finding?.title ||
      "Review this website recommendation",
    plain_english_explanation:
      finding?.plain_english_explanation ||
      finding?.explanation ||
      finding?.evidence ||
      "This recommendation was found during the website scan.",
    why_it_matters:
      finding?.why_it_matters ||
      finding?.why ||
      "Improving this can help visitors and search engines understand the website more clearly.",
    current_value: finding?.current_value || "",
    recommended_value: finding?.recommended_value || recommendation,
    ai_recommendation: recommendation,
    confidence_score:
      typeof finding?.confidence_score === "number"
        ? finding.confidence_score
        : 90,
    can_auto_fix: finding?.can_auto_fix === true || status === "auto_fixed",
    requires_approval:
      finding?.requires_approval === true || status === "needs_approval",
    requires_developer:
      finding?.requires_developer === true || status === "needs_developer",
  };
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
    indexable: !/noindex/i.test(page.robots_meta || ""),
    in_sitemap: Boolean(page.in_sitemap),
    rendered_title: "",
    rendered_meta_description: "",
    rendered_canonical: "",
    js_difference_detected: false,
    h2s: page.h2s || [],
    h3s: page.h3s || [],
    has_faq: Boolean(page.has_faq || page.hasFaq),
    faq_questions: page.faq_questions || page.faqQuestions || [],
    has_schema: Boolean(page.has_schema || page.hasSchema),
    schema_types: page.schema_types || page.schemaTypes || [],
    has_phone: Boolean(page.has_phone || page.hasPhone),
    has_email: Boolean(page.has_email || page.hasEmail),
    cta_phrases: page.cta_phrases || page.ctaPhrases || [],
    trust_signals: page.trust_signals || page.trustSignals || [],
    image_count: page.image_count || page.imageCount || 0,
    images_missing_alt_count:
      page.images_missing_alt_count || page.imagesMissingAltCount || 0,
    placeholder_hits:
      page.placeholder_hits ||
      page.placeholderHits ||
      page.placeholder_text ||
      [],
  };
}

function normalizeSeoIssueForSave(fix, project, job, user) {
  const status = getSafeStatus(fix);
  const category = getSafeCategory(fix?.category);

  return {
    project_id: project.id,
    crawl_job_id: job.id,
    owner_user_id: user.id,
    page_url: fix?.page_url || "/",
    category,
    customer_category: fix?.customer_category || "Website improvement",
    priority: VALID_PRIORITIES.has(fix?.priority) ? fix.priority : "medium",
    status,
    difficulty: VALID_DIFFICULTIES.has(fix?.difficulty)
      ? fix.difficulty
      : status === "needs_developer"
        ? "developer"
        : "easy",
    issue_title: fix?.issue_title || "Review this website recommendation",
    plain_english_explanation:
      fix?.plain_english_explanation ||
      "This recommendation was found during the website scan.",
    why_it_matters:
      fix?.why_it_matters ||
      "Improving this can help visitors and search engines understand the website more clearly.",
    current_value: fix?.current_value || "",
    recommended_value:
      fix?.recommended_value ||
      fix?.ai_recommendation ||
      "Review this recommendation.",
    ai_recommendation:
      fix?.ai_recommendation ||
      fix?.recommended_value ||
      "Review this recommendation.",
    confidence_score:
      typeof fix?.confidence_score === "number" ? fix.confidence_score : 90,
    can_auto_fix: fix?.can_auto_fix === true || status === "auto_fixed",
    requires_approval:
      fix?.requires_approval === true || status === "needs_approval",
    requires_developer:
      fix?.requires_developer === true || status === "needs_developer",
    affected_pages: Array.isArray(fix?.affected_pages) ? fix.affected_pages : [],
    details: fix?.details && typeof fix.details === "object" ? fix.details : {},
  };
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

  const recommended_package =
    estimated_complexity === "moderate" ? "500_cleanup" : "diy";

  return {
    project_id: project.id,
    owner_user_id: user.id,
    title: fix.issue_title,
    description: fix.plain_english_explanation,
    category,
    priority: fix.priority,
    business_impact: fix.why_it_matters,
    estimated_complexity,
    recommended_package,
    status: "open",
  };
}

function getCompetitorUrlsFromForm(form) {
  return (form?.competitor_urls || [])
    .map((url) => String(url || "").trim())
    .filter(Boolean);
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

          const comps = await base44.entities.Competitor.filter({
            project_id: activeProject.id,
          });

          setCompetitors(comps || []);

          const jobs = await base44.entities.CrawlJob.filter(
            { project_id: activeProject.id },
            "-created_date",
            1
          );

          if (jobs.length > 0) setCrawlJob(jobs[0]);
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

    if (params.get("autostart") === "1" && crawlJob?.status === "queued") {
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
        base44.functions.invoke("runAdvancedScan", {
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
        scanMode === "deep" ? 90000 : 45000,
        "Website scan"
      );

      const scanData = scanResponse?.data || {};

      if (scanData.error || scanData.success === false) {
        throw new Error(scanData.error || "Scan failed.");
      }

      const crawledPagesData = Array.isArray(scanData.crawled_pages)
        ? scanData.crawled_pages
        : [];

      const groupedFindings = Array.isArray(scanData.grouped_findings)
        ? scanData.grouped_findings
        : [];

      const rawFindings = Array.isArray(scanData.raw_findings)
        ? scanData.raw_findings
        : [];

      const findingsForMapping =
        groupedFindings.length > 0 ? groupedFindings : rawFindings;

      const mappedSeoIssues = findingsForMapping.map(mapGroupedFindingToSeoIssue);

      let finalFixes = mappedSeoIssues;
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

      try {
        const aiReviewRes = await withTimeout(
          base44.functions.invoke("aiReviewScan", {
            business_name: activeProject.business_name,
            business_type: activeProject.business_type,
            city: activeProject.city,
            website_url: activeProject.website_url,
            crawled_pages: crawledPagesData,
            raw_fixes: mappedSeoIssues,
            competitor_results: competitorResultsForReview,
            discovered_competitors: discoveredCompetitors,
            scan_mode: scanMode,
            crawl_warnings: scanData.crawl_warnings || [],
          }),
          30000,
          "AI review"
        );

        const aiData = aiReviewRes?.data || {};
        const aiFixes = Array.isArray(aiData.cleaned_fixes)
          ? aiData.cleaned_fixes
          : [];

        if (aiData.success && aiFixes.length > 0) {
          finalFixes = aiFixes;
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
          "AI review failed or timed out. Falling back to crawler findings.",
          err
        );
        finalFixes = mappedSeoIssues;
      }

      if (mappedSeoIssues.length > 0 && finalFixes.length === 0) {
        finalFixes = mappedSeoIssues;
      }

      progressRunIdRef.current = 0;

      const pagesCrawled =
        typeof scanData.pages_crawled === "number"
          ? scanData.pages_crawled
          : crawledPagesData.length;

      const finalSummary = summarizeFixes(finalFixes);

      const finalHealthScore =
        finalFixes.length > 0
          ? computeHealthScore(finalFixes)
          : typeof scanData.health_score === "number"
            ? scanData.health_score
            : 100;

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
        await base44.entities.SeoIssue.bulkCreate(
          finalFixes.map((fix) =>
            normalizeSeoIssueForSave(fix, activeProject, job, user)
          )
        );
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
          scan_source: "runAdvancedScan",
          scan_mode: scanMode,
          raw_findings_count: rawFindings.length,
          grouped_findings_count: groupedFindings.length,
          cleaned_fixes_count: finalFixes.length,
          broken_links_count: Array.isArray(scanData.broken_links)
            ? scanData.broken_links.length
            : 0,
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
        raw_findings: rawFindings.length,
        grouped_findings: groupedFindings.length,
        cleaned_fixes: finalFixes.length,
        scan_mode: scanMode,
        discovered_competitors: discoveredCompetitors.length,
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
              We reviewed {scanResult.pages_crawled ?? 0} pages and found{" "}
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