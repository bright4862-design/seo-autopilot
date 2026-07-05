import React from "react";
import { Compass, CheckCircle2 } from "lucide-react";

export default function WhatToDoFirst({ counts }) {
  const steps = [];
  if ((counts.needs_approval || 0) > 0) steps.push("Review approval items first.");
  if ((counts.auto_fixed || 0) > 0) steps.push("Review prepared fixes.");
  if ((counts.needs_developer || 0) > 0) steps.push("Review website improvements.");

  return (
    <div className="bg-blue-50 border border-blue-100 rounded-2xl p-5">
      <div className="flex items-center gap-2 mb-3">
        <Compass className="w-4 h-4 text-blue-600" />
        <h2 className="text-sm font-semibold text-blue-900 uppercase tracking-wider">What to do first</h2>
      </div>
      {steps.length === 0 ? (
        <p className="flex items-center gap-2 text-sm text-blue-800">
          <CheckCircle2 className="w-4 h-4 text-green-600" /> No major issues found.
        </p>
      ) : (
        <ol className="space-y-2">
          {steps.map((step, i) => (
            <li key={i} className="flex items-start gap-2 text-sm text-blue-800">
              <span className="flex-shrink-0 w-5 h-5 rounded-full bg-blue-100 text-blue-700 text-xs font-semibold flex items-center justify-center mt-0.5">{i + 1}</span>
              <span>{step}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}