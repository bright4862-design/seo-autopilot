import React from "react";

export default function WhatToDoFirst({ counts }) {
  const steps = [];
  if ((counts.needs_approval || 0) > 0) steps.push("Review approval items first.");
  if ((counts.auto_fixed || 0) > 0) steps.push("Review prepared fixes.");
  if ((counts.needs_developer || 0) > 0) steps.push("Review website improvements.");

  return (
    <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
      <h2 className="text-sm font-semibold text-gray-900 mb-3">What to do first</h2>
      {steps.length === 0 ? (
        <p className="text-sm text-gray-500">No major issues found.</p>
      ) : (
        <ol className="space-y-2">
          {steps.map((step, i) => (
            <li key={i} className="flex items-start gap-2.5 text-sm text-gray-600">
              <span className="flex-shrink-0 w-5 h-5 rounded-full bg-gray-100 text-gray-500 text-xs font-medium flex items-center justify-center mt-0.5">{i + 1}</span>
              <span>{step}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}