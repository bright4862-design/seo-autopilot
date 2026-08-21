import React from "react";

/**
 * Rollup for repairs that are the same shared problem.
 *
 * This is a summary, never a replacement: each repair it counts is still
 * rendered as its own row below, with its own evidence, affected URLs,
 * detection details, priority, and verification state. Nothing here merges or
 * hides a repair, and no grouping happens in the scanner or the scoring model.
 */
export default function RepairGroupSummary({ groups = [] }) {
  const list = Array.isArray(groups) ? groups.filter(Boolean) : [];
  if (list.length === 0) return null;

  return (
    <div className="mt-3 space-y-2.5">
      {list.map((group) => {
        const impact = [
          group.pageCount > 0
            ? `${group.pageCount}${group.pageCountExact === false ? "+" : ""} ${group.pageCount === 1 ? "page" : "pages"} affected`
            : "",
          group.templateCount > 0
            ? `${group.templateCount} ${group.templateCount === 1 ? "template" : "templates"} affected`
            : "",
        ].filter(Boolean).join(" · ");

        return (
          <div key={group.key} className="rounded-lg border border-hairline-soft bg-white/50 px-4 py-3.5">
            <p className="text-[14px] font-medium leading-snug tracking-tight text-ink">
              {group.title}
            </p>
            {impact ? <p className="mt-1 text-[12px] tabular-nums text-ink-faint">{impact}</p> : null}
            {group.fixOnce ? (
              <p className="mt-2 text-[13px] leading-relaxed text-ink-muted">
                <span className="font-medium text-ink">Fix once: </span>{group.fixOnce}
              </p>
            ) : null}
            <p className="mt-2 text-[11.5px] leading-relaxed text-ink-faint">
              Each of the {group.repairCount} repairs below keeps its own evidence and affected URLs.
            </p>
          </div>
        );
      })}
    </div>
  );
}
