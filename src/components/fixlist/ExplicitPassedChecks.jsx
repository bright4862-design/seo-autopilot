import React, { useMemo } from "react";

import { buildExplicitPassedChecks } from "@/lib/passedChecksPresentation";

/**
 * Conservative "Already good" presentation.
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
    <section aria-labelledby="fixlist-passed-checks-heading" className="mt-8 border-t border-hairline-soft pt-6">
      <div className="flex items-baseline justify-between gap-4">
        <h2
          id="fixlist-passed-checks-heading"
          className="text-[14px] font-semibold tracking-tight text-ink"
        >
          Already good
        </h2>
        <span className="shrink-0 text-[11px] text-ink-faint">
          {claims.length} {claims.length === 1 ? "check" : "checks"}
        </span>
      </div>

      <ul className="mt-2 divide-y divide-hairline-soft" aria-label="Checks that passed">
        {claims.map((claim) => (
          <li key={claim.key} className="flex items-start gap-2.5 py-3">
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
