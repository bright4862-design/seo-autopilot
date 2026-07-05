import React, { useEffect, useState } from "react";
import { base44 } from "@/api/base44Client";
import { Button } from "@/components/ui/button";
import { exportScanReportPdf } from "@/lib/exportScanReport";
import { customerText } from "@/lib/friendlyLabels";
import { Download, Loader2 } from "lucide-react";

export default function Reports() {
  const [reports, setReports] = useState([]);
  const [project, setProject] = useState(null);
  const [issues, setIssues] = useState([]);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);

  const handleExport = async () => {
    if (!project) return;
    setExporting(true);
    try {
      const [jobs, devRecs, insights] = await Promise.all([
        base44.entities.CrawlJob.filter({ project_id: project.id, status: "complete" }, "-created_date", 1),
        base44.entities.DeveloperRecommendation.filter({ project_id: project.id }),
        base44.entities.CompetitorInsight.filter({ project_id: project.id }),
      ]);
      exportScanReportPdf({ project, crawlJob: jobs[0], issues, devRecs, insights });
    } finally {
      setExporting(false);
    }
  };

  useEffect(() => {
    const load = async () => {
      const projects = await base44.entities.BusinessProject.list("-created_date", 1);
      if (projects.length > 0) {
        setProject(projects[0]);
        const [reps, iss] = await Promise.all([
          base44.entities.Report.filter({ project_id: projects[0].id }),
          base44.entities.SeoIssue.filter({ project_id: projects[0].id }),
        ]);
        setReports(reps);
        setIssues(iss);
      }
      setLoading(false);
    };
    load();
  }, []);

  const generateReport = async () => {
    if (!project) return;
    const prepared = issues.filter((item) => item.status === "auto_fixed" || item.status === "completed").length;
    const review = issues.filter((item) => item.status === "needs_approval").length;
    const help = issues.filter((item) => item.status === "needs_developer").length;
    const user = await base44.auth.me();
    const report = await base44.entities.Report.create({
      project_id: project.id,
      owner_user_id: user.id,
      summary: `The scan of ${project.website_url} prepared ${issues.length} recommendations. ${prepared} are ready to review, ${review} need your approval, and ${help} may need help from a website editor or developer.`,
      fixed_count: prepared,
      approval_count: review,
      developer_count: help,
      seo_score: project.seo_score || 62,
      competitor_summary: "Competitor gaps may show opportunities for clearer service pages, search titles, descriptions, and trust signals.",
      next_steps: "1. Review the Fix List\n2. Approve recommendations that match your business\n3. Request help for larger website improvements\n4. Add competitor pages during your next scan",
    });
    setReports((prev) => [report, ...prev]);
  };

  if (loading) return <div className="flex h-64 items-center justify-center"><div className="h-8 w-8 animate-spin rounded-full border-4 border-slate-200 border-t-blue-600" /></div>;

  return (
    <div className="min-h-screen bg-[#F7F8FA]">
      <div className="mx-auto w-full max-w-5xl px-6 py-10">
        <div className="mb-8 flex flex-col items-start justify-between gap-6 sm:flex-row">
          <div><h1 className="text-3xl font-semibold tracking-tight text-slate-950">Scan Report</h1><p className="mt-2 text-base text-slate-500">A plain-English summary of your website scan.</p></div>
          <div className="flex gap-3">
            <Button onClick={handleExport} disabled={!project || exporting} className="rounded-full bg-blue-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-blue-700">
              {exporting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Download className="mr-2 h-4 w-4" />}
              Export report
            </Button>
            <Button onClick={generateReport} variant="outline" className="rounded-full border border-slate-200 bg-white px-5 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50">Generate summary</Button>
          </div>
        </div>

        {reports.length === 0 ? (
          <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center shadow-sm">
            <h2 className="text-lg font-semibold text-slate-950">No report yet</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">Generate a simple summary after your scan.</p>
            <Button onClick={generateReport} className="mt-6 rounded-full bg-blue-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-blue-700">Generate summary</Button>
          </div>
        ) : (
          <div className="space-y-6">
            {reports.map((report) => (
              <article key={report.id} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                <div className="mb-6 flex flex-col justify-between gap-3 border-b border-slate-100 pb-5 sm:flex-row sm:items-start">
                  <div>
                    <h2 className="text-xl font-semibold tracking-tight text-slate-950">{project?.business_name || "Website"} scan summary</h2>
                    <p className="mt-1 text-sm text-slate-500">Generated {new Date(report.created_date).toLocaleDateString()}</p>
                  </div>
                  {report.seo_score > 0 && <p className="rounded-full bg-slate-100 px-3 py-1 text-sm font-medium text-slate-600">Score {report.seo_score}</p>}
                </div>

                <div className="grid gap-5">
                  <section><h3 className="text-sm font-semibold text-slate-950">Summary</h3><p className="mt-2 text-sm leading-6 text-slate-600">{customerText(report.summary)}</p></section>
                  <section><h3 className="text-sm font-semibold text-slate-950">What to review</h3><p className="mt-2 text-sm leading-6 text-slate-600">{report.approval_count || 0} recommendations need review. {report.fixed_count || 0} are prepared.</p></section>
                  <section><h3 className="text-sm font-semibold text-slate-950">Website improvements</h3><p className="mt-2 text-sm leading-6 text-slate-600">{report.developer_count || 0} recommendations may need help.</p></section>
                  {report.competitor_summary && <section><h3 className="text-sm font-semibold text-slate-950">Competitor gaps</h3><p className="mt-2 text-sm leading-6 text-slate-600">{customerText(report.competitor_summary)}</p></section>}
                  {report.next_steps && <section><h3 className="text-sm font-semibold text-slate-950">Next steps</h3><div className="mt-2 space-y-2">{customerText(report.next_steps).split("\n").map((step, index) => <p key={index} className="text-sm leading-6 text-slate-600">{step}</p>)}</div></section>}
                </div>

                <div className="mt-6 border-t border-slate-100 pt-5">
                  <Button variant="outline" onClick={handleExport} disabled={exporting} className="rounded-full border border-slate-200 bg-white px-5 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50">Export report</Button>
                </div>
              </article>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}