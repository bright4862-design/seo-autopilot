import React from "react";

/**
 * Suggested-fix block for one repair.
 *
 * Presentation only. Every sentence comes from the deterministic suggestion
 * model built by `src/lib/repairSuggestions.js`; no repair-specific copy is
 * written here, so adding or rewording a repair type never touches this file.
 * The model guarantees strings, so an unmapped rule renders its review-the-
 * evidence fallback rather than an empty block or `undefined`.
 *
 * This block never replaces evidence. It sits above the repair's affected URLs
 * and detection details, which remain the source of truth.
 */
export default function SuggestedFix({ suggestion, compact = false }) {
  if (!suggestion) return null;

  const facts = [
    { label: "Fix scope", value: suggestion.fixScopeLabel },
    { label: "Effort", value: suggestion.effortDisplay },
    { label: "Who should fix", value: suggestion.role },
  ].filter((fact) => Boolean(fact.value));

  // The compact form rides on the collapsed repair row, so the customer sees
  // what to do, at what scope, and for how much effort without opening
  // anything. Evidence stays one level down, where it can be read in full.
  if (compact) {
    return (
      <>
        <span className="mt-1.5 block text-[13px] leading-relaxed text-ink-muted">
          <span className="text-ink-faint">Suggested fix · </span>
          <span className="text-ink">{suggestion.suggestedFix}</span>
        </span>
        {facts.length > 0 ? (
          <span className="mt-1.5 block text-[12px] leading-relaxed text-ink-faint">
            {facts.map((fact) => `${fact.label}: ${fact.value}`).join(" · ")}
          </span>
        ) : null}
      </>
    );
  }

  return (
    <div className="mt-6 max-w-[60ch] rounded-lg border border-hairline-soft bg-white/50 px-4 py-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">
          Suggested fix
        </div>
        {suggestion.suggestionAvailable ? null : (
          <span className="text-[11px] font-medium text-ink-faint">Needs manual review</span>
        )}
      </div>
      <p className="mt-1.5 text-[14px] leading-relaxed text-ink">{suggestion.suggestedFix}</p>

      {facts.length > 0 ? (
        <dl className="mt-4 grid gap-x-6 gap-y-2 sm:grid-cols-[auto_1fr]">
          {facts.map((fact) => (
            <React.Fragment key={fact.label}>
              <dt className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint sm:pt-0.5">
                {fact.label}
              </dt>
              <dd className="text-[13.5px] leading-relaxed text-ink">{fact.value}</dd>
            </React.Fragment>
          ))}
        </dl>
      ) : null}

      {suggestion.bestApproach ? (
        <p className="mt-3.5 border-t border-hairline-soft pt-3 text-[13px] leading-relaxed text-ink-muted">
          {suggestion.bestApproach}
        </p>
      ) : null}
    </div>
  );
}
