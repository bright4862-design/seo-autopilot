import React from "react";
import { Button } from "@/components/ui/button";
import { PRIORITY_COLORS, STATUS_COLORS, STATUS_LABELS, CATEGORY_LABELS } from "@/lib/mockData";
import { X, CheckCircle2, XCircle, Wrench, ThumbsUp, AlertTriangle, Info, Zap } from "lucide-react";

export default function IssueDetailModal({ issue, onClose, onStatusUpdate }) {
  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="sticky top-0 bg-white border-b border-gray-100 px-6 py-4 flex items-center justify-between rounded-t-2xl">
          <div>
            <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium border ${PRIORITY_COLORS[issue.priority]} mr-2`}>
              {issue.priority}
            </span>
            <span className="text-xs text-gray-400">{CATEGORY_LABELS[issue.category]}</span>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100"><X className="w-4 h-4" /></button>
        </div>

        <div className="p-6 space-y-6">
          <div>
            <h2 className="text-lg font-bold text-gray-900 mb-1">{issue.issue_title}</h2>
            <code className="text-xs bg-gray-100 px-2 py-1 rounded text-gray-600">{issue.page_url}</code>
          </div>

          {/* Status */}
          <div className="flex items-center gap-2">
            <span className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium ${STATUS_COLORS[issue.status]}`}>
              {STATUS_LABELS[issue.status]}
            </span>
            {issue.confidence_score > 0 && (
              <span className="text-xs text-gray-400">Confidence: {issue.confidence_score}%</span>
            )}
          </div>

          {/* Explanation */}
          {issue.plain_english_explanation && (
            <div className="bg-blue-50 border border-blue-100 rounded-xl p-4">
              <div className="flex items-start gap-2">
                <Info className="w-4 h-4 text-blue-600 mt-0.5 flex-shrink-0" />
                <div>
                  <p className="text-sm font-medium text-blue-900 mb-1">What's happening</p>
                  <p className="text-sm text-blue-700">{issue.plain_english_explanation}</p>
                </div>
              </div>
            </div>
          )}

          {issue.why_it_matters && (
            <div className="bg-amber-50 border border-amber-100 rounded-xl p-4">
              <div className="flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-600 mt-0.5 flex-shrink-0" />
                <div>
                  <p className="text-sm font-medium text-amber-900 mb-1">Why this matters</p>
                  <p className="text-sm text-amber-700">{issue.why_it_matters}</p>
                </div>
              </div>
            </div>
          )}

          {/* Current vs Recommended */}
          {(issue.current_value || issue.recommended_value) && (
            <div className="grid sm:grid-cols-2 gap-4">
              {issue.current_value && (
                <div className="bg-red-50 border border-red-100 rounded-xl p-4">
                  <p className="text-xs font-medium text-red-600 mb-1 uppercase tracking-wider">Current</p>
                  <p className="text-sm text-red-800">{issue.current_value}</p>
                </div>
              )}
              {issue.recommended_value && (
                <div className="bg-green-50 border border-green-100 rounded-xl p-4">
                  <p className="text-xs font-medium text-green-600 mb-1 uppercase tracking-wider">Recommended</p>
                  <p className="text-sm text-green-800">{issue.recommended_value}</p>
                </div>
              )}
            </div>
          )}

          {issue.ai_recommendation && (
            <div className="bg-indigo-50 border border-indigo-100 rounded-xl p-4">
              <div className="flex items-start gap-2">
                <Zap className="w-4 h-4 text-indigo-600 mt-0.5 flex-shrink-0" />
                <div>
                  <p className="text-sm font-medium text-indigo-900 mb-1">AI Recommendation</p>
                  <p className="text-sm text-indigo-700">{issue.ai_recommendation}</p>
                </div>
              </div>
            </div>
          )}

          {/* Flags */}
          <div className="flex flex-wrap gap-2">
            {issue.can_auto_fix && <span className="text-xs bg-green-100 text-green-700 px-2 py-1 rounded-full">✓ Prepared for you</span>}
            {issue.requires_approval && <span className="text-xs bg-amber-100 text-amber-700 px-2 py-1 rounded-full">⏳ Requires your approval</span>}
            {issue.requires_developer && <span className="text-xs bg-purple-100 text-purple-700 px-2 py-1 rounded-full">🔧 Needs a developer</span>}
          </div>

          {/* Actions */}
          <div className="flex flex-wrap gap-3 pt-2 border-t border-gray-100">
            {(issue.status === "needs_approval" || issue.status === "open") && (
              <>
                <Button size="sm" className="gradient-primary text-white border-0" onClick={() => onStatusUpdate(issue.id, "approved")}>
                  <ThumbsUp className="w-3.5 h-3.5 mr-1.5" /> Approve Fix
                </Button>
                <Button size="sm" variant="outline" className="text-red-600 border-red-200 hover:bg-red-50" onClick={() => onStatusUpdate(issue.id, "rejected")}>
                  <XCircle className="w-3.5 h-3.5 mr-1.5" /> Reject
                </Button>
              </>
            )}
            <Button size="sm" variant="outline" onClick={() => onStatusUpdate(issue.id, "completed")}>
              <CheckCircle2 className="w-3.5 h-3.5 mr-1.5" /> Mark Completed
            </Button>
            {issue.requires_developer && (
              <Button size="sm" variant="outline" className="text-purple-600 border-purple-200 hover:bg-purple-50">
                <Wrench className="w-3.5 h-3.5 mr-1.5" /> Request Help
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}