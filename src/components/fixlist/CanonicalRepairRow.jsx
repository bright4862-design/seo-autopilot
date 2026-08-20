import React, { useId, useMemo, useState } from "react";

import { canonicalRepairDisplayModel } from "@/lib/canonicalRepairDisplay";

/**
 * Compact action-priority row for the canonical FixList presentation.
 *
 * This component is presentation-only. It does not fetch, persist, reorder,
 * mark scans terminal, or interpret crawler state. The parent supplies the
 * already-authoritative repair item and may optionally provide expanded detail
 * content once that detail seam is migrated.
 */
export default function CanonicalRepairRow({ item, model: suppliedModel, renderDetails }) {
  const model = useMemo(
    () => canonicalRepairDisplayModel(item, suppliedModel),
    [item, suppliedModel],
  );
  const [open, setOpen] = useState(false);
  const disclosureId = useId();
  const hasDetails = typeof renderDetails === "function";
  const supporting = [model.surface, model.scope, model.evidenceLabel].filter(Boolean).join(" · ");

  return (
    <div className="border-b border-hairline-soft">
      <button
        type="button"
        aria-expanded={hasDetails ? open : undefined}
        aria-controls={hasDetails ? disclosureId : undefined}
        aria-label={hasDetails ? `${open ? "Hide" : "Show"} evidence and steps for ${model.title}` : undefined}
        onClick={() => {
          if (hasDetails) setOpen((value) => !value);
        }}
        className={`min-h-11 w-full py-3.5 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink sm:py-4 ${hasDetails ? "cursor-pointer" : "cursor-default"}`}
      >
        <span className="block min-w-0">
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
              <span className="text-ink-faint">Why this is here · </span>{model.reason}
            </span>
          ) : null}
          {model.leverage ? (
            <span className="mt-1.5 block text-[12px] leading-relaxed text-ink-muted">
              {model.leverage}
            </span>
          ) : null}
          {model.verification ? (
            <span className="mt-2 block text-[12px] font-medium leading-relaxed text-ink-muted">
              <span className="text-ink-faint">Verification · </span>{model.verification}
            </span>
          ) : null}
          {hasDetails ? (
            <span className="mt-2 flex items-center gap-1.5 text-[11px] font-medium text-ink-faint">
              {open ? "Hide evidence & steps" : "Evidence & steps"}
              <span
                aria-hidden="true"
                className={`inline-block leading-none transition-transform ${open ? "rotate-90" : ""}`}
              >
                ›
              </span>
            </span>
          ) : null}
        </span>
      </button>
      {hasDetails && open ? (
        <div
          id={disclosureId}
          role="region"
          aria-label={`Evidence and steps for ${model.title}`}
          className="mb-2 border-l border-hairline-soft pb-5 pl-4 sm:pl-5"
        >
          {renderDetails({ item, model })}
        </div>
      ) : null}
    </div>
  );
}
