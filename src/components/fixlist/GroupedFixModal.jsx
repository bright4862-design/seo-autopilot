import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { customerText, friendlyCategory } from "@/lib/friendlyLabels";
import { pageName } from "@/components/fixlist/fixDisplay";
import { ChevronLeft, Loader2, X } from "lucide-react";

export default function GroupedFixModal({ group, onClose, onStatusUpdate }) {
  const [saving, setSaving] = useState(false);
  const name = pageName(group[0].page_url);
  const whyItMatters = group.find((item) => item.why_it_matters)?.why_it_matters;

  const markAllCompleted = async () => {
    setSaving(true);
    for (const item of group) await onStatusUpdate(item.id, "completed");
    setSaving(false);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/25 p-4" onClick={onClose}>
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-3xl bg-white shadow-2xl shadow-slate-950/10" onClick={(event) => event.stopPropagation()}>
        <div className="flex items-start justify-between gap-4 border-b border-slate-100 px-6 py-5">
          <div><p className="text-sm font-medium text-blue-600">{group.length} recommendations</p><h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">Improve your {name}</h2><p className="mt-1 text-sm text-slate-400">{group[0].page_url}</p></div>
          <div className="flex shrink-0 items-center gap-2">
            <button aria-label="Back" onClick={onClose} className="inline-flex min-h-11 items-center gap-1 rounded-full px-3 text-sm font-medium text-slate-600 hover:bg-slate-50 hover:text-slate-950 sm:hidden"><ChevronLeft className="h-4 w-4" /> Back</button>
            <button aria-label="Close recommendations" onClick={onClose} className="rounded-full p-2 text-slate-400 hover:bg-slate-50 hover:text-slate-700"><X className="h-4 w-4" /></button>
          </div>
        </div>

        <div className="divide-y divide-slate-100">
          {whyItMatters && <section className="px-6 py-5"><h3 className="text-sm font-semibold text-slate-950">Why it matters</h3><p className="mt-2 text-sm leading-6 text-slate-600">{customerText(whyItMatters)}</p></section>}

          {group.map((item) => (
            <section key={item.id} className="px-6 py-5">
              <p className="text-xs font-medium text-slate-400">{friendlyCategory(item.category)}</p>
              <h3 className="mt-2 text-base font-medium text-slate-950">{customerText(item.issue_title)}</h3>
              {item.plain_english_explanation && <p className="mt-2 text-sm leading-6 text-slate-600">{customerText(item.plain_english_explanation)}</p>}
              {item.recommended_value && <p className="mt-3 text-sm leading-6 text-slate-600"><span className="font-medium text-slate-950">Recommended next step:</span> {customerText(item.recommended_value)}</p>}
            </section>
          ))}
        </div>

        <div className="flex justify-end bg-slate-50/70 px-6 py-5">
          <Button variant="outline" onClick={markAllCompleted} disabled={saving} className="rounded-full border-slate-200 bg-white px-5 text-sm font-medium text-slate-700 shadow-none hover:bg-slate-50">
            {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Mark all reviewed
          </Button>
        </div>
      </div>
    </div>
  );
}