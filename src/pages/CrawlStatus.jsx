import React, { useState, useEffect, useRef } from "react";
import { base44 } from "@/api/base44Client";
import { Button } from "@/components/ui/button";
import {
  Search, FileText, Code, Globe, ArrowRightLeft, BarChart3,
  Zap, CheckCircle2, Loader2, Circle, Clock, AlertTriangle
} from "lucide-react";

const CRAWL_STEPS = [
  { key: "queued", label: "Queued", icon: Clock, desc: "Your crawl is in the queue" },
  { key: "crawling_html", label: "Crawling HTML", icon: Search, desc: "Scanning all pages on your site" },
  { key: "rendering_js", label: "Rendering JavaScript", icon: Code, desc: "Loading JavaScript-heavy pages" },
  { key: "checking_metadata", label: "Checking Metadata", icon: FileText, desc: "Reviewing titles and descriptions" },
  { key: "checking_canonicals", label: "Checking Canonicals", icon: Globe, desc: "Verifying canonical tags" },
  { key: "checking_sitemap", label: "Checking Sitemap", icon: Globe, desc: "Validating your sitemap" },
  { key: "checking_redirects", label: "Checking Redirects & 404s", icon: ArrowRightLeft, desc: "Finding broken pages and redirect chains" },
  { key: "benchmarking_competitors", label: "Benchmarking Competitors", icon: BarChart3, desc: "Comparing your site to competitors" },
  { key: "generating_recommendations", label: "Generating AI Recommendations", icon: Zap, desc: "Creating personalized fixes" },
  { key: "complete", label: "Complete", icon: CheckCircle2, desc: "Your scan results are ready!" },
];

const SCAN_ISSUES = [
  {
    page_url: "/services", category: "meta_title", priority: "high", status: "auto_fixed",
    issue_title: "Missing page title on Services page",
    plain_english_explanation: "Your Services page didn't have a title tag. We generated one for you.",
    why_it_matters: "Page titles are the first thing people see in Google. Without one, Google guesses — usually poorly.",
    current_value: "(empty)", recommended_value: "Plumbing & HVAC Services | Sunshine Plumbing Denver",
    ai_recommendation: "We auto-generated a title using your business name and services.",
    confidence_score: 92, can_auto_fix: true, requires_approval: false, requires_developer: false,
  },
  {
    page_url: "/blog/tips", category: "internal_link", priority: "low", status: "auto_fixed",
    issue_title: "Broken internal link to removed blog post",
    plain_english_explanation: "This page linked to a blog post that no longer exists. We removed the broken link.",
    why_it_matters: "Broken links make your site look unmaintained and waste Google's time.",
    current_value: "Link to /blog/summer-tips-2024 (404)", recommended_value: "Link removed",
    ai_recommendation: "We removed the broken link automatically.",
    confidence_score: 80, can_auto_fix: true, requires_approval: false, requires_developer: false,
  },
  {
    page_url: "/about", category: "meta_description", priority: "medium", status: "needs_approval",
    issue_title: "Missing description on About page",
    plain_english_explanation: "Your About page has no meta description — the short summary shown under your title in Google.",
    why_it_matters: "A good description convinces people to click your result over a competitor's.",
    current_value: "(empty)", recommended_value: "Sunshine Plumbing has served Denver for 15+ years. Licensed, insured, ready to help.",
    ai_recommendation: "We wrote a description highlighting your experience and service area — approve it to apply.",
    confidence_score: 85, can_auto_fix: false, requires_approval: true, requires_developer: false,
  },
  {
    page_url: "/old-summer-promo", category: "404_error", priority: "critical", status: "needs_approval",
    issue_title: "Broken page returning an error",
    plain_english_explanation: "This page no longer exists but people (and Google) still try to visit it.",
    why_it_matters: "Broken pages frustrate visitors and waste your SEO value.",
    current_value: "404 error", recommended_value: "Redirect to /services",
    ai_recommendation: "We can set up a redirect from this old page to your services page — just approve it.",
    confidence_score: 90, can_auto_fix: false, requires_approval: true, requires_developer: false,
  },
  {
    page_url: "/water-heater-repair", category: "canonical", priority: "medium", status: "needs_approval",
    issue_title: "Canonical tag points to a different URL version",
    plain_english_explanation: "This page's canonical tag points to a URL with a trailing slash, but the real URL doesn't have one.",
    why_it_matters: "When Google sees two versions of a page, it may split your ranking power between them.",
    current_value: ".../water-heater-repair/", recommended_value: ".../water-heater-repair",
    ai_recommendation: "We can update the canonical tag to match — approve and we'll apply it.",
    confidence_score: 95, can_auto_fix: false, requires_approval: true, requires_developer: false,
  },
  {
    page_url: "/drain-cleaning", category: "thin_content", priority: "high", status: "needs_developer",
    issue_title: "Very little content on service page",
    plain_english_explanation: "This page only has 87 words — not enough for Google to understand or rank it well.",
    why_it_matters: "Pages with little content rarely rank. Your competitors' similar pages have 500-1,200 words.",
    current_value: "87 words", recommended_value: "500+ words with service details & FAQ",
    ai_recommendation: "A developer or writer should expand this page with service details and FAQs.",
    confidence_score: 88, can_auto_fix: false, requires_approval: false, requires_developer: true,
  },
  {
    page_url: "/contact", category: "schema", priority: "medium", status: "needs_developer",
    issue_title: "Missing business details for Google",
    plain_english_explanation: "Your contact page doesn't tell Google your business name, address, phone, and hours in a format it understands.",
    why_it_matters: "This helps Google show your phone number and hours directly in search results.",
    current_value: "Not found", recommended_value: "Add LocalBusiness schema",
    ai_recommendation: "A developer should add LocalBusiness schema markup to your contact page.",
    confidence_score: 95, can_auto_fix: false, requires_approval: false, requires_developer: true,
  },
  {
    page_url: "/", category: "performance", priority: "medium", status: "needs_developer",
    issue_title: "Homepage loads slowly on mobile",
    plain_english_explanation: "Your homepage takes over 5 seconds to load on mobile. Most visitors leave after 3.",
    why_it_matters: "Google uses page speed as a ranking factor, and slow pages lose customers.",
    current_value: "5.2s load time", recommended_value: "Under 3 seconds",
    ai_recommendation: "A developer should optimize images and reduce JavaScript.",
    confidence_score: 78, can_auto_fix: false, requires_approval: false, requires_developer: true,
  },
];

export default function CrawlStatus() {
  const [crawlJob, setCrawlJob] = useState(null);
  const [project, setProject] = useState(null);
  const [loading, setLoading] = useState(true);
  const [simulating, setSimulating] = useState(false);
  const [error, setError] = useState(null);
  const didAutoStart = useRef(false);

  useEffect(() => {
    const load = async () => {
      const projects = await base44.entities.BusinessProject.list("-created_date", 1);
      if (projects.length > 0) {
        setProject(projects[0]);
        const jobs = await base44.entities.CrawlJob.filter({ project_id: projects[0].id }, "-created_date", 1);
        if (jobs.length > 0) setCrawlJob(jobs[0]);
      }
      setLoading(false);
    };
    load();
  }, []);

  useEffect(() => {
    if (didAutoStart.current) return;
    if (!project) return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("autostart") !== "1") return;
    if (crawlJob?.status === "queued") {
      didAutoStart.current = true;
      simulateCrawl(crawlJob);
    }
  }, [project, crawlJob]);

  const simulateCrawl = async (existingJob) => {
    if (!project) return;
    setSimulating(true);
    setError(null);
    try {
      let job = existingJob;
      if (!job) {
        job = await base44.entities.CrawlJob.create({
          project_id: project.id,
          status: "queued",
          crawl_type: "full",
          started_at: new Date().toISOString(),
        });
      }
      setCrawlJob(job);

      // Start each scan with a clean Fix List
      try { await base44.entities.SeoIssue.deleteMany({ project_id: project.id }); } catch (e) {}

      const steps = CRAWL_STEPS.map(s => s.key).filter(k => k !== "complete");
      for (const status of steps) {
        await new Promise(r => setTimeout(r, 1500));
        const updated = await base44.entities.CrawlJob.update(job.id, {
          status,
          pages_found: status === "crawling_html" ? 47 : undefined,
          pages_crawled: status === "checking_metadata" ? 47 : undefined,
          js_pages_rendered: status === "checking_canonicals" ? 12 : undefined,
        });
        setCrawlJob(updated);
      }

      await new Promise(r => setTimeout(r, 1000));
      const completed = await base44.entities.CrawlJob.update(job.id, {
        status: "complete",
        completed_at: new Date().toISOString(),
        pages_found: 47,
        pages_crawled: 47,
        js_pages_rendered: 12,
      });
      setCrawlJob(completed);

      // Turn the findings into simple fixes on the Fix List
      await base44.entities.SeoIssue.bulkCreate(
        SCAN_ISSUES.map(i => ({ ...i, project_id: project.id, crawl_job_id: job.id }))
      );

      await base44.entities.BusinessProject.update(project.id, {
        last_crawl_at: new Date().toISOString(),
        seo_score: 62,
      });
    } catch (err) {
      console.error("Crawl simulation failed", err);
      setError(err.message || "Something went wrong during the crawl. Please try again.");
    } finally {
      setSimulating(false);
    }
  };

  const currentIdx = crawlJob ? CRAWL_STEPS.findIndex(s => s.key === crawlJob.status) : -1;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
      </div>
    );
  }

  if (!project) {
    return (
      <div className="max-w-2xl mx-auto">
        <div className="bg-white rounded-2xl border border-gray-100 p-10 text-center">
          <Search className="w-10 h-10 text-gray-300 mx-auto mb-3" />
          <h3 className="font-semibold text-gray-800 mb-1">No project set up yet</h3>
          <p className="text-sm text-gray-500 mb-5">Add your business website first to start an SEO scan.</p>
          <a href="/onboarding"><Button className="gradient-primary text-white border-0">Set Up Project</Button></a>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Crawl Status</h1>
          <p className="text-sm text-gray-500 mt-1">Track your website scan progress</p>
        </div>
        <Button onClick={() => simulateCrawl()} disabled={simulating} className="gradient-primary text-white border-0">
          {simulating ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Search className="w-4 h-4 mr-2" />}
          {simulating ? "Scanning..." : crawlJob?.status === "complete" ? "Run New Scan" : "Scan My Website"}
        </Button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-100 rounded-xl p-4 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-red-800">Crawl failed</p>
            <p className="text-xs text-red-600 mt-0.5">{error}</p>
          </div>
        </div>
      )}

      {/* Progress */}
      <div className="bg-white rounded-2xl border border-gray-100 p-6">
        <div className="space-y-0">
          {CRAWL_STEPS.map((step, i) => {
            const isComplete = i < currentIdx;
            const isCurrent = i === currentIdx;
            const isPending = i > currentIdx;

            return (
              <div key={step.key} className="flex gap-4">
                <div className="flex flex-col items-center">
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${isComplete ? "bg-green-100" : isCurrent ? "bg-blue-100" : "bg-gray-100"}`}>
                    {isComplete ? (
                      <CheckCircle2 className="w-4 h-4 text-green-600" />
                    ) : isCurrent ? (
                      <Loader2 className="w-4 h-4 text-blue-600 animate-spin" />
                    ) : (
                      <Circle className="w-4 h-4 text-gray-300" />
                    )}
                  </div>
                  {i < CRAWL_STEPS.length - 1 && (
                    <div className={`w-0.5 h-8 ${isComplete ? "bg-green-200" : "bg-gray-200"}`} />
                  )}
                </div>
                <div className="pb-8">
                  <p className={`text-sm font-medium ${isComplete ? "text-green-700" : isCurrent ? "text-blue-700" : "text-gray-400"}`}>
                    {step.label}
                  </p>
                  <p className={`text-xs mt-0.5 ${isCurrent ? "text-blue-500" : "text-gray-400"}`}>
                    {step.desc}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Stats when complete */}
      {crawlJob?.status === "complete" && (
        <div className="bg-green-50 border border-green-100 rounded-xl p-5 text-center">
          <CheckCircle2 className="w-10 h-10 text-green-500 mx-auto mb-3" />
          <h3 className="font-bold text-green-900 text-lg mb-1">Scan Complete!</h3>
          <p className="text-sm text-green-700 mb-4">We found {crawlJob.pages_found} pages and rendered {crawlJob.js_pages_rendered} JavaScript pages.</p>
          <div className="flex justify-center gap-3">
            <a href="/dashboard"><Button size="sm" className="gradient-primary text-white border-0">View Fix List</Button></a>
          </div>
        </div>
      )}
    </div>
  );
}