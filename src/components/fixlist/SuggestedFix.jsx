import React from "react";

/**
 * Suggested-fix block for one repair.
 *
 * Presentation only. Every sentence comes from the deterministic suggestion
 * model built by `src/lib/repairSuggestions.js`; no repair-specific copy is
 * written here, so adding or rewording a repair type never touches this file.
 * The model guarantees strings, so an unmapped rule renders its manual-review
 * fallback rather than an empty block.
 */
export default function SuggestedFix({ suggestion, onAskGrok }) {
  if (!suggestion) return null;

  const meta = [
    suggestion.effortLabel ? `Effort · ${suggestion.effortLabel}` : "",
    suggestion.recommendedRole ? `Usually done by · ${suggestion.recommendedRole}` : "",
  ].filter(Boolean).join(" · ");

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

      {suggestion.bestApproach ? (
        <>
          <div className="mt-4 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">
            Best approach
          </div>
          <p className="mt-1.5 text-[13.5px] leading-relaxed text-ink-muted">
            {suggestion.fixStrategyLabel ? (
              <span className="font-medium text-ink">{suggestion.fixStrategyLabel} · </span>
            ) : null}
            {suggestion.bestApproach}
          </p>
        </>
      ) : null}

      {meta ? <p className="mt-3 text-[12.5px] text-ink-faint">{meta}</p> : null}

      {typeof onAskGrok === "function" ? (
        <div className="mt-4 border-t border-hairline-soft pt-3.5">
          <p className="text-[12.5px] text-ink-faint">Need help implementing this?</p>
          <button
            type="button"
            onClick={onAskGrok}
            className="mt-2 rounded-full border border-hairline px-4 py-1.5 text-[13px] font-medium text-ink transition-colors hover:bg-ink hover:text-paper focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
          >
            Ask Grok
          </button>
          <p className="mt-2 text-[11.5px] leading-relaxed text-ink-faint">
            Grok receives this repair and its evidence to help you implement it. FixList keeps the diagnosis and priority.
          </p>
        </div>
      ) : null}
    </div>
  );
}
