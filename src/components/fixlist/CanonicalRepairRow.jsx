import React, { useMemo, useState } from "react";

import { repairRowModel } from "@/lib/repairPresentation";

/**
 * Compact action-priority row for the canonical FixList presentation.
 *
 * This component is presentation-only. It does not fetch, persist, reorder,
 * mark scans terminal, or interpret crawler state. The parent supplies the
 * already-authoritative repair item and may optionally provide expanded detail
 * content once that detail seam is migrated.
 */
export default function CanonicalRepairRow({ item, model: suppliedModel, renderDetails }) {
  const model = useMemo(() => suppliedModel || repairRowModel(item), [item, suppliedModel]);
  const [open, setOpen] = useState(false);
  const hasDetails = typeof renderDetails === "function";
  const supporting = [model.surface, model.scope].filter(Boolean).join(" · ");

  return (
    <div className="border-b border-hairline-soft">
      <button
        type="button"
        aria-expanded={hasDetails ? open : undefined}
        onClick={() => {
          if (hasDetails) setOpen((value) => !value);
        }}
        className={`w-full py-4 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink ${hasDetails ? "cursor-pointer" : "cursor-default"}`}
      >
        <span className="flex items-start gap-3">
          <span className="min-w-0 flex-1">
            <span className="block text-[15px] font-medium leading-snug tracking-tight text-ink">
              {model.title}
            </span>
            {supporting ? (
              <span className="mt-1 block text-[12px] leading-relaxed text-ink-faint">
                {supporting}
              </span>
            ) : null}
            {model.reason ? (
              <span className="mt-1.5 block text-[13px] leading-relaxed text-ink-muted">
                {model.reason}
              </span>
            ) : null}
            {model.verification ? (
              <span className="mt-1.5 block text-[11px] font-medium uppercase tracking-[0.06em] text-ink-faint">
                {model.verification}
              </span>
            ) : null}
          </span>
          {hasDetails ? (
            <span
              aria-hidden="true"
              className={`mt-0.5 shrink-0 text-[13px] leading-none text-ink-faint transition-transform ${open ? "rotate-90" : ""}`}
            >
              ›
            </span>
          ) : null}
        </span>
      </button>
      {hasDetails && open ? <div className="pb-5">{renderDetails({ item, model })}</div> : null}
    </div>
  );
}
