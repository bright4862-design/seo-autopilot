import React from "react";
import { Button } from "@/components/ui/button";
import { customerText } from "@/lib/friendlyLabels";

export default function GapInsights({ insights, onCreatePlan, creatingPlan }) {
  return (
    <section className="overflow-hidden rounded-3xl border border-slate-200/80 bg-white shadow-sm">
      <div className="border-b border-slate-100 px-5 py-4 sm:px-6">
        <h2 className="text-base font-semibold text-slate-950">Where competitors look stronger</h2>
        <p className="mt-1 text-sm text-slate-500">Focus on the biggest visible gaps first.</p>
      </div>
      <div className="divide-y divide-slate-100">
        {insights.slice(0, 4).map((insight) => (
          <div key={insight.id} className="px-5 py-5 sm:px-6">
            <h3 className="text-[15px] font-medium text-slate-950">{customerText(insight.insight_title)}</h3>
            <p className="mt-2 text-sm leading-6 text-slate-600">{customerText(insight.explanation)}</p>
          </div>
        ))}
      </div>
      {onCreatePlan && (
        <div className="flex justify-end bg-slate-50/70 px-5 py-4 sm:px-6">
          <Button variant="outline" onClick={onCreatePlan} disabled={creatingPlan} className="rounded-full border-slate-200 bg-white px-5 text-sm font-medium text-slate-700 shadow-none hover:bg-slate-50">
            {creatingPlan ? "Creating…" : "Add to improvement plan"}
          </Button>
        </div>
      )}
    </section>
  );
}