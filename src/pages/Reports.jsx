import React, { useEffect, useState } from "react";
import { base44 } from "@/api/base44Client";
import { Button } from "@/components/ui/button";
import { exportScanReportPdf } from "@/lib/exportScanReport";
import { customerText } from "@/lib/friendlyLabels";
import { Loader2 } from "lucide-react";

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
      <div className="mx-auto w-full max-w-4xl px-5 py-10 sm:px-6 lg:py-12">
        <div className="mb-8 flex flex-col items-start justify-between gap-5 sm:flex-row">
          <div>
            <p className="text-sm font-medium text-blue-600">Plain-English summary</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">Scan Report</h1>
            <p className="mt-2 text-base leading-7 text-slate-500">A simple summary you can save or share.</p>
          </div>
          <div className="flex gap-3">
            <Button onClick={handleExport} disabled={!project || exporting} className="rounded-full bg-blue-600 px-5 text-sm font-medium text-white shadow-none hover:bg-blue-700">
              {exporting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Export report
            </Button>
            <Button onClick={generateReport} variant="outline" className="rounded-full border-slate-200 bg-white px-5 text-sm font-medium text-slate-700 shadow-none hover:bg-slate-50">Generate summary</Button>
          </div>
        </div>

        {reports.length === 0 ? (
          <div className="rounded-3xl border border-slate-200/80 bg-white p-10 text-center shadow-sm">
            <h2 className="text-lg font-semibold text-slate-950">No report yet</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">Generate a simple summary after your scan.</p>
            <Button onClick={generateReport} className="mt-6 rounded-full bg-blue-600 px-5 text-sm font-medium text-white shadow-none hover:bg-blue-700">Generate summary</Button>
          </div>
        ) : (
          <div className="space-y-7">
            {reports.map((report) => (
              <article key={report.id} className="overflow-hidden rounded-3xl border border-slate-200/80 bg-white shadow-sm">
                <div className="border-b border-slate-100 px-5 py-5 sm:px-6">
                  <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
                    <div>
                      <h2 className="text-xl font-semibold tracking-tight text-slate-950">{project?.business_name || "Website"} scan summary</h2>
                      <p className="mt-1 text-sm text-slate-500">Generated {new Date(report.created_date).toLocaleDateString()}</p>
                    </div>
                    {report.seo_score > 0 && <p className="text-sm font-medium text-slate-500">Score {report.seo_score}</p>}
                  </div>
                </div>

                <div className="divide-y divide-slate-100">
                  <section className="px-5 py-5 sm:px-6"><h3 className="text-sm font-semibold text-slate-950">Summary</h3><p className="mt-2 text-sm leading-6 text-slate-600">{customerText(report.summary)}</p></section>
                  <section className="px-5 py-5 sm:px-6"><h3 className="text-sm font-semibold text-slate-950">What to review</h3><p className="mt-2 text-sm leading-6 text-slate-600">{report.approval_count || 0} recommendations need review. {report.fixed_count || 0} are prepared.</p></section>
                  <section className="px-5 py-5 sm:px-6"><h3 className="text-sm font-semibold text-slate-950">Website improvements</h3><p className="mt-2 text-sm leading-6 text-slate-600">{report.developer_count || 0} recommendations may need help.</p></section>
                  {report.competitor_summary && <section className="px-5 py-5 sm:px-6"><h3 className="text-sm font-semibold text-slate-950">Competitor gaps</h3><p className="mt-2 text-sm leading-6 text-slate-600">{customerText(report.competitor_summary)}</p></section>}
                  {report.next_steps && <section className="px-5 py-5 sm:px-6"><h3 className="text-sm font-semibold text-slate-950">Next steps</h3><div className="mt-2 space-y-2">{customerText(report.next_steps).split("\n").map((step, index) => <p key={index} className="text-sm leading-6 text-slate-600">{step}</p>)}</div></section>}
                </div>

                <div className="flex justify-end bg-slate-50/70 px-5 py-4 sm:px-6">
                  <Button variant="outline" onClick={handleExport} disabled={exporting} className="rounded-full border-slate-200 bg-white px-5 text-sm font-medium text-slate-700 shadow-none hover:bg-slate-50">Export report</Button>
                </div>
              </article>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}