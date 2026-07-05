import React, { useEffect, useState } from "react";
import { base44 } from "@/api/base44Client";
import { Button } from "@/components/ui/button";
import { customerText, getPriorityLabel } from "@/lib/friendlyLabels";

const GROUPS = [
  { key: "content", title: "Content improvements", match: (rec) => ["content_pages", "quick_fix"].includes(rec.category) },
  { key: "setup", title: "Website setup", match: (rec) => ["cms_seo_setup", "technical_seo", "website_structure", "speed_mobile"].includes(rec.category) },
  { key: "gaps", title: "Competitor gaps", match: (rec) => rec.category === "competitor_gap" || /competitor/i.test(rec.title || "") },
  { key: "projects", title: "Larger projects", match: (rec) => ["rebuild_migration"].includes(rec.category) || rec.recommended_package === "custom_rebuild" },
];

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

  if (loading) return <div className="flex h-64 items-center justify-center"><div className="h-8 w-8 animate-spin rounded-full border-4 border-slate-200 border-t-blue-600" /></div>;

  return (
    <div className="min-h-screen bg-[#F7F8FA]">
      <div className="mx-auto w-full max-w-5xl px-6 py-10">
        <div className="mb-8 flex items-start justify-between gap-6">
          <div><h1 className="text-3xl font-semibold tracking-tight text-slate-950">Website Improvements</h1><p className="mt-2 text-base text-slate-500">Recommendations that may need a website editor, developer, or done-for-you help.</p></div>
        </div>

        <div className="mb-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div><h2 className="text-base font-semibold text-slate-950">Need help with these?</h2><p className="mt-1 text-sm text-slate-500">Request done-for-you help and we’ll review your scan.</p></div>
            <Button className="rounded-full bg-blue-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-blue-700">Request help</Button>
          </div>
        </div>

        {recs.length === 0 ? (
          <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center shadow-sm">
            <h2 className="text-lg font-semibold text-slate-950">No website improvements right now.</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">Run a scan or add competitor pages to find larger opportunities.</p>
          </div>
        ) : (
          <div className="space-y-8">
            {GROUPS.map((group) => {
              const items = recs.filter(group.match);
              if (items.length === 0) return null;
              return (
                <section key={group.key} className="rounded-2xl border border-slate-200 bg-white shadow-sm">
                  <div className="border-b border-slate-100 px-5 py-4"><h2 className="text-lg font-semibold text-slate-950">{group.title}</h2></div>
                  <div className="divide-y divide-slate-100">
                    {items.map((rec) => (
                      <div key={rec.id} className="px-5 py-5">
                        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                          <div className="min-w-0">
                            <h3 className="text-base font-medium text-slate-950">{customerText(rec.title)}</h3>
                            <p className="mt-2 text-sm leading-6 text-slate-600">{customerText(rec.description)}</p>
                            {rec.business_impact && <p className="mt-3 text-sm leading-6 text-slate-600"><span className="font-medium text-slate-950">Why it matters:</span> {customerText(rec.business_impact)}</p>}
                            <div className="mt-3 flex flex-wrap gap-2"><span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600">{getPriorityLabel(rec.priority)}</span><span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600">Suggested next step: review</span></div>
                          </div>
                          <Button variant="outline" className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">Request help</Button>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}