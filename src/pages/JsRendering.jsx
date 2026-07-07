import React, { useState, useEffect } from "react";
import { base44 } from "@/api/base44Client";
import { AlertTriangle, CheckCircle2, Info } from "lucide-react";

export default function JsRendering() {
  const [pages, setPages] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      const projects = await base44.entities.BusinessProject.list("-created_date", 1);
      if (projects.length > 0) {
        const data = await base44.entities.CrawledPage.filter({ project_id: projects[0].id });
        setPages(data);
      }
      setLoading(false);
    };
    load();
  }, []);

  if (loading) return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" /></div>;

  const jsPages = pages.filter(p => p.js_difference_detected);
  const okPages = pages.filter(p => !p.js_difference_detected && p.status_code === 200);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Website Content Check</h1>
        <p className="text-sm text-gray-500 mt-1">Review pages where important content may need a closer look.</p>
      </div>

      <div className="bg-blue-50 border border-blue-100 rounded-xl p-4">
        <div className="flex items-start gap-2">
          <Info className="w-4 h-4 text-blue-600 mt-0.5 flex-shrink-0" />
          <p className="text-sm text-blue-700">
            Some important page content may need a deeper manual review. This may be okay, but if titles, links, or content are hard to see directly, a website editor should review it.
          </p>
        </div>
      </div>

      {/* Summary */}
      <div className="grid sm:grid-cols-3 gap-4">
        <div className="bg-white rounded-xl border border-gray-100 p-4">
          <span className="text-2xl font-bold text-gray-900">{pages.filter(p => p.status_code === 200).length}</span>
          <p className="text-sm text-gray-500 mt-1">Pages scanned</p>
        </div>
        <div className="bg-white rounded-xl border border-gray-100 p-4">
          <span className="text-2xl font-bold text-amber-600">{jsPages.length}</span>
          <p className="text-sm text-gray-500 mt-1">Pages to review</p>
        </div>
        <div className="bg-white rounded-xl border border-gray-100 p-4">
          <span className="text-2xl font-bold text-green-600">{okPages.length}</span>
          <p className="text-sm text-gray-500 mt-1">Pages look the same</p>
        </div>
      </div>

      {/* Pages with JS differences */}
      {jsPages.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-100 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-500" />
            <h3 className="font-semibold">Pages to review</h3>
          </div>
          <div className="divide-y divide-gray-50">
            {jsPages.map(page => (
              <div key={page.id} className="px-6 py-4">
                <code className="text-xs bg-gray-100 px-2 py-0.5 rounded text-gray-600 mb-3 inline-block">{page.url}</code>
                <div className="grid sm:grid-cols-2 gap-4 mt-3">
                  <div className="bg-red-50 border border-red-100 rounded-lg p-3">
                    <p className="text-xs font-medium text-red-600 uppercase tracking-wider mb-2">Direct page content</p>
                    <div className="space-y-1 text-xs text-red-800">
                      <p>Title: {page.title || "(empty)"}</p>
                      <p>Description: {page.meta_description || "(empty)"}</p>
                      <p>Words: {page.word_count}</p>
                    </div>
                  </div>
                  <div className="bg-green-50 border border-green-100 rounded-lg p-3">
                    <p className="text-xs font-medium text-green-600 uppercase tracking-wider mb-2">Loaded page content</p>
                    <div className="space-y-1 text-xs text-green-800">
                      <p>Title: {page.rendered_title || "(empty)"}</p>
                      <p>Description: {page.rendered_meta_description || "(empty)"}</p>
                      <p>Words: varies</p>
                    </div>
                  </div>
                </div>
                <div className="mt-3 bg-purple-50 border border-purple-100 rounded-lg p-3">
                  <p className="text-xs text-purple-700">
                    <strong>Recommendation:</strong> A website editor should review this page. Important content or search appearance details may be hard for Google to read clearly.
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {jsPages.length === 0 && (
        <div className="bg-green-50 border border-green-100 rounded-xl p-6 text-center">
          <CheckCircle2 className="w-10 h-10 text-green-500 mx-auto mb-3" />
          <h3 className="font-semibold text-green-900">All pages look good!</h3>
          <p className="text-sm text-green-700 mt-1">No significant content visibility differences found.</p>
        </div>
      )}
    </div>
  );
}
