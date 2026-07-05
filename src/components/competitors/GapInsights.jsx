import React from "react";
import { Button } from "@/components/ui/button";
import { customerText } from "@/lib/friendlyLabels";

export default function GapInsights({ insights, onCreatePlan, creatingPlan }) {
  return (
    <section>
      <div className="mb-4">
        <h2 className="text-lg font-semibold text-slate-950">Where competitors look stronger</h2>
        <p className="mt-1 text-sm text-slate-500">Focus on the biggest visible gaps first.</p>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        {insights.slice(0, 4).map((insight) => (
          <div key={insight.id} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h3 className="text-base font-semibold text-slate-950">{customerText(insight.insight_title)}</h3>
            <p className="mt-2 text-sm leading-6 text-slate-600">{customerText(insight.explanation)}</p>
            {onCreatePlan && (
              <Button variant="outline" onClick={onCreatePlan} disabled={creatingPlan} className="mt-4 rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">
                {creatingPlan ? "Creating…" : "Create improvement plan"}
              </Button>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}