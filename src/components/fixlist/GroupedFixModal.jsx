import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { pageName, fixTypeLabel } from "@/components/fixlist/fixDisplay";
import { X, CheckCircle2, AlertTriangle, Loader2 } from "lucide-react";

export default function GroupedFixModal({ group, onClose, onStatusUpdate }) {
  const [saving, setSaving] = useState(false);
  const name = pageName(group[0].page_url);
  const whyItMatters = group.find(i => i.why_it_matters)?.why_it_matters;

  const markAllCompleted = async () => {
    setSaving(true);
    for (const issue of group) {
      await onStatusUpdate(issue.id, "completed");
    }
    setSaving(false);
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="sticky top-0 bg-white border-b border-gray-100 px-6 py-4 flex items-center justify-between rounded-t-2xl">
          <div>
            <h2 className="font-bold text-gray-900">Improve your {name}</h2>
            <p className="text-xs text-gray-400">{group.length} recommendations prepared for this page · {group[0].page_url}</p>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100"><X className="w-4 h-4" /></button>
        </div>

        <div className="p-6 space-y-5">
          {whyItMatters && (
            <div className="bg-amber-50 border border-amber-100 rounded-xl p-4 flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-600 mt-0.5 flex-shrink-0" />
              <div>
                <p className="text-sm font-medium text-amber-900 mb-1">Why this matters</p>
                <p className="text-sm text-amber-700">{whyItMatters}</p>
              </div>
            </div>
          )}

          {group.map(issue => (
            <div key={issue.id} className="border border-gray-100 rounded-xl p-4 space-y-3">
              <p className="text-xs font-semibold text-blue-600 uppercase tracking-wider">
                {fixTypeLabel(issue)} recommendation
              </p>
              <p className="text-sm font-medium text-gray-800">{issue.issue_title}</p>
              {issue.plain_english_explanation && (
                <p className="text-sm text-gray-500">{issue.plain_english_explanation}</p>
              )}
              <div className="grid sm:grid-cols-2 gap-3">
                {issue.current_value && (
                  <div className="bg-red-50 border border-red-100 rounded-lg p-3">
                    <p className="text-xs font-medium text-red-600 mb-1 uppercase tracking-wider">Current</p>
                    <p className="text-sm text-red-800">{issue.current_value}</p>
                  </div>
                )}
                {issue.recommended_value && (
                  <div className="bg-green-50 border border-green-100 rounded-lg p-3">
                    <p className="text-xs font-medium text-green-600 mb-1 uppercase tracking-wider">Recommended</p>
                    <p className="text-sm text-green-800">{issue.recommended_value}</p>
                  </div>
                )}
              </div>
            </div>
          ))}

          <div className="flex justify-end pt-2 border-t border-gray-100">
            <Button size="sm" variant="outline" onClick={markAllCompleted} disabled={saving}>
              {saving ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5 mr-1.5" />}
              Mark all as done
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}