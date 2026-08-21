import React from "react";

/**
 * Rollup for repairs that are the same template problem.
 *
 * This is a summary, never a replacement: each repair it counts is still
 * rendered as its own row below, with its own evidence, priority, and
 * verification state. Nothing here merges or hides a repair.
 */
export default function RepairGroupSummary({ groups = [] }) {
  const list = Array.isArray(groups) ? groups.filter(Boolean) : [];
  if (list.length === 0) return null;

  return (
    <div className="mt-3 space-y-2.5">
      {list.map((group) => {
        const scope = [
          group.pageCount > 0
            ? `${group.pageCount}${group.pageCountExact === false ? "+" : ""} ${group.pageCount === 1 ? "page" : "pages"} affected`
            : "",
          group.templateCount > 0
            ? `${group.templateCount} ${group.templateCount === 1 ? "page template" : "page templates"} affected`
            : "",
          `${group.repairCount} ${group.repairCount === 1 ? "repair" : "repairs"} below`,
        ].filter(Boolean).join(" · ");

        return (
          <div key={group.key} className="rounded-lg border border-hairline-soft bg-white/50 px-4 py-3.5">
            <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">
              Fix once
            </div>
            <p className="mt-1 text-[14px] font-medium leading-snug tracking-tight text-ink">
              {group.title}
            </p>
            <p className="mt-1 text-[12px] tabular-nums text-ink-faint">{scope}</p>
            {group.fixOnce ? (
              <p className="mt-2 text-[13px] leading-relaxed text-ink-muted">{group.fixOnce}</p>
            ) : null}
            <p className="mt-2 text-[11.5px] leading-relaxed text-ink-faint">
              Each repair below keeps its own evidence and can still be fixed on its own.
            </p>
          </div>
        );
      })}
    </div>
  );
}
