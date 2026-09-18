import React from "react";

import { buildGeoReadinessPresentation } from "@/lib/geoReadinessPresentation";

export default function GeoReadinessPanel({
  geoReadiness,
  customerAccess = "",
  cards = [],
  siteOrigin = "",
  completedAt = "",
}) {
  const presentation = buildGeoReadinessPresentation({
    geoReadiness,
    customerAccess,
    cards,
    siteOrigin,
    completedAt,
  });

  return (
    <section className="mt-8 max-w-[60ch] rounded-2xl border border-hairline-soft bg-white/45 px-5 py-5" aria-labelledby="geo-readiness-heading">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-ink-faint">Experimental v1</p>
          <h2 id="geo-readiness-heading" className="mt-1 text-[18px] font-semibold tracking-tight text-ink">GEO readiness</h2>
          <p className="mt-1 text-[12.5px] text-ink-muted">{presentation.statusLabel}</p>
        </div>
        <div className="text-right">
          <div className="text-[30px] font-semibold leading-none tabular-nums text-ink" aria-label={presentation.scoreAvailable ? `GEO readiness score ${presentation.score}` : "GEO readiness score unavailable"}>
            {presentation.scoreAvailable ? presentation.score : "—"}
          </div>
          <div className="mt-1 text-[11px] text-ink-faint">out of 100</div>
        </div>
      </div>

      <dl className="mt-4 grid grid-cols-1 gap-2 border-y border-hairline-soft py-3 text-[12.5px] sm:grid-cols-2">
        <div><dt className="inline text-ink-faint">Sample: </dt><dd className="inline font-medium text-ink-muted">{presentation.sampleLabel}</dd></div>
        <div><dt className="inline text-ink-faint">Coverage: </dt><dd className="inline font-medium text-ink-muted">{presentation.coverageLabel}</dd></div>
        {presentation.boundsLabel ? (
          <div className="sm:col-span-2"><dt className="inline text-ink-faint">Unresolved outcomes: </dt><dd className="inline font-medium text-ink-muted">{presentation.boundsLabel}</dd></div>
        ) : null}
        {presentation.completedAt ? (
          <div className="sm:col-span-2"><dt className="inline text-ink-faint">Assessed: </dt><dd className="inline text-ink-muted">{new Date(presentation.completedAt).toLocaleString()}</dd></div>
        ) : null}
      </dl>

      <div className="mt-3 space-y-1 text-[11.5px] leading-relaxed text-ink-faint">
        <p>{presentation.methodologyLabel}</p>
        <p>{presentation.nonCitationLabel}</p>
        {presentation.boundsLabel ? <p>The range shows possible outcomes for checks without verified evidence. It is not a statistical confidence interval.</p> : null}
      </div>

      {presentation.actions.length > 0 ? (
        <div className="mt-5 border-t border-hairline-soft pt-4">
          <h3 className="text-[14px] font-semibold text-ink">GEO checks to review</h3>
          <div className="mt-2 divide-y divide-hairline-soft">
            {presentation.actions.map((action) => (
              <article key={action.checkId} className="py-3 first:pt-1">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <h4 className="text-[13px] font-medium text-ink">{action.label || "Review this GEO check"}</h4>
                  <span className="text-[11px] tabular-nums text-ink-faint">{action.affectedPageCount} affected {action.affectedPageCount === 1 ? "page" : "pages"}</span>
                </div>
                {action.existingRepairTitle ? (
                  <p className="mt-1.5 text-[12px] leading-relaxed text-ink-muted">Covered by the existing repair: <span className="font-medium text-ink">{action.existingRepairTitle}</span>.</p>
                ) : (
                  <>
                    {action.suggestedAction ? <p className="mt-1.5 text-[12px] leading-relaxed text-ink-muted">{action.suggestedAction}</p> : null}
                    {action.verificationStep ? <p className="mt-1 text-[11.5px] leading-relaxed text-ink-faint">Verify: {action.verificationStep}</p> : null}
                  </>
                )}
                {action.pages.length > 0 ? (
                  <p className="mt-2 text-[11.5px] text-ink-faint">
                    Examples: {action.pages.map((page, index) => (
                      <React.Fragment key={page.href || page.label}>
                        {index > 0 ? ", " : ""}
                        <a href={page.href} target="_blank" rel="noreferrer" className="underline decoration-hairline underline-offset-2">{page.label}</a>
                      </React.Fragment>
                    ))}{action.pagesArePartial ? " (sample)" : ""}
                  </p>
                ) : null}
              </article>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}
