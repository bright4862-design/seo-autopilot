import React, { useState, useEffect } from "react";
import { base44 } from "@/api/base44Client";
import { Button } from "@/components/ui/button";
import { computeCustomerMetrics } from "@/lib/competitorMetrics";
import ComparisonTable from "@/components/competitors/ComparisonTable";
import GapInsights from "@/components/competitors/GapInsights";
import { Users, ClipboardList, Loader2, CheckCircle2 } from "lucide-react";

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
    const existingTitles = new Set(existing.map(r => r.title));
    const newRecs = insights
      .filter(i => !existingTitles.has(i.insight_title))
      .map(i => ({
        project_id: project.id,
        owner_user_id: me.id,
        title: i.insight_title,
        description: i.explanation,
        category: INSIGHT_CATEGORY[i.insight_title] || "technical_seo",
        priority: i.impact === "high" ? "high" : i.impact === "low" ? "low" : "medium",
        business_impact: i.recommended_action,
        estimated_complexity: "moderate",
        recommended_package: "diy",
        status: "open",
      }));
    if (newRecs.length > 0) {
      await base44.entities.DeveloperRecommendation.bulkCreate(newRecs);
    }
    setCreatingPlan(false);
    setPlanCreated(true);
  };

  if (loading) return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" /></div>;

  const scanned = competitors.filter(c => (c.title_quality_score || 0) > 0 || (c.meta_coverage_pct || 0) > 0 || (c.content_depth_score || 0) > 0);
  const hasData = scanned.length > 0 && customer;

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Competitor Comparison</h1>
          <p className="text-sm text-gray-500 mt-1">See how your site compares — in plain English</p>
        </div>
        {hasData && insights.length > 0 && (
          planCreated ? (
            <div className="flex items-center gap-2 text-sm text-green-700 bg-green-50 border border-green-100 rounded-lg px-4 py-2">
              <CheckCircle2 className="w-4 h-4" /> Added to your improvement plan
            </div>
          ) : (
            <Button onClick={createImprovementPlan} disabled={creatingPlan} className="gradient-primary text-white border-0">
              {creatingPlan ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <ClipboardList className="w-4 h-4 mr-2" />}
              Create improvement plan
            </Button>
          )
        )}
      </div>

      {competitors.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-100 p-12 text-center">
          <Users className="w-10 h-10 text-gray-300 mx-auto mb-3" />
          <p className="font-medium text-gray-600">No competitors added yet</p>
          <p className="text-sm text-gray-400 mt-1">Add competitor websites when setting up a scan to see how you compare.</p>
        </div>
      ) : !hasData ? (
        <div className="bg-white rounded-xl border border-gray-100 p-12 text-center">
          <Users className="w-10 h-10 text-gray-300 mx-auto mb-3" />
          <p className="font-medium text-gray-600">Competitor comparison not ready yet</p>
          <p className="text-sm text-gray-400 mt-1">Run a scan and we'll compare your site to your competitors automatically.</p>
        </div>
      ) : (
        <>
          {/* Summary */}
          <div className="bg-white rounded-xl border border-gray-100 p-6">
            <p className="text-sm text-gray-700 leading-relaxed">
              We compared your website to <span className="font-semibold">{scanned.length} competitor {scanned.length === 1 ? "site" : "sites"}</span>
              {" "}({scanned.map(c => c.name || c.website_url).join(", ")}).
              {insights.length > 0
                ? ` We found ${insights.length} ${insights.length === 1 ? "area" : "areas"} where competitors look stronger — the details and next steps are below.`
                : " Good news — your site holds up well against these competitors."}
            </p>
          </div>

          {insights.length > 0 && <GapInsights insights={insights} />}

          <ComparisonTable customer={customer} competitors={scanned} />
        </>
      )}
    </div>
  );
}