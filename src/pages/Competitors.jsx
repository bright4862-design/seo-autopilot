import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { base44 } from "@/api/base44Client";
import { Button } from "@/components/ui/button";
import { computeCustomerMetrics } from "@/lib/competitorMetrics";
import ComparisonTable from "@/components/competitors/ComparisonTable";
import GapInsights from "@/components/competitors/GapInsights";
import { Loader2 } from "lucide-react";

const INSIGHT_CATEGORY = {
  "Competitors have more dedicated service pages": "content_pages",
  "Competitors use clearer search titles": "cms_seo_setup",
  "Competitors have better search descriptions": "cms_seo_setup",
  "Competitors may answer more customer questions": "content_pages",
  "Your site has more broken pages": "technical_seo",
};

export default function Competitors() {
  const [competitors, setCompetitors] = useState([]);
  const [insights, setInsights] = useState([]);
  const [customer, setCustomer] = useState(null);
  const [project, setProject] = useState(null);
  const [loading, setLoading] = useState(true);
  const [creatingPlan, setCreatingPlan] = useState(false);
  const [planCreated, setPlanCreated] = useState(false);

  useEffect(() => {
    const load = async () => {
      const projects = await base44.entities.BusinessProject.list("-created_date", 1);
      if (projects.length > 0) {
        const proj = projects[0];
        setProject(proj);
        const [comps, ins, jobs] = await Promise.all([
          base44.entities.Competitor.filter({ project_id: proj.id }),
          base44.entities.CompetitorInsight.filter({ project_id: proj.id }),
          base44.entities.CrawlJob.filter({ project_id: proj.id, status: "complete" }, "-created_date", 1),
        ]);
        setCompetitors(comps);
        setInsights(ins);
        if (jobs.length > 0) {
          const pages = await base44.entities.CrawledPage.filter({ crawl_job_id: jobs[0].id });
          setCustomer(computeCustomerMetrics(pages, proj.business_type, proj.city));
        }
      }
      setLoading(false);
    };
    load();
  }, []);

  const createImprovementPlan = async () => {
    if (!project || insights.length === 0) return;
    setCreatingPlan(true);
    const me = await base44.auth.me();
    const existing = await base44.entities.DeveloperRecommendation.filter({ project_id: project.id });
    const existingTitles = new Set(existing.map((rec) => rec.title));
    const newRecs = insights.filter((insight) => !existingTitles.has(insight.insight_title)).map((insight) => ({
      project_id: project.id,
      owner_user_id: me.id,
      title: insight.insight_title,
      description: insight.explanation,
      category: INSIGHT_CATEGORY[insight.insight_title] || "technical_seo",
      priority: insight.impact === "high" ? "high" : insight.impact === "low" ? "low" : "medium",
      business_impact: insight.recommended_action,
      estimated_complexity: "moderate",
      recommended_package: "diy",
      status: "open",
    }));
    if (newRecs.length > 0) await base44.entities.DeveloperRecommendation.bulkCreate(newRecs);
    setCreatingPlan(false);
    setPlanCreated(true);
  };

  if (loading) return <div className="flex h-64 items-center justify-center"><div className="h-8 w-8 animate-spin rounded-full border-4 border-slate-200 border-t-blue-600" /></div>;

  const scanned = competitors.filter((c) => (c.title_quality_score || 0) > 0 || (c.meta_coverage_pct || 0) > 0 || (c.content_depth_score || 0) > 0);
  const hasData = scanned.length > 0 && customer;

  return (
    <div className="min-h-screen bg-[#F7F8FA]">
      <div className="mx-auto w-full max-w-4xl px-5 py-10 sm:px-6 lg:py-12">
        <div className="mb-8 flex flex-col items-start justify-between gap-5 sm:flex-row">
          <div>
            <p className="text-sm font-medium text-blue-600">Competitor view</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">Competitor Gaps</h1>
            <p className="mt-2 text-base leading-7 text-slate-500">See where similar pages may be clearer or more helpful.</p>
          </div>
          <Button asChild className="rounded-full bg-blue-600 px-5 text-sm font-medium text-white shadow-none hover:bg-blue-700"><Link to="/crawl-status">Add competitors</Link></Button>
        </div>

        {planCreated && <div className="mb-6 rounded-2xl border border-slate-200/80 bg-white px-5 py-4 text-sm text-slate-600 shadow-sm">Added to your improvement plan.</div>}

        {competitors.length === 0 || !hasData ? (
          <div className="rounded-3xl border border-slate-200/80 bg-white p-10 text-center shadow-sm">
            <h2 className="text-lg font-semibold text-slate-950">No competitor gaps yet</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">Add competitor pages during your next scan to see where other sites may be stronger.</p>
            <Button asChild className="mt-6 rounded-full bg-blue-600 px-5 text-sm font-medium text-white shadow-none hover:bg-blue-700"><Link to="/crawl-status">Scan Website</Link></Button>
          </div>
        ) : (
          <div className="space-y-7">
            {insights.length > 0 ? <GapInsights insights={insights} onCreatePlan={createImprovementPlan} creatingPlan={creatingPlan} /> : <div className="rounded-3xl border border-slate-200/80 bg-white p-6 shadow-sm"><p className="text-sm leading-6 text-slate-600">Good news — your site holds up well against these competitors.</p></div>}
            {creatingPlan && <div className="flex items-center gap-2 text-sm text-slate-500"><Loader2 className="h-4 w-4 animate-spin" /> Creating improvement plan…</div>}
            <ComparisonTable customer={customer} competitors={scanned} />
          </div>
        )}
      </div>
    </div>
  );
}