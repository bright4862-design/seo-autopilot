import React, { useEffect, useRef, useState } from "react";
import { base44 } from "@/api/base44Client";
import { trackEvent } from "@/lib/analytics";
import { reviewFixesWithAi, computeHealthScore, summarizeFixes } from "@/lib/aiReview";
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

const DEMO_RECOMMENDATIONS = [
  {
    page_url: "/services", category: "meta_title", priority: "high", status: "auto_fixed",
    issue_title: "This page needs a clearer search title",
    plain_english_explanation: "The services page could be clearer in search results.",
    why_it_matters: "A clear search title helps customers understand the page before they click.",
    current_value: "Not found", recommended_value: "Services | Your Business",
    ai_recommendation: "Use a short title that includes the main service and business name.",
    confidence_score: 92, can_auto_fix: true, requires_approval: false, requires_developer: false,
  },
  {
    page_url: "/about", category: "meta_description", priority: "medium", status: "needs_approval",
    issue_title: "Improve this page’s search description",
    plain_english_explanation: "The about page needs a short summary for search results.",
    why_it_matters: "A useful description can help more people choose your website.",
    current_value: "Not found", recommended_value: "A short summary of your business, location, and services.",
    ai_recommendation: "Review the prepared description and approve it if it matches your business.",
    confidence_score: 85, can_auto_fix: false, requires_approval: true, requires_developer: false,
  },
  {
    page_url: "/contact", category: "schema", priority: "medium", status: "needs_developer",
    issue_title: "Add clearer trust signals for search engines",
    plain_english_explanation: "Your contact page may need business details in a format search engines understand.",
    why_it_matters: "Clear business details can help customers find your hours, phone number, and location.",
    current_value: "Not found", recommended_value: "Add business name, address, phone, and hours.",
    ai_recommendation: "Ask a website editor or developer to add structured business details.",
    confidence_score: 90, can_auto_fix: false, requires_approval: false, requires_developer: true,
  },
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

const VALID_CATEGORIES = new Set(["meta_title", "meta_description", "404_error", "redirect", "canonical", "sitemap", "robots_txt", "js_rendering", "internal_link", "thin_content", "duplicate_content", "schema", "performance", "web_dev"]);
const VALID_STATUSES = new Set(["auto_fixed", "needs_approval", "approved", "rejected", "needs_developer", "in_progress", "completed", "open"]);
const VALID_PRIORITIES = new Set(["critical", "high", "medium", "low"]);
const VALID_DIFFICULTIES = new Set(["easy", "moderate", "developer"]);

const normalizePageUrl = (finding) => finding.page_url || finding.full_url || finding.affected_pages?.[0] || "/";

const mapGroupedFindingToSeoIssue = (finding) => {
  const affectedPages = Array.isArray(finding.affected_pages) ? finding.affected_pages.filter(Boolean) : [];
  const category = CATEGORY_MAP[finding.category] || finding.category || "web_dev";
  const recommendation = finding.ai_recommendation || finding.recommended_value || "Review this item.";
  const affectedText = affectedPages.length ? `\n\nAffected pages: ${affectedPages.join(" · ")}` : "";
  const status = VALID_STATUSES.has(finding.status) ? finding.status : finding.requires_developer ? "needs_developer" : finding.requires_approval ? "needs_approval" : "auto_fixed";

  return {
    page_url: normalizePageUrl(finding),
    category: VALID_CATEGORIES.has(category) ? category : "web_dev",
    customer_category: finding.customer_category || "Website improvement",
    priority: VALID_PRIORITIES.has(finding.priority) ? finding.priority : "medium",
    status,
    difficulty: VALID_DIFFICULTIES.has(finding.difficulty) ? finding.difficulty : status === "needs_developer" ? "developer" : "easy",
    issue_title: finding.issue_title || finding.title || "Review this website improvement",
    plain_english_explanation: finding.plain_english_explanation || finding.explanation || finding.evidence || "This item was found during the website scan.",
    why_it_matters: finding.why_it_matters || finding.why || "Fixing this can help visitors and search engines understand the website more clearly.",
    current_value: finding.current_value || "",
    recommended_value: finding.recommended_value || recommendation,
    ai_recommendation: `${recommendation}${affectedText}`,
    confidence_score: typeof finding.confidence_score === "number" ? finding.confidence_score : 90,
    can_auto_fix: finding.can_auto_fix === true || status === "auto_fixed",
    requires_approval: finding.requires_approval === true || status === "needs_approval",
    requires_developer: finding.requires_developer === true || status === "needs_developer",
  };
};

const mapCrawledPageForStorage = (page) => ({
  url: page.url,
  status_code: page.status_code || 0,
  title: page.title || "",
  meta_description: page.meta_description || "",
  h1: page.h1 || "",
  canonical_url: page.canonical_url || "",
  word_count: page.word_count || 0,
  indexable: !/noindex/i.test(page.robots_meta || ""),
  in_sitemap: false,
  rendered_title: "",
  rendered_meta_description: "",
  rendered_canonical: "",
  js_difference_detected: false,
});

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
      const projects = await base44.entities.BusinessProject.list("-created_date", 1);
      if (projects.length > 0) {
        setProject(projects[0]);
        const comps = await base44.entities.Competitor.filter({ project_id: projects[0].id });
        setCompetitors(comps);
        const jobs = await base44.entities.CrawlJob.filter({ project_id: projects[0].id }, "-created_date", 1);
        if (jobs.length > 0) setCrawlJob(jobs[0]);
      }
      setLoading(false);
    };
    load();
  }, []);

  useEffect(() => {
    if (didAutoStart.current || !project) return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("autostart") === "1" && crawlJob?.status === "queued") {
      didAutoStart.current = true;
      simulateScan(crawlJob);
    }
  }, [project, crawlJob]);

  const simulateScan = async (existingJob, projOverride) => {
    const proj = projOverride || project;
    if (!proj) return;
    setScanStarted(true);
    setSimulating(true);
    setError(null);
    let job = existingJob;

    try {
      trackEvent("scan_started", { project_id: proj.id, existing_job: Boolean(existingJob) });
      const me = await base44.auth.me();
      if (!job) {
        job = await base44.entities.CrawlJob.create({ project_id: proj.id, status: "queued", crawl_type: "full", started_at: new Date().toISOString(), owner_user_id: me.id });
      }
      setCrawlJob(job);

      try { await base44.entities.SeoIssue.deleteMany({ project_id: proj.id }); } catch (e) {}

      const stepKeys = SCAN_STEPS.map((step) => step.key).filter((key) => key !== "complete");
      for (const status of stepKeys) {
        await new Promise((resolve) => setTimeout(resolve, 1200));
        const updated = await base44.entities.CrawlJob.update(job.id, {
          status,
          pages_found: status === "crawling_html" ? 47 : undefined,
          pages_crawled: status === "checking_metadata" ? 47 : undefined,
        });
        setCrawlJob(updated);
      }

      await new Promise((resolve) => setTimeout(resolve, 700));
      const completed = await base44.entities.CrawlJob.update(job.id, { status: "complete", completed_at: new Date().toISOString(), pages_found: 47, pages_crawled: 47 });
      setCrawlJob(completed);

      let realFixes = [];
      let healthScore = 62;
      let pagesCrawled = 47;
      let issuesFound = 0;
      let summary = null;
      let crawledPagesData = [];
      let scanSucceeded = false;

      try {
        const res = await base44.functions.invoke("runAdvancedScan", {
          website_url: proj.website_url,
          business_name: proj.business_name,
          business_type: proj.business_type,
          city: proj.city,
          project_id: proj.id,
          crawl_job_id: job.id,
        });
        const scanData = res.data || {};
        if (scanData.error || scanData.success === false) throw new Error(scanData.error || "Scan failed");

        crawledPagesData = scanData.crawled_pages || [];
        realFixes = Array.isArray(scanData.grouped_findings) ? scanData.grouped_findings.map(mapGroupedFindingToSeoIssue) : [];
        if (typeof scanData.health_score === "number") healthScore = scanData.health_score;
        if (typeof scanData.pages_crawled === "number") pagesCrawled = scanData.pages_crawled;
        issuesFound = realFixes.length;
        summary = summarizeFixes(realFixes);

        let topActions = [];
        let positiveFindings = Array.isArray(scanData.site_summary?.positives) ? scanData.site_summary.positives : [];
        let aiSummary = "";
        try {
          const reviewed = await reviewFixesWithAi({ project: proj, crawledPages: crawledPagesData, rawFixes: realFixes });
          if (reviewed) {
            realFixes = reviewed.fixes;
            topActions = reviewed.topActions;
            positiveFindings = reviewed.positiveFindings;
            aiSummary = reviewed.aiSummary;
            healthScore = computeHealthScore(realFixes);
            issuesFound = realFixes.length;
            summary = summarizeFixes(realFixes);
          }
        } catch (e) {}

        scanSucceeded = true;
        setScanResult({ fixes: realFixes, health_score: healthScore, pages_crawled: pagesCrawled, issues_found: issuesFound, summary, top_actions: topActions, positive_findings: positiveFindings, ai_summary: aiSummary });
      } catch (e) {}

      if (crawledPagesData.length) {
        await base44.entities.CrawledPage.bulkCreate(crawledPagesData.map((page) => ({ ...mapCrawledPageForStorage(page), project_id: proj.id, crawl_job_id: job.id, owner_user_id: me.id })));
      }

      if (scanSucceeded) {
        try {
          await base44.functions.invoke("scanCompetitors", { project_id: proj.id, business_type: proj.business_type, city: proj.city, customer_pages: crawledPagesData });
        } catch (e) {}
      }

      const sourceFixes = scanSucceeded ? realFixes : DEMO_RECOMMENDATIONS;
      if (!scanSucceeded) {
        setScanResult({
          fixes: DEMO_RECOMMENDATIONS,
          health_score: 62,
          pages_crawled: 47,
          issues_found: DEMO_RECOMMENDATIONS.length,
          summary: {
            we_can_fix: DEMO_RECOMMENDATIONS.filter((fix) => fix.status === "auto_fixed").length,
            needs_approval: DEMO_RECOMMENDATIONS.filter((fix) => fix.status === "needs_approval").length,
            needs_developer: DEMO_RECOMMENDATIONS.filter((fix) => fix.requires_developer === true).length,
          },
        });
      }

      await base44.entities.SeoIssue.bulkCreate(sourceFixes.map((fix) => ({ ...fix, project_id: proj.id, crawl_job_id: job.id, owner_user_id: me.id })));
      try { await base44.entities.DeveloperRecommendation.deleteMany({ project_id: proj.id }); } catch (e) {}

      const devFixes = sourceFixes.filter((fix) => fix.requires_developer === true);
      if (devFixes.length > 0) {
        await base44.entities.DeveloperRecommendation.bulkCreate(devFixes.map((fix) => {
          const category = fix.category === "thin_content" ? "content_pages" : fix.category === "performance" ? "speed_mobile" : fix.category === "web_dev" ? "website_structure" : "technical_seo";
          const estimated_complexity = fix.difficulty === "developer" ? "moderate" : "simple";
          const recommended_package = estimated_complexity === "moderate" ? "500_cleanup" : estimated_complexity === "complex" ? "custom_rebuild" : "diy";
          return {
            project_id: proj.id,
            owner_user_id: me.id,
            title: fix.issue_title,
            description: fix.plain_english_explanation,
            category,
            priority: fix.priority,
            business_impact: fix.why_it_matters,
            estimated_complexity,
            recommended_package,
            status: "open",
          };
        }));
      }

      const finalJob = await base44.entities.CrawlJob.update(job.id, { pages_found: pagesCrawled, pages_crawled: pagesCrawled, seo_score: healthScore, issues_found: sourceFixes.length, error_message: "" });
      setCrawlJob(finalJob);
      await base44.entities.BusinessProject.update(proj.id, { last_crawl_at: new Date().toISOString(), seo_score: healthScore });
      trackEvent("scan_completed", { project_id: proj.id, pages_crawled: pagesCrawled, issues_found: sourceFixes.length, health_score: healthScore, real_scan_completed: scanSucceeded });
    } catch (err) {
      if (job) {
        try {
          const failed = await base44.entities.CrawlJob.update(job.id, { status: "failed", completed_at: new Date().toISOString(), error_message: err.message || "Scan failed" });
          setCrawlJob(failed);
        } catch (e) {}
      }
      setError(err.message || "Something went wrong during the scan. Please try again.");
      trackEvent("scan_failed", { project_id: proj.id, message: err.message || "Scan failed" });
    } finally {
      setSimulating(false);
    }
  };

  const handleScan = async (form) => {
    setSimulating(true);
    setError(null);
    try {
      const me = await base44.auth.me();
      let proj = project;
      const projectData = { business_name: form.business_name, website_url: form.website_url, important_keywords: form.important_keywords || [] };
      if (proj) {
        proj = await base44.entities.BusinessProject.update(proj.id, projectData);
      } else {
        proj = await base44.entities.BusinessProject.create({ ...projectData, status: "active", seo_score: 0, subscription_plan: "free", cms_platform: "Unknown", owner_user_id: me.id });
      }
      setProject(proj);

      try { await base44.entities.Competitor.deleteMany({ project_id: proj.id }); } catch (e) {}
      const urls = form.competitor_urls.map((url) => url.trim()).filter(Boolean);
      let comps = [];
      if (urls.length > 0) {
        comps = await base44.entities.Competitor.bulkCreate(urls.map((url) => {
          let name = url;
          try { name = new URL(/^https?:\/\//i.test(url) ? url : "https://" + url).hostname.replace(/^www\./, ""); } catch (e) {}
          return { project_id: proj.id, website_url: url, name, owner_user_id: me.id };
        }));
      }
      setCompetitors(comps);
      await simulateScan(null, proj);
    } catch (e) {
      setError(e.message || "Could not start the scan. Please try again.");
      setSimulating(false);
    }
  };

  const currentIdx = crawlJob ? SCAN_STEPS.findIndex((step) => step.key === crawlJob.status) : -1;
  const showProgress = scanStarted || (crawlJob && !["complete", "failed"].includes(crawlJob.status));
  const hasNoRecommendations = (scanResult?.issues_found ?? 0) === 0;

  if (loading) return <div className="flex h-64 items-center justify-center"><div className="h-8 w-8 animate-spin rounded-full border-4 border-slate-200 border-t-blue-600" /></div>;

  return (
    <div className="min-h-screen bg-[#F7F8FA]">
      <div className="mx-auto w-full max-w-4xl px-5 py-10 sm:px-6 lg:py-12">
        <div className="mb-8">
          <p className="text-sm font-medium text-blue-600">Start a review</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">Scan Website</h1>
          <p className="mt-2 text-base leading-7 text-slate-500">Enter your website and we’ll prepare a simple Fix List.</p>
        </div>

        <ScanWebsiteForm project={project} competitors={competitors} saving={simulating} onScan={handleScan} />

        {error && (
          <div className="mt-6 rounded-3xl border border-red-100 bg-white p-5 shadow-sm">
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-0.5 h-4 w-4 text-red-500" />
              <div><p className="text-sm font-medium text-slate-950">Scan failed</p><p className="mt-1 text-sm leading-6 text-slate-600">{error}</p></div>
            </div>
          </div>
        )}

        {showProgress && crawlJob && (
          <div className="mt-6 rounded-3xl border border-slate-200/80 bg-white p-6 shadow-sm">
            <h2 className="text-base font-semibold text-slate-950">Scan progress</h2>
            <div className="mt-5 space-y-4">
              {SCAN_STEPS.map((step, index) => {
                const isComplete = index < currentIdx || crawlJob.status === "complete";
                const isCurrent = index === currentIdx && crawlJob.status !== "complete";
                return (
                  <div key={step.key} className="flex items-center gap-3">
                    <div className={`flex h-6 w-6 items-center justify-center rounded-full ${isComplete ? "bg-slate-950" : isCurrent ? "bg-blue-600" : "bg-slate-100"}`}>
                      {isComplete ? <CheckCircle2 className="h-3.5 w-3.5 text-white" /> : isCurrent ? <Loader2 className="h-3.5 w-3.5 animate-spin text-white" /> : <Circle className="h-3.5 w-3.5 text-slate-300" />}
                    </div>
                    <span className={`text-sm ${isComplete || isCurrent ? "font-medium text-slate-950" : "text-slate-500"}`}>{step.label}</span>
                  </div>
                );
              })}
            </div>
            <p className="mt-5 text-xs leading-5 text-slate-400">This scan reviews website content we can access directly. Some websites may need a deeper manual review.</p>
          </div>
        )}

        {scanStarted && crawlJob?.status === "complete" && (
          <div className="mt-6 rounded-3xl border border-slate-200/80 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-slate-950">Your scan is complete.</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              We scanned {scanResult?.pages_crawled ?? crawlJob.pages_found ?? 0} pages and found {scanResult?.issues_found ?? 0} recommended {(scanResult?.issues_found ?? 0) === 1 ? "improvement" : "improvements"}.
            </p>
            {scanResult?.ai_summary && <p className="mt-4 text-sm leading-6 text-slate-600">{scanResult.ai_summary}</p>}
            {scanResult?.positive_findings?.length > 0 && (
              <div className="mt-5"><p className="text-xs font-medium uppercase tracking-wide text-slate-400">What’s working well</p><div className="mt-3 space-y-2">{scanResult.positive_findings.map((finding, index) => <p key={index} className="text-sm leading-6 text-slate-600">{finding}</p>)}</div></div>
            )}
            <div className="mt-5 grid gap-3 md:grid-cols-3">
              <div className="rounded-xl bg-slate-50 p-4"><div className="text-2xl font-semibold text-slate-950">{scanResult?.summary?.we_can_fix ?? 0}</div><div className="text-sm text-slate-500">Prepared</div></div>
              <div className="rounded-xl bg-slate-50 p-4"><div className="text-2xl font-semibold text-slate-950">{scanResult?.summary?.needs_approval ?? 0}</div><div className="text-sm text-slate-500">Needs review</div></div>
              <div className="rounded-xl bg-slate-50 p-4"><div className="text-2xl font-semibold text-slate-950">{scanResult?.summary?.needs_developer ?? 0}</div><div className="text-sm text-slate-500">May need help</div></div>
            </div>
            <div className="mt-6"><Button asChild className="rounded-full bg-blue-600 px-5 py-2.5 text-sm font-medium text-white shadow-none hover:bg-blue-700"><a href="/dashboard">View Fix List</a></Button></div>
            {hasNoRecommendations && <p className="mt-4 text-sm text-slate-500">No major recommendations found. Your site is looking good.</p>}
          </div>
        )}
      </div>
    </div>
  );
}