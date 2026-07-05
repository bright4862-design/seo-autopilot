import React from "react";

export default function ComparisonTable({ customer, competitors }) {
  const avg = (key) => competitors.length ? Math.round(competitors.reduce((sum, competitor) => sum + (competitor[key] || 0), 0) / competitors.length) : 0;
  const countTrue = (key) => competitors.filter((competitor) => competitor[key]).length;

  const rows = [
    { label: "Helpful pages", you: customer.service_pages_count, comp: avg("service_pages_count") },
    { label: "Clear search titles", you: `${customer.title_quality_score}/100`, comp: `${avg("title_quality_score")}/100` },
    { label: "Search descriptions", you: `${customer.meta_coverage_pct}%`, comp: `${avg("meta_coverage_pct")}%` },
    { label: "Helpful page content", you: `${customer.content_depth_score}/100`, comp: `${avg("content_depth_score")}/100` },
    { label: "FAQs", you: "—", comp: `${countTrue("faq_usage")} of ${competitors.length} use them` },
    { label: "Trust signals", you: "—", comp: `${countTrue("schema_usage")} of ${competitors.length} use them` },
    { label: "Broken pages", you: customer.broken_links_count, comp: avg("broken_links_count") },
  ];

  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-100 px-5 py-4">
        <h3 className="text-lg font-semibold text-slate-950">Comparison details</h3>
        <p className="mt-1 text-sm text-slate-500">A simple view of your site beside competitor averages.</p>
      </div>

      <div className="hidden overflow-x-auto md:block">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-100">
              <th className="px-5 py-3 text-left font-medium text-slate-500">What we compared</th>
              <th className="px-5 py-3 text-left font-medium text-slate-500">Your site</th>
              <th className="px-5 py-3 text-left font-medium text-slate-500">Competitor average</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.label} className="border-b border-slate-100 last:border-b-0">
                <td className="px-5 py-4 font-medium text-slate-950">{row.label}</td>
                <td className="px-5 py-4 text-slate-600">{row.you}</td>
                <td className="px-5 py-4 text-slate-600">{row.comp}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid gap-3 p-4 md:hidden">
        {rows.map((row) => (
          <div key={row.label} className="rounded-xl bg-slate-50 p-4">
            <p className="text-sm font-medium text-slate-950">{row.label}</p>
            <div className="mt-3 grid grid-cols-2 gap-3 text-sm text-slate-600"><div><span className="block text-xs text-slate-400">Your site</span>{row.you}</div><div><span className="block text-xs text-slate-400">Competitors</span>{row.comp}</div></div>
          </div>
        ))}
      </div>
    </div>
  );
}