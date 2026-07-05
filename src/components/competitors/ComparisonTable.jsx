import React from "react";
import { TrendingUp } from "lucide-react";

export default function ComparisonTable({ customer, competitors }) {
  const avg = (key) => competitors.length
    ? Math.round(competitors.reduce((s, c) => s + (c[key] || 0), 0) / competitors.length)
    : 0;
  const countTrue = (key) => competitors.filter(c => c[key]).length;

  const rows = [
    { label: "Service pages", you: customer.service_pages_count, comp: avg("service_pages_count"), higherIsBetter: true },
    { label: "Clear search titles", you: `${customer.title_quality_score}/100`, comp: `${avg("title_quality_score")}/100`, youNum: customer.title_quality_score, compNum: avg("title_quality_score"), higherIsBetter: true },
    { label: "Search descriptions", you: `${customer.meta_coverage_pct}%`, comp: `${avg("meta_coverage_pct")}%`, youNum: customer.meta_coverage_pct, compNum: avg("meta_coverage_pct"), higherIsBetter: true },
    { label: "Helpful page content", you: `${customer.content_depth_score}/100`, comp: `${avg("content_depth_score")}/100`, youNum: customer.content_depth_score, compNum: avg("content_depth_score"), higherIsBetter: true },
    { label: "FAQs", you: "—", comp: `${countTrue("faq_usage")} of ${competitors.length} use them` },
    { label: "Trust signals for Google", you: "—", comp: `${countTrue("schema_usage")} of ${competitors.length} use them` },
    { label: "Broken pages", you: customer.broken_links_count, comp: avg("broken_links_count"), higherIsBetter: false },
  ];

  return (
    <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
      <div className="px-6 py-4 border-b border-gray-100">
        <h3 className="font-semibold">Your Site vs. Competitor Average</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100 bg-gray-50/50">
              <th className="text-left font-medium text-gray-500 px-4 py-3">What we compared</th>
              <th className="text-center font-medium text-blue-600 px-4 py-3 bg-blue-50/50">Your Site</th>
              <th className="text-center font-medium text-gray-500 px-4 py-3">Competitor Average</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(r => {
              const youNum = r.youNum ?? (typeof r.you === "number" ? r.you : null);
              const compNum = r.compNum ?? (typeof r.comp === "number" ? r.comp : null);
              const compAhead = youNum !== null && compNum !== null &&
                (r.higherIsBetter ? compNum > youNum : compNum < youNum);
              return (
                <tr key={r.label} className="border-b border-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-700">{r.label}</td>
                  <td className="px-4 py-3 text-center bg-blue-50/30 font-medium text-gray-900">{r.you}</td>
                  <td className="px-4 py-3 text-center">
                    <span className={compAhead ? "text-green-600 font-medium" : "text-gray-600"}>{r.comp}</span>
                    {compAhead && <TrendingUp className="w-3 h-3 text-green-500 inline-block ml-1" />}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}