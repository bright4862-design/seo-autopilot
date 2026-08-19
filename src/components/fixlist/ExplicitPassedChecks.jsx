import React, { useMemo } from "react";

import { buildExplicitPassedChecks } from "@/lib/passedChecksPresentation";

/**
 * Conservative passed-check presentation.
 *
 * This component never derives success from repair-card absence. It renders only
 * claims returned by the explicit rule-evaluation contract:
 * evaluated=true + applicable=true + passed=true.
 *
 * With current production data (which has no supported evaluation ledger), this
 * component intentionally renders nothing.
 */
export default function ExplicitPassedChecks({ scan, claims: suppliedClaims }) {
  const claims = useMemo(
    () => (Array.isArray(suppliedClaims) ? suppliedClaims : buildExplicitPassedChecks(scan || {})),
    [scan, suppliedClaims],
  );

  if (claims.length === 0) return null;

  return (
    <section aria-labelledby="fixlist-passed-checks-heading" className="mt-10 border-t border-hairline-soft pt-5 sm:mt-12 sm:pt-6">
      <div className="flex items-baseline justify-between gap-4">
        <h2
          id="fixlist-passed-checks-heading"
          className="text-[13px] font-semibold tracking-tight text-ink-muted"
        >
          Checks that passed
        </h2>
        <span className="shrink-0 text-[11px] tabular-nums text-ink-faint">
          {claims.length}
        </span>
      </div>
      <p className="mt-1 text-[12px] leading-relaxed text-ink-faint">
        Explicitly evaluated in this scan.
      </p>

      <ul className="mt-2 divide-y divide-hairline-soft" aria-label="Checks that explicitly passed">
        {claims.map((claim) => (
          <li key={claim.key} className="flex items-start gap-2.5 py-2.5 sm:py-3">
            <span
              aria-hidden="true"
              className="mt-[3px] inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-ink/20 text-[10px] leading-none text-ink-muted"
            >
              ✓
            </span>
            <span className="text-[13px] leading-relaxed text-ink-muted">{claim.label}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
