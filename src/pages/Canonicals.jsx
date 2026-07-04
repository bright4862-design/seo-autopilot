import React, { useState, useEffect } from "react";
import { base44 } from "@/api/base44Client";
import { Globe, AlertTriangle, CheckCircle2, XCircle, FileText, Search } from "lucide-react";

export default function Canonicals() {
  const [pages, setPages] = useState([]);
  const [issues, setIssues] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      const projects = await base44.entities.BusinessProject.list("-created_date", 1);
      if (projects.length > 0) {
        const [p, iss] = await Promise.all([
          base44.entities.CrawledPage.filter({ project_id: projects[0].id }),
          base44.entities.SeoIssue.filter({ project_id: projects[0].id }),
        ]);
        setPages(p);
        setIssues(iss.filter(i => i.category === "canonical" || i.category === "sitemap"));
      }
      setLoading(false);
    };
    load();
  }, []);

  if (loading) return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" /></div>;

  const missingCanonical = pages.filter(p => !p.canonical_url && p.status_code === 200);
  const canonicalTo404 = pages.filter(p => p.canonical_url && p.status_code === 404);
  const sitemapWith404 = pages.filter(p => p.in_sitemap && p.status_code === 404);
  const notInSitemap = pages.filter(p => !p.in_sitemap && p.status_code === 200 && p.indexable);

  const sections = [
    { title: "Missing Canonicals", desc: "Pages without a canonical tag — Google might index duplicate versions", icon: XCircle, color: "red", items: missingCanonical, render: p => p.url },
    { title: "Sitemap URLs returning 404", desc: "Your sitemap tells Google to visit pages that don't exist", icon: AlertTriangle, color: "amber", items: sitemapWith404, render: p => p.url },
    { title: "Pages missing from sitemap", desc: "Good pages that should be in your sitemap but aren't", icon: FileText, color: "blue", items: notInSitemap, render: p => p.url },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Canonicals & Sitemap</h1>
        <p className="text-sm text-gray-500 mt-1">Make sure Google sees the right pages and finds them in your sitemap</p>
      </div>

      {/* Summary */}
      <div className="grid sm:grid-cols-4 gap-4">
        {[
          { label: "Total Pages", value: pages.length, color: "bg-blue-50 text-blue-700" },
          { label: "In Sitemap", value: pages.filter(p => p.in_sitemap).length, color: "bg-green-50 text-green-700" },
          { label: "Missing Canonical", value: missingCanonical.length, color: "bg-red-50 text-red-700" },
          { label: "Sitemap 404s", value: sitemapWith404.length, color: "bg-amber-50 text-amber-700" },
        ].map(s => (
          <div key={s.label} className="bg-white rounded-xl border border-gray-100 p-4">
            <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${s.color}`}>{s.value}</span>
            <p className="text-sm font-medium text-gray-600 mt-2">{s.label}</p>
          </div>
        ))}
      </div>

      {/* Canonical issues from SeoIssue */}
      {issues.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-100">
            <h3 className="font-semibold">Specific Issues Found</h3>
          </div>
          <div className="divide-y divide-gray-50">
            {issues.map(iss => (
              <div key={iss.id} className="px-6 py-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-sm font-medium text-gray-900">{iss.issue_title}</p>
                    <code className="text-xs bg-gray-100 px-1.5 py-0.5 rounded text-gray-600 mt-1 inline-block">{iss.page_url}</code>
                    <p className="text-xs text-gray-500 mt-1">{iss.plain_english_explanation}</p>
                  </div>
                  <span className={`text-xs px-2 py-1 rounded-full flex-shrink-0 ${iss.status === "needs_approval" ? "bg-amber-100 text-amber-700" : iss.status === "auto_fixed" ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-600"}`}>
                    {iss.status === "auto_fixed" ? "Fixed" : iss.status === "needs_approval" ? "Needs approval" : iss.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Section lists */}
      {sections.map(section => (
        <div key={section.title} className="bg-white rounded-xl border border-gray-100 overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-100 flex items-center gap-2">
            <section.icon className={`w-4 h-4 ${section.color === "red" ? "text-red-500" : section.color === "amber" ? "text-amber-500" : "text-blue-500"}`} />
            <div>
              <h3 className="font-semibold">{section.title} ({section.items.length})</h3>
              <p className="text-xs text-gray-500">{section.desc}</p>
            </div>
          </div>
          {section.items.length === 0 ? (
            <div className="px-6 py-6 text-center text-sm text-gray-400 flex items-center justify-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-green-500" /> All good here!
            </div>
          ) : (
            <div className="divide-y divide-gray-50">
              {section.items.map((item, i) => (
                <div key={i} className="px-6 py-3">
                  <code className="text-xs bg-gray-100 px-1.5 py-0.5 rounded text-gray-600">{section.render(item)}</code>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}