import React, { useState, useEffect } from "react";
import { base44 } from "@/api/base44Client";
import { Button } from "@/components/ui/button";
import { PRIORITY_COLORS } from "@/lib/mockData";
import { Wrench, ArrowRight, CheckCircle2, Zap, Clock, Code, FileText, Gauge, Globe, Hammer } from "lucide-react";

const CATEGORY_INFO = {
  quick_fix: { label: "Quick Fixes", icon: Zap, color: "green" },
  cms_seo_setup: { label: "CMS / SEO Setup", icon: Wrench, color: "blue" },
  technical_seo: { label: "Technical SEO", icon: Code, color: "indigo" },
  website_structure: { label: "Website Structure", icon: Globe, color: "purple" },
  content_pages: { label: "Content Pages", icon: FileText, color: "amber" },
  speed_mobile: { label: "Speed & Mobile", icon: Gauge, color: "red" },
  rebuild_migration: { label: "Rebuild / Migration", icon: Hammer, color: "gray" },
};

const PACKAGE_LABELS = {
  diy: { label: "DIY", desc: "You can do this yourself", color: "bg-green-100 text-green-700" },
  "500_cleanup": { label: "$500 Cleanup", desc: "We'll handle it for $500", color: "bg-blue-100 text-blue-700" },
  custom_rebuild: { label: "Custom Quote", desc: "Needs a custom solution", color: "bg-purple-100 text-purple-700" },
};

export default function Developer() {
  const [recs, setRecs] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      const projects = await base44.entities.BusinessProject.list("-created_date", 1);
      if (projects.length > 0) {
        const data = await base44.entities.DeveloperRecommendation.filter({ project_id: projects[0].id });
        setRecs(data);
      }
      setLoading(false);
    };
    load();
  }, []);

  if (loading) return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" /></div>;

  const grouped = {};
  recs.forEach(r => {
    if (!grouped[r.category]) grouped[r.category] = [];
    grouped[r.category].push(r);
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Web Development Recommendations</h1>
          <p className="text-sm text-gray-500 mt-1">Developer work that would boost your rankings — sorted by impact</p>
        </div>
        <Button className="gradient-primary text-white border-0">
          <Wrench className="w-4 h-4 mr-2" /> Request Done-for-You Help
        </Button>
      </div>

      {/* Package summary */}
      <div className="grid sm:grid-cols-3 gap-4">
        {Object.entries(PACKAGE_LABELS).map(([key, pkg]) => {
          const count = recs.filter(r => r.recommended_package === key).length;
          return (
            <div key={key} className="bg-white rounded-xl border border-gray-100 p-4">
              <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${pkg.color}`}>{pkg.label}</span>
              <p className="text-2xl font-bold text-gray-900 mt-2">{count}</p>
              <p className="text-xs text-gray-500 mt-0.5">{pkg.desc}</p>
            </div>
          );
        })}
      </div>

      {recs.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-100 p-12 text-center">
          <Wrench className="w-10 h-10 text-gray-300 mx-auto mb-3" />
          <p className="font-medium text-gray-600">No developer recommendations yet</p>
          <p className="text-sm text-gray-400 mt-1">Run a crawl to generate web development recommendations.</p>
        </div>
      ) : (
        Object.entries(grouped).map(([cat, items]) => {
          const info = CATEGORY_INFO[cat] || { label: cat, icon: Wrench, color: "gray" };
          return (
            <div key={cat} className="bg-white rounded-xl border border-gray-100 overflow-hidden">
              <div className="px-6 py-4 border-b border-gray-100 flex items-center gap-2">
                <info.icon className="w-4 h-4 text-gray-600" />
                <h3 className="font-semibold">{info.label}</h3>
                <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full ml-auto">{items.length}</span>
              </div>
              <div className="divide-y divide-gray-50">
                {items.map(rec => (
                  <div key={rec.id} className="px-6 py-4">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <h4 className="text-sm font-semibold text-gray-900">{rec.title}</h4>
                          <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium border ${PRIORITY_COLORS[rec.priority]}`}>
                            {rec.priority}
                          </span>
                        </div>
                        <p className="text-sm text-gray-500 mb-3">{rec.description}</p>
                        {rec.business_impact && (
                          <div className="bg-blue-50 border border-blue-100 rounded-lg p-3 mb-3">
                            <p className="text-xs font-medium text-blue-600 mb-0.5">Why this matters for your business</p>
                            <p className="text-xs text-blue-700">{rec.business_impact}</p>
                          </div>
                        )}
                        <div className="flex flex-wrap gap-2">
                          <span className="text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded-full">
                            Complexity: {rec.estimated_complexity}
                          </span>
                          {rec.recommended_package && (
                            <span className={`text-xs px-2 py-1 rounded-full ${PACKAGE_LABELS[rec.recommended_package]?.color || "bg-gray-100 text-gray-600"}`}>
                              {PACKAGE_LABELS[rec.recommended_package]?.label || rec.recommended_package}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          );
        })
      )}
    </div>
  );
}