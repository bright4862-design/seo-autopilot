import { useId } from "react";
import { buildScanComparisonPanelModel } from "../../lib/scanComparisonPanelModel.js";

/**
 * Presentation only. The caller must obtain presentation from the authenticated
 * comparison reader, after server-side authority and lineage validation. The
 * boolean below is a UI gate, never a substitute for that server verification.
 */
export default function ScanComparisonPanel({
  presentation = null,
  currentScanId,
  authorityVerified = false,
}) {
  const headingId = useId();
  if (presentation === null || presentation === undefined) return null;

  const model = buildScanComparisonPanelModel(presentation);
  const ready = authorityVerified === true
    && model.state === "ready"
    && typeof currentScanId === "string"
    && currentScanId === model.currentScanId;

  if (!ready) {
    return (
      <section aria-labelledby={headingId} className="rounded-xl border border-slate-200 bg-white p-5">
        <h2 id={headingId} className="text-base font-semibold text-slate-900">Comparison unavailable</h2>
        <p className="mt-2 text-sm text-slate-600">
          We couldn’t compare these scans. Your current FixList is still available.
        </p>
      </section>
    );
  }

  const metrics = [
    ...model.metrics.slice(0, 2),
    { key: "came_back", label: "Returned", count: model.counts.came_back },
    ...model.metrics.slice(2),
  ];

  return (
    <section aria-labelledby={headingId} className="rounded-xl border border-slate-200 bg-white p-5 sm:p-6">
      <h2 id={headingId} className="text-lg font-semibold text-slate-900">{model.headline}</h2>
      <dl className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {metrics.map(({ key, label, count }) => (
          <div key={key} className="min-w-0 rounded-lg bg-slate-50 p-3">
            <dt className="text-sm leading-snug text-slate-600">{label}</dt>
            <dd className="mt-2 text-2xl font-semibold tabular-nums text-slate-900">{count}</dd>
          </div>
        ))}
      </dl>
      <div className="mt-5 space-y-1 text-sm text-slate-700">
        <p>{model.scoreLine}</p>
        <p>{model.sampleLine}</p>
      </div>
      <p className="mt-3 rounded-lg bg-slate-50 p-3 text-sm leading-relaxed text-slate-700">
        {model.sampleScopeWarning}
      </p>
      <p className="mt-3 text-xs leading-relaxed text-slate-500">
        New or returned candidates are not confirmed changes. “Could not verify” means
        the available evidence cannot establish whether the repair changed.
      </p>
    </section>
  );
}
