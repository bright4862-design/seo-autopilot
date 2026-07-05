import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { customerText, friendlyCategory } from "@/lib/friendlyLabels";
import { pageName } from "@/components/fixlist/fixDisplay";
import { CheckCircle2, Loader2, X } from "lucide-react";

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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/30 p-4" onClick={onClose}>
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-3xl bg-white shadow-xl" onClick={(event) => event.stopPropagation()}>
        <div className="flex items-start justify-between gap-4 border-b border-slate-100 p-6">
          <div><h2 className="text-2xl font-semibold tracking-tight text-slate-950">Improve your {name}</h2><p className="mt-1 text-sm text-slate-400">{group.length} recommendations prepared for this page · {group[0].page_url}</p></div>
          <button aria-label="Close recommendations" onClick={onClose} className="rounded-full p-2 text-slate-500 hover:bg-slate-50"><X className="h-4 w-4" /></button>
        </div>

        <div className="space-y-5 p-6">
          {whyItMatters && <section><h3 className="text-sm font-semibold text-slate-950">Why it matters</h3><p className="mt-2 text-sm leading-6 text-slate-600">{customerText(whyItMatters)}</p></section>}

          <div className="space-y-4">
            {group.map((item) => (
              <div key={item.id} className="rounded-2xl border border-slate-200 bg-white p-4">
                <p className="text-xs font-medium uppercase tracking-wide text-slate-400">{friendlyCategory(item.category)}</p>
                <h3 className="mt-2 text-base font-medium text-slate-950">{customerText(item.issue_title)}</h3>
                {item.plain_english_explanation && <p className="mt-2 text-sm leading-6 text-slate-600">{customerText(item.plain_english_explanation)}</p>}
                {item.recommended_value && <p className="mt-3 text-sm leading-6 text-slate-600"><span className="font-medium text-slate-950">Recommended next step:</span> {customerText(item.recommended_value)}</p>}
              </div>
            ))}
          </div>

          <div className="flex justify-end border-t border-slate-100 pt-5">
            <Button variant="outline" onClick={markAllCompleted} disabled={saving} className="rounded-full border border-slate-200 bg-white px-5 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50">
              {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <CheckCircle2 className="mr-2 h-4 w-4" />}
              Mark all reviewed
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}