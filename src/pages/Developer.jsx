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
      <div className="mx-auto w-full max-w-4xl px-5 py-10 sm:px-6 lg:py-12">
        <div className="mb-8">
          <p className="text-sm font-medium text-blue-600">Bigger next steps</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">Website Improvements</h1>
          <p className="mt-2 text-base leading-7 text-slate-500">Recommendations that may need a website editor or done-for-you help.</p>
        </div>

        <section className="mb-7 overflow-hidden rounded-3xl border border-slate-200/80 bg-white shadow-sm">
          <div className="flex flex-col gap-4 px-5 py-5 sm:flex-row sm:items-center sm:justify-between sm:px-6">
            <div><h2 className="text-base font-semibold text-slate-950">Need help with these?</h2><p className="mt-1 text-sm leading-6 text-slate-500">Request a review of your scan and next steps.</p></div>
            <Button className="rounded-full bg-blue-600 px-5 text-sm font-medium text-white shadow-none hover:bg-blue-700">Request help</Button>
          </div>
        </section>

        {recs.length === 0 ? (
          <div className="rounded-3xl border border-slate-200/80 bg-white p-10 text-center shadow-sm">
            <h2 className="text-lg font-semibold text-slate-950">No website improvements right now.</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">Run a scan or add competitor pages to find larger opportunities.</p>
          </div>
        ) : (
          <div className="space-y-7">
            {GROUPS.map((group) => {
              const items = recs.filter(group.match);
              if (items.length === 0) return null;
              return (
                <section key={group.key} className="overflow-hidden rounded-3xl border border-slate-200/80 bg-white shadow-sm">
                  <div className="border-b border-slate-100 px-5 py-4 sm:px-6"><h2 className="text-base font-semibold text-slate-950">{group.title}</h2></div>
                  <div className="divide-y divide-slate-100">
                    {items.map((rec) => (
                      <div key={rec.id} className="px-5 py-5 sm:px-6">
                        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                          <div className="min-w-0">
                            <h3 className="text-[15px] font-medium text-slate-950">{customerText(rec.title)}</h3>
                            <p className="mt-2 text-sm leading-6 text-slate-600">{customerText(rec.description)}</p>
                            {rec.business_impact && <p className="mt-3 text-sm leading-6 text-slate-600"><span className="font-medium text-slate-950">Why it matters:</span> {customerText(rec.business_impact)}</p>}
                            <p className="mt-3 text-xs font-medium text-slate-400">{getPriorityLabel(rec.priority)} · Suggested next step: review</p>
                          </div>
                          <Button variant="outline" className="rounded-full border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 shadow-none hover:bg-slate-50">Request help</Button>
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