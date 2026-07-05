import React, { useState, useEffect } from "react";
import { base44 } from "@/api/base44Client";
import { Button } from "@/components/ui/button";
import { FileText, Download, CheckCircle2, Clock, Wrench, BarChart3, ArrowRight } from "lucide-react";

export default function Reports() {
  const [reports, setReports] = useState([]);
  const [project, setProject] = useState(null);
  const [issues, setIssues] = useState([]);
  const [loading, setLoading] = useState(true);

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
    const fixed = issues.filter(i => i.status === "auto_fixed" || i.status === "completed").length;
    const approval = issues.filter(i => i.status === "needs_approval").length;
    const dev = issues.filter(i => i.status === "needs_developer").length;

    const user = await base44.auth.me();
    const report = await base44.entities.Report.create({
      project_id: project.id,
      owner_user_id: user.id,
      summary: `SEO scan of ${project.website_url} found ${issues.length} total issues. ${fixed} simple fixes were prepared for review, ${approval} need your review, and ${dev} require developer work.`,
      fixed_count: fixed,
      approval_count: approval,
      developer_count: dev,
      seo_score: project.seo_score || 62,
      competitor_summary: "Your site trails top competitors in service page count, title tag quality, and schema markup usage. See the Competitor Benchmark page for detailed gaps.",
      next_steps: "1. Review and approve pending fixes\n2. Export redirect map for your developer\n3. Consider the $500 SEO Cleanup package for faster results\n4. Add dedicated service pages for each service\n5. Implement LocalBusiness schema",
    });
    setReports(prev => [report, ...prev]);
  };

  if (loading) return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" /></div>;

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Scan Report</h1>
          <p className="text-sm text-gray-500 mt-1">Simple summaries of your website's progress</p>
        </div>
        <Button onClick={generateReport} className="gradient-primary text-white border-0">
          <FileText className="w-4 h-4 mr-2" /> Generate New Report
        </Button>
      </div>

      {reports.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-100 p-12 text-center">
          <FileText className="w-10 h-10 text-gray-300 mx-auto mb-3" />
          <p className="font-medium text-gray-600">No reports generated yet</p>
          <p className="text-sm text-gray-400 mt-1">Click "Generate New Report" to create your first SEO report.</p>
        </div>
      ) : (
        reports.map(report => (
          <div key={report.id} className="bg-white rounded-2xl border border-gray-100 overflow-hidden">
            {/* Header */}
            <div className="px-6 py-5 border-b border-gray-100 bg-gradient-to-r from-blue-50 to-indigo-50">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-bold text-lg">SEO Report — {project?.business_name}</h3>
                  <p className="text-sm text-gray-500 mt-0.5">
                    Generated {new Date(report.created_date).toLocaleDateString()}
                  </p>
                </div>
                <div className="text-right">
                  <div className="text-3xl font-extrabold text-blue-600">{report.seo_score}</div>
                  <div className="text-xs text-gray-400">SEO Score</div>
                </div>
              </div>
            </div>

            {/* Summary */}
            <div className="px-6 py-4 border-b border-gray-100">
              <h4 className="text-sm font-semibold text-gray-900 mb-2">Executive Summary</h4>
              <p className="text-sm text-gray-600 leading-relaxed">{report.summary}</p>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-3 border-b border-gray-100">
              <div className="px-6 py-4 text-center border-r border-gray-100">
                <CheckCircle2 className="w-5 h-5 text-green-500 mx-auto mb-1" />
                <div className="text-xl font-bold text-green-600">{report.fixed_count}</div>
                <div className="text-xs text-gray-500">Fix prepared</div>
              </div>
              <div className="px-6 py-4 text-center border-r border-gray-100">
                <Clock className="w-5 h-5 text-amber-500 mx-auto mb-1" />
                <div className="text-xl font-bold text-amber-600">{report.approval_count}</div>
                <div className="text-xs text-gray-500">Needs approval</div>
              </div>
              <div className="px-6 py-4 text-center">
                <Wrench className="w-5 h-5 text-purple-500 mx-auto mb-1" />
                <div className="text-xl font-bold text-purple-600">{report.developer_count}</div>
                <div className="text-xs text-gray-500">Needs developer</div>
              </div>
            </div>

            {/* Competitor summary */}
            {report.competitor_summary && (
              <div className="px-6 py-4 border-b border-gray-100">
                <h4 className="text-sm font-semibold text-gray-900 mb-2 flex items-center gap-2">
                  <BarChart3 className="w-4 h-4 text-blue-500" /> Competitor Insights
                </h4>
                <p className="text-sm text-gray-600">{report.competitor_summary}</p>
              </div>
            )}

            {/* Next steps */}
            {report.next_steps && (
              <div className="px-6 py-4">
                <h4 className="text-sm font-semibold text-gray-900 mb-2 flex items-center gap-2">
                  <ArrowRight className="w-4 h-4 text-blue-500" /> Recommended Next Steps
                </h4>
                <div className="space-y-2">
                  {report.next_steps.split("\n").map((step, i) => (
                    <p key={i} className="text-sm text-gray-600">{step}</p>
                  ))}
                </div>
              </div>
            )}

            <div className="px-6 py-4 border-t border-gray-100 bg-gray-50/50">
              <Button variant="outline" size="sm" disabled>
                <Download className="w-3.5 h-3.5 mr-1.5" /> Export PDF (Coming Soon)
              </Button>
            </div>
          </div>
        ))
      )}
    </div>
  );
}