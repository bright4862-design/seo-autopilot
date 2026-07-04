import React, { useState, useEffect } from "react";
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

export default function CrawlStatus() {
  const [crawlJob, setCrawlJob] = useState(null);
  const [project, setProject] = useState(null);
  const [loading, setLoading] = useState(true);
  const [simulating, setSimulating] = useState(false);
  const [error, setError] = useState(null);

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

  const simulateCrawl = async () => {
    if (!project) return;
    setSimulating(true);
    setError(null);
    try {
      const job = await base44.entities.CrawlJob.create({
        project_id: project.id,
        status: "queued",
        crawl_type: "full",
        started_at: new Date().toISOString(),
      });
      setCrawlJob(job);

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
        <Button onClick={simulateCrawl} disabled={simulating} className="gradient-primary text-white border-0">
          {simulating ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Search className="w-4 h-4 mr-2" />}
          {simulating ? "Scanning..." : crawlJob ? "Run New Crawl" : "Start Crawl"}
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
            <a href="/dashboard"><Button size="sm" className="gradient-primary text-white border-0">View Dashboard</Button></a>
            <a href="/issues"><Button size="sm" variant="outline">See Issues</Button></a>
          </div>
        </div>
      )}
    </div>
  );
}