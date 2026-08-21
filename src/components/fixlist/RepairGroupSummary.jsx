import React from "react";

/**
 * Rollup for repairs that are the same shared problem.
 *
 * This is a summary, never a replacement: each repair it counts is still
 * rendered as its own row below, with its own evidence, affected URLs,
 * detection details, priority, and verification state. Nothing here merges or
 * hides a repair, and no grouping happens in the scanner or the scoring model.
 *
 * The group states the shared action once and carries the scope, effort, and
 * owner for the whole set, so the rows beneath it can stay short and be read
 * as evidence.
 */
export default function RepairGroupSummary({ groups = [] }) {
  const list = Array.isArray(groups) ? groups.filter(Boolean) : [];
  if (list.length === 0) return null;

  return (
    <div className="mt-4 space-y-3">
      {list.map((group) => {
        const impact = [
          group.pageCount > 0
            ? `${group.pageCount}${group.pageCountExact === false ? "+" : ""} ${group.pageCount === 1 ? "page" : "pages"} affected`
            : "",
          group.templateCount > 0
            ? `${group.templateCount} ${group.templateCount === 1 ? "template" : "templates"} affected`
            : "",
        ].filter(Boolean);

        const facts = [
          { label: "Fix scope", value: group.fixScopeLabel },
          { label: "Effort", value: group.effortDisplay },
          { label: "Who should fix", value: group.role },
        ].filter((fact) => Boolean(fact.value));

        return (
          <div key={group.key} className="rounded-xl border border-hairline-soft bg-white/60 px-4 py-4 sm:px-5">
            <p className="text-[17px] font-semibold leading-snug tracking-tight text-ink">
              {group.title}
            </p>
            {impact.length > 0 ? (
              <div className="mt-1.5 space-y-0.5">
                {impact.map((line) => (
                  <p key={line} className="text-[13px] tabular-nums leading-snug text-ink-muted">{line}</p>
                ))}
              </div>
            ) : null}
            {group.fixOnce ? (
              <p className="mt-3 text-[13.5px] leading-relaxed text-ink">
                <span className="text-ink-faint">Suggested fix · </span>{group.fixOnce}
              </p>
            ) : null}
            {facts.length > 0 ? (
              <p className="mt-1.5 text-[12px] leading-relaxed text-ink-faint">
                {facts.map((fact) => `${fact.label}: ${fact.value}`).join(" · ")}
              </p>
            ) : null}
            <p className="mt-3 border-t border-hairline-soft pt-2.5 text-[11.5px] leading-relaxed text-ink-faint">
              Evidence for each of the {group.repairCount} repairs below, with its own affected URLs.
            </p>
          </div>
        );
      })}
    </div>
  );
}
