import React from "react";
import { TrendingUp, ArrowRight } from "lucide-react";

const IMPACT_STYLES = {
  high: "bg-red-100 text-red-700",
  medium: "bg-amber-100 text-amber-700",
  low: "bg-gray-100 text-gray-600",
};

export default function GapInsights({ insights }) {
  return (
    <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
      <div className="px-6 py-4 border-b border-gray-100">
        <h3 className="font-semibold flex items-center gap-2">
          <TrendingUp className="w-4 h-4 text-amber-500" />
          Where competitors look stronger
        </h3>
      </div>
      <div className="divide-y divide-gray-50">
        {insights.map(insight => (
          <div key={insight.id} className="px-6 py-4">
            <div className="flex items-center gap-2 mb-1">
              <h4 className="text-sm font-semibold text-gray-900">{insight.insight_title}</h4>
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${IMPACT_STYLES[insight.impact] || IMPACT_STYLES.medium}`}>
                {insight.impact} impact
              </span>
            </div>
            <p className="text-sm text-gray-500 mb-2">{insight.explanation}</p>
            <p className="text-sm text-blue-700 flex items-start gap-1.5">
              <ArrowRight className="w-4 h-4 mt-0.5 flex-shrink-0" />
              {insight.recommended_action}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}