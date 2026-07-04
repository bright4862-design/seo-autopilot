import React, { useState, useEffect } from "react";
import { base44 } from "@/api/base44Client";
import { BarChart3, TrendingUp, AlertTriangle, CheckCircle2, XCircle, Users } from "lucide-react";

export default function Competitors() {
  const [competitors, setCompetitors] = useState([]);
  const [project, setProject] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      const projects = await base44.entities.BusinessProject.list("-created_date", 1);
      if (projects.length > 0) {
        setProject(projects[0]);
        const data = await base44.entities.Competitor.filter({ project_id: projects[0].id });
        setCompetitors(data);
      }
      setLoading(false);
    };
    load();
  }, []);

  if (loading) return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" /></div>;

  const metrics = [
    { key: "service_pages_count", label: "Service Pages", you: 3, format: v => v },
    { key: "title_quality_score", label: "Title Quality", you: 55, format: v => `${v}/100` },
    { key: "meta_coverage_pct", label: "Meta Coverage", you: 40, format: v => `${v}%` },
    { key: "content_depth_score", label: "Content Depth", you: 35, format: v => `${v}/100` },
    { key: "faq_usage", label: "FAQ Usage", you: false, format: v => v ? "Yes" : "No" },
    { key: "schema_usage", label: "Schema Markup", you: false, format: v => v ? "Yes" : "No" },
    { key: "broken_links_count", label: "Broken Links", you: 4, format: v => v },
  ];

  const insights = [
    { text: `${competitors[0]?.name || "Competitor A"} has dedicated service pages for services you only mention on your homepage.`, type: "gap" },
    { text: `${competitors[1]?.name || "Competitor B"} uses location-specific title tags on every page.`, type: "gap" },
    { text: `${competitors[1]?.name || "Competitor B"} answers pricing and FAQ questions directly on service pages.`, type: "gap" },
    { text: "Your site has broken internal links that competitors do not appear to have.", type: "warning" },
    { text: "You're missing LocalBusiness schema that two of your competitors already have.", type: "gap" },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Competitor Benchmark</h1>
        <p className="text-sm text-gray-500 mt-1">See how your site compares to local competitors</p>
      </div>

      {competitors.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-100 p-12 text-center">
          <Users className="w-10 h-10 text-gray-300 mx-auto mb-3" />
          <p className="font-medium text-gray-600">No competitors added yet</p>
          <p className="text-sm text-gray-400 mt-1">Add competitors during onboarding or settings to see benchmark data.</p>
        </div>
      ) : (
        <>
          {/* Comparison table */}
          <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-100 bg-gray-50/50">
                    <th className="text-left font-medium text-gray-500 px-4 py-3">Metric</th>
                    <th className="text-center font-medium text-blue-600 px-4 py-3 bg-blue-50/50">Your Site</th>
                    {competitors.map(c => (
                      <th key={c.id} className="text-center font-medium text-gray-500 px-4 py-3">{c.name}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {metrics.map(m => {
                    const youVal = m.you;
                    return (
                      <tr key={m.key} className="border-b border-gray-50">
                        <td className="px-4 py-3 font-medium text-gray-700">{m.label}</td>
                        <td className="px-4 py-3 text-center bg-blue-50/30">
                          <span className="font-medium text-gray-900">{m.format(youVal)}</span>
                        </td>
                        {competitors.map(c => {
                          const val = c[m.key];
                          const isBetter = typeof val === "boolean" ? (val && !youVal) : typeof val === "number" ? val > youVal : false;
                          return (
                            <td key={c.id} className="px-4 py-3 text-center">
                              <span className={isBetter ? "text-green-600 font-medium" : "text-gray-600"}>
                                {m.format(val)}
                              </span>
                              {isBetter && m.key !== "broken_links_count" && <TrendingUp className="w-3 h-3 text-green-500 inline-block ml-1" />}
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Insights */}
          <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-100">
              <h3 className="font-semibold flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-500" />
                Why competitors may be outranking you
              </h3>
            </div>
            <div className="divide-y divide-gray-50">
              {insights.map((insight, i) => (
                <div key={i} className="px-6 py-4 flex items-start gap-3">
                  {insight.type === "warning" ? (
                    <XCircle className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />
                  ) : (
                    <TrendingUp className="w-4 h-4 text-amber-500 mt-0.5 flex-shrink-0" />
                  )}
                  <p className="text-sm text-gray-700">{insight.text}</p>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}