import React, { useState, useEffect } from "react";
import { base44 } from "@/api/base44Client";
import { Button } from "@/components/ui/button";
import { Zap, CheckCircle2, XCircle, ChevronDown, ChevronUp } from "lucide-react";

export default function Metadata() {
  const [recs, setRecs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(null);

  useEffect(() => {
    const load = async () => {
      const projects = await base44.entities.BusinessProject.list("-created_date", 1);
      if (projects.length > 0) {
        const data = await base44.entities.MetadataRecommendation.filter({ project_id: projects[0].id });
        setRecs(data);
      }
      setLoading(false);
    };
    load();
  }, []);

  const handleApprove = async (id) => {
    await base44.entities.MetadataRecommendation.update(id, { approval_status: "approved" });
    setRecs(prev => prev.map(r => r.id === id ? { ...r, approval_status: "approved" } : r));
  };

  if (loading) return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" /></div>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Search Appearance</h1>
        <p className="text-sm text-gray-500 mt-1">AI-written search titles and descriptions for your pages. Pick the one that sounds best.</p>
      </div>

      {recs.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-100 p-12 text-center">
          <Zap className="w-10 h-10 text-gray-300 mx-auto mb-3" />
          <p className="font-medium text-gray-600">No search appearance recommendations yet</p>
          <p className="text-sm text-gray-400 mt-1">Run a scan to generate AI-powered title and description suggestions.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {recs.map((rec, idx) => (
            <div key={rec.id} className="bg-white rounded-xl border border-gray-100 overflow-hidden">
              <button className="w-full px-6 py-4 flex items-center justify-between text-left hover:bg-gray-50 transition-colors" onClick={() => setExpanded(expanded === idx ? null : idx)}>
                <div>
                  <code className="text-xs bg-gray-100 px-2 py-0.5 rounded text-gray-600">{rec.page_url}</code>
                  <p className="text-sm font-medium text-gray-900 mt-1">{rec.current_title || "(no current title)"}</p>
                </div>
                <div className="flex items-center gap-2">
                  {rec.approval_status === "approved" && <span className="text-xs bg-green-100 text-green-700 px-2 py-1 rounded-full">Approved</span>}
                  {expanded === idx ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
                </div>
              </button>

              {expanded === idx && (
                <div className="px-6 pb-6 space-y-6 border-t border-gray-100 pt-4">
                  {/* Title options */}
                  <div>
                    <h4 className="text-sm font-semibold text-gray-900 mb-3 flex items-center gap-2">
                      <Zap className="w-4 h-4 text-blue-600" /> Search title options
                    </h4>
                    <div className="space-y-2">
                      {[rec.recommended_title_1, rec.recommended_title_2, rec.recommended_title_3].filter(Boolean).map((title, i) => (
                        <div key={i} className="flex items-center gap-3 p-3 bg-blue-50 border border-blue-100 rounded-lg">
                          <span className="w-6 h-6 rounded-full bg-blue-200 text-blue-700 text-xs font-bold flex items-center justify-center flex-shrink-0">{i + 1}</span>
                          <p className="text-sm text-blue-900 flex-1">{title}</p>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Description options */}
                  <div>
                    <h4 className="text-sm font-semibold text-gray-900 mb-3">Search description options</h4>
                    <div className="space-y-2">
                      {[rec.recommended_description_1, rec.recommended_description_2, rec.recommended_description_3].filter(Boolean).map((desc, i) => (
                        <div key={i} className="p-3 bg-gray-50 border border-gray-100 rounded-lg">
                          <div className="flex items-start gap-3">
                            <span className="w-6 h-6 rounded-full bg-gray-200 text-gray-600 text-xs font-bold flex items-center justify-center flex-shrink-0 mt-0.5">{i + 1}</span>
                            <p className="text-sm text-gray-700">{desc}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Extras */}
                  <div className="grid sm:grid-cols-2 gap-4">
                    {rec.suggested_h1 && (
                      <div className="bg-indigo-50 border border-indigo-100 rounded-lg p-3">
                        <p className="text-xs font-medium text-indigo-600 uppercase tracking-wider mb-1">Suggested H1</p>
                        <p className="text-sm text-indigo-900">{rec.suggested_h1}</p>
                      </div>
                    )}
                    {rec.suggested_slug && (
                      <div className="bg-gray-50 border border-gray-100 rounded-lg p-3">
                        <p className="text-xs font-medium text-gray-600 uppercase tracking-wider mb-1">Suggested URL</p>
                        <code className="text-sm text-gray-900">{rec.suggested_slug}</code>
                      </div>
                    )}
                  </div>

                  {rec.suggested_faq_ideas && (
                    <div className="bg-amber-50 border border-amber-100 rounded-lg p-3">
                      <p className="text-xs font-medium text-amber-600 uppercase tracking-wider mb-1">FAQ Ideas</p>
                      <p className="text-sm text-amber-900">{rec.suggested_faq_ideas}</p>
                    </div>
                  )}

                  {rec.approval_status !== "approved" && (
                    <div className="flex gap-3">
                      <Button size="sm" className="gradient-primary text-white border-0" onClick={() => handleApprove(rec.id)}>
                        <CheckCircle2 className="w-3.5 h-3.5 mr-1.5" /> Approve Recommendations
                      </Button>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}