import React, { useEffect, useRef, useState } from "react";
import { base44 } from "@/api/base44Client";
import { trackEvent } from "@/lib/analytics";
import { computeHealthScore, summarizeFixes } from "@/lib/aiReview";
import ScanWebsiteForm from "@/components/scan/ScanWebsiteForm";
import { Button } from "@/components/ui/button";
import { AlertTriangle, CheckCircle2, Circle, Loader2 } from "lucide-react";

const SCAN_STEPS = [
  { key: "queued", label: "Finding pages" },
  { key: "crawling_html", label: "Reading website content" },
  { key: "checking_metadata", label: "Checking search appearance" },
  { key: "checking_canonicals", label: "Reviewing website setup" },
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

const normalizePageUrl = (finding) => {
  if (finding.page_url) return finding.page_url;
  if (Array.isArray(finding.affected_pages) && finding.affected_pages[0]) {
    return finding.affected_pages[0];
  }

  try {
    if (finding.full_url) return new URL(finding.full_url).pathname || "/";
  } catch {}

  return "/";
};

const getSafeStatus = (item) => {
  if (VALID_STATUSES.has(item.status)) return item.status;
  if (item.requires_developer) return "needs_developer";
  if (item.requires_approval) return "needs_approval";
  if (item.can_auto_fix) return "auto_fixed";
  return "needs_approval";
};

const getSafeCategory = (category) => {
  const mapped = CATEGORY_MAP[category] || category || "web_dev";
  return VALID_CATEGORIES.has(mapped) ? mapped : "web_dev";
};

const mapGroupedFindingToSeoIssue = (finding) => {
  const affectedPages = Array.isArray(finding.affected_pages)
    ? finding.affected_pages.filter(Boolean)
    : [];

  const status = getSafeStatus(finding);
  const category = getSafeCategory(finding.category);

  const recommendation =
    finding.ai_recommendation ||
    finding.recommended_value ||
    finding.recommendation ||
    "Review this recommendation.";

  const details = {
    ...(finding.details || {}),
    original_category: finding.category || "",
    scan_source: "runAdvancedScan",
    grouped: finding.type === "site_level",
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
    customer_category: finding.customer_category || "Website improvement",
    priority: VALID_PRIORITIES.has(finding.priority) ? finding.priority : "medium",
    status,
    difficulty: VALID_DIFFICULTIES.has(finding.difficulty)
      ? finding.difficulty
      : status === "needs_developer"
        ? "developer"
        : "easy",
    issue_title:
      finding.issue_title ||
      finding.title ||
      "Review this website recommendation",
    plain_english_explanation:
      finding.plain_english_explanation ||
      finding.explanation ||
      finding.evidence ||
      "This recommendation was found during the website scan.",
    why_it_matters:
      finding.why_it_matters ||
      finding.why ||
      "Improving this can help visitors and search engines understand the website more clearly.",
    current_value: finding.current_value || "",
    recommended_value: finding.recommended_value || recommendation,
    ai_recommendation: recommendation,
    confidence_score:
      typeof finding.confidence_score === "number"
        ? finding.confidence_score
        : 90,
    can_auto_fix: finding.can_auto_fix === true || status === "auto_fixed",
    requires_approval:
      finding.requires_approval === true || status === "needs_approval",
    requires_developer:
      finding.requires_developer === true || status === "needs_developer",
  };
};

const mapCrawledPageForStorage = (page) => ({
  url: page.url || page.final_url || page.original_url || "",
  status_code: page.status_code || page.status || 0,
  title: page.title || "",
  meta_description: page.meta_description || page.metaDesc || "",
  h1: page.h1 || "",
  canonical_url: page.canonical_url || page.canonical || "",
  word_count: page.word_count || page.wordCount || 0,
  indexable: !/noindex/i.test(page.robots_meta || ""),
  in_sitemap: false,
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
  placeholder_hits: page.placeholder_hits || page.placeholderHits || page.placeholder_text || [],
});

const normalizeSeoIssueForSave = (fix, project, job, user) => {
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
      fix.recommended_value || fix.ai_recommendation || "Review this recommendation.",
    ai_recommendation:
      fix.ai_recommendation || fix.recommended_value || "Review this recommendation.",
    confidence_score:
      typeof fix.confidence_score === "number" ? fix.confidence_score : 90,
    can_auto_fix: fix.can_auto_fix === true || status === "auto_fixed",
    requires_approval:
      fix.requires_approval === true || status === "needs_approval",
    requires_developer:
      fix.requires_developer === true || status === "needs_developer",
    affected_pages: Array.isArray(fix.affected_pages) ? fix.affected_pages : [],
    details: fix.details && typeof fix.details === "object" ? fix.details : {},
  };
};

const buildDeveloperRecommendation = (fix, project, user) => {
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
};

export default function CrawlStatus() {
  const [crawlJob, setCrawlJob] = useState(null);
  const [project, setProject] = useState(null);
  const [competitors, setCompetitors] = useState([]);
  const [scanStarted, setScanStarted] = useState(false);
  const [loading, setLoading] = useState(true);
  const [simulating, setSimulating] = useState(false);
  const [error, setError] = useState(null);
  const [scanResult, setScanResult] = useState(null);
  const didAutoStart = useRef(false);

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

  const runProgressSteps = async (job) => {
    const stepsBeforeComplete = SCAN_STEPS.filter(
      (step) => step.key !== "complete"
    );

    for (const step of stepsBeforeComplete) {
      await sleep(700);

      const updated = await base44.entities.CrawlJob.update(job.id, {
        status: step.key,
      });

      setCrawlJob(updated);
    }
  };

  const simulateScan = async (existingJob = null, projectOverride = null) => {
    const activeProject = projectOverride || project;
    if (!activeProject) return;

    setScanStarted(true);
    setSimulating(true);
    setError(null);
    setScanResult(null);

    let job = existingJob;

    try {
      const user = await base44.auth.me();

      trackEvent("scan_started", {
        project_id: activeProject.id,
        existing_job: Boolean(existingJob),
      });

      if (!job) {
        job = await base44.entities.CrawlJob.create({
          project_id: activeProject.id,
          status: "queued",
          crawl_type: "full",
          started_at: new Date().toISOString(),
          owner_user_id: user.id,
        });
      } else {
        job = await base44.entities.CrawlJob.update(job.id, {
          status: "queued",
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

      const progressPromise = runProgressSteps(job);

      const scanResponse = await base44.functions.invoke("runAdvancedScan", {
        website_url: activeProject.website_url,
        business_name: activeProject.business_name,
        business_type: activeProject.business_type,
        city: activeProject.city,
        project_id: activeProject.id,
        crawl_job_id: job.id,
      });

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

      if (rawFindings.length === 0 && groupedFindings.length === 0) {
        console.warn("runAdvancedScan returned zero findings", {
          website_url: activeProject.website_url,
          pages_crawled: scanData.pages_crawled,
          pages_found: scanData.pages_found,
          crawled_pages_sample: crawledPagesData.slice(0, 5),
          site_summary: scanData.site_summary,
          crawl_warnings: scanData.crawl_warnings,
        });
      }

      const findingsForMapping =
        groupedFindings.length > 0 ? groupedFindings : rawFindings;

      const mappedSeoIssues = findingsForMapping.map(mapGroupedFindingToSeoIssue);

      let finalFixes = mappedSeoIssues;
      let topActions = [];
      let aiSummary = "";
      let positiveFindings = Array.isArray(scanData.site_summary?.positives)
        ? scanData.site_summary.positives
        : [];

      try {
        const competitorResults = (competitors || []).map((competitor) => ({
          name: competitor.name,
          website_url: competitor.website_url,
          service_pages: competitor.service_pages_count,
          title_quality: competitor.title_quality_score,
          description_coverage: competitor.meta_coverage_pct,
          content_depth: competitor.content_depth_score,
        }));

        const aiReviewRes = await base44.functions.invoke("aiReviewScan", {
          business_name: activeProject.business_name,
          business_type: activeProject.business_type,
          city: activeProject.city,
          website_url: activeProject.website_url,
          crawled_pages: crawledPagesData,
          raw_fixes: mappedSeoIssues,
          competitor_results: competitorResults,
        });

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
          console.warn(
            "AI review returned no fixes. Falling back to grouped scan findings."
          );
          finalFixes = mappedSeoIssues;
        }
      } catch (err) {
        console.warn("AI review failed. Falling back to grouped scan findings.", err);
        finalFixes = mappedSeoIssues;
      }

      if (mappedSeoIssues.length > 0 && finalFixes.length === 0) {
        finalFixes = mappedSeoIssues;
      }

      console.log("Advanced scan result", {
        success: scanData.success,
        pages: scanData.pages_crawled,
        rawFindings: rawFindings.length,
        groupedFindings: groupedFindings.length,
        mappedSeoIssues: mappedSeoIssues.length,
        finalFixes: finalFixes.length,
        healthScore: scanData.health_score,
      });

      await progressPromise;

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

      let competitorScanResult = null;

      if ((competitors || []).length > 0) {
        try {
          competitorScanResult = await base44.functions.invoke("scanCompetitors", {
            project_id: activeProject.id,
            business_type: activeProject.business_type,
            city: activeProject.city,
            customer_pages: crawledPagesData,
          });
        } catch (err) {
          console.warn("Competitor scan failed.", err);
        }
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
        (fix) => fix.requires_developer === true || fix.status === "needs_developer"
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
          raw_findings_count: rawFindings.length,
          grouped_findings_count: groupedFindings.length,
          broken_links_count: Array.isArray(scanData.broken_links)
            ? scanData.broken_links.length
            : 0,
          pages_crawled: pagesCrawled,
          pages_found:
            typeof scanData.pages_found === "number"
              ? scanData.pages_found
              : pagesCrawled,
          health_score: finalHealthScore,
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
        competitor_result: competitorScanResult?.data || null,
      };

      setScanResult(result);

      trackEvent("scan_completed", {
        project_id: activeProject.id,
        pages_crawled: pagesCrawled,
        issues_found: finalFixes.length,
        health_score: finalHealthScore,
        raw_findings: rawFindings.length,
        grouped_findings: groupedFindings.length,
      });
    } catch (err) {
      console.error("Scan failed.", err);

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

      const projectData = {
        business_name: form.business_name,
        website_url: form.website_url,
        important_keywords: form.important_keywords || [],
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

      setProject(activeProject);
      window.localStorage.setItem("active_project_id", activeProject.id);

      try {
        await base44.entities.Competitor.deleteMany({
          project_id: activeProject.id,
        });
      } catch {}

      const competitorUrls = (form.competitor_urls || [])
        .map((url) => url.trim())
        .filter(Boolean);

      let createdCompetitors = [];

      if (competitorUrls.length > 0) {
        createdCompetitors = await base44.entities.Competitor.bulkCreate(
          competitorUrls.map((url) => {
            let normalizedUrl = url;
            let name = url;

            try {
              normalizedUrl = /^https?:\/\//i.test(url) ? url : `https://${url}`;
              name = new URL(normalizedUrl).hostname.replace(/^www\./, "");
            } catch {}

            return {
              project_id: activeProject.id,
              website_url: normalizedUrl,
              name,
              owner_user_id: user.id,
            };
          })
        );
      }

      setCompetitors(createdCompetitors);

      await simulateScan(null, activeProject);
    } catch (err) {
      setError(err.message || "Could not start the scan. Please try again.");
      setSimulating(false);
    }
  };

  const currentIndex = crawlJob
    ? SCAN_STEPS.findIndex((step) => step.key === crawlJob.status)
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
            Enter your website and we’ll prepare a simple Fix List.
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
              {SCAN_STEPS.map((step, index) => {
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
              We scanned {scanResult.pages_crawled ?? 0} pages and found{" "}
              {scanResult.issues_found ?? 0} recommended{" "}
              {(scanResult.issues_found ?? 0) === 1
                ? "improvement"
                : "improvements"}
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
                    <p
                      key={index}
                      className="text-sm leading-6 text-slate-600"
                    >
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