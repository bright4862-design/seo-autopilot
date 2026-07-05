import React from "react";

export default function ComparisonTable({ customer, competitors }) {
  const avg = (key) => competitors.length ? Math.round(competitors.reduce((sum, competitor) => sum + (competitor[key] || 0), 0) / competitors.length) : 0;
  const countTrue = (key) => competitors.filter((competitor) => competitor[key]).length;

  const rows = [
    { label: "Helpful pages", you: customer.service_pages_count, comp: avg("service_pages_count") },
    { label: "Clear search titles", you: `${customer.title_quality_score}/100`, comp: `${avg("title_quality_score")}/100` },
    { label: "Search descriptions", you: `${customer.meta_coverage_pct}%`, comp: `${avg("meta_coverage_pct")}%` },
    { label: "Helpful page content", you: `${customer.content_depth_score}/100`, comp: `${avg("content_depth_score")}/100` },
    { label: "Customer questions answered", you: "—", comp: `${countTrue("faq_usage")} of ${competitors.length}` },
    { label: "Trust signals", you: "—", comp: `${countTrue("schema_usage")} of ${competitors.length}` },
    { label: "Broken pages", you: customer.broken_links_count, comp: avg("broken_links_count") },
  ];

  return (
    <section className="overflow-hidden rounded-3xl border border-slate-200/80 bg-white shadow-sm">
      <div className="border-b border-slate-100 px-5 py-4 sm:px-6">
        <h3 className="text-base font-semibold text-slate-950">Comparison details</h3>
        <p className="mt-1 text-sm text-slate-500">Your site beside competitor averages.</p>
      </div>
      <div className="divide-y divide-slate-100">
        {rows.map((row) => (
          <div key={row.label} className="grid gap-3 px-5 py-4 sm:grid-cols-[1fr_120px_150px] sm:px-6">
            <div className="text-sm font-medium text-slate-950">{row.label}</div>
            <div className="text-sm text-slate-600"><span className="mr-2 text-slate-400 sm:hidden">Your site</span>{row.you}</div>
            <div className="text-sm text-slate-600"><span className="mr-2 text-slate-400 sm:hidden">Competitors</span>{row.comp}</div>
          </div>
        ))}
      </div>
    </section>
  );
}