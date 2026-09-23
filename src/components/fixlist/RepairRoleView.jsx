import { REPAIR_EXPLANATION_ROLES, REPAIR_ROLE_VIEW_COPY } from "../../lib/repairRoleExplanations.js";
import { repairRolePresentation } from "../../lib/repairRolePresentation.js";

/** Controlled per-view preference; never persisted or sent to a model. */
export function RepairRoleSelector({ role = "owner", onRoleChange, disabled = false }) {
  const selected = REPAIR_EXPLANATION_ROLES.includes(role) ? role : "";
  return (
    <label className="flex flex-col gap-2 text-sm font-medium text-slate-700 sm:flex-row sm:items-center">
      Explain for
      <select
        value={selected}
        disabled={disabled || typeof onRoleChange !== "function"}
        onChange={(event) => {
          const next = event.target.value;
          if (!disabled && REPAIR_EXPLANATION_ROLES.includes(next) && typeof onRoleChange === "function") {
            onRoleChange(next);
          }
        }}
        className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-slate-400 disabled:opacity-60"
      >
        {!selected && <option value="" disabled>Choose a role</option>}
        {REPAIR_EXPLANATION_ROLES.map((value) => <option key={value} value={value}>{REPAIR_ROLE_VIEW_COPY[value].label}</option>)}
      </select>
    </label>
  );
}

/**
 * Consume an already-authenticated repair. This is additive explanation copy,
 * not a replacement for the parent card's evidence, counts or canonical rank.
 */
export function RepairRoleExplanation({ repair, role = "owner" }) {
  if (!repair || typeof repair !== "object" || Array.isArray(repair)) return null;
  const model = repairRolePresentation(repair, role);
  return (
    <div className="space-y-4 text-sm leading-relaxed text-slate-700">
      <div>
        <h3 className="font-semibold text-slate-900">{model.explanation.explanationAvailable ? REPAIR_ROLE_VIEW_COPY[model.role].heading : "What this means"}</h3>
        <p className="mt-1 whitespace-pre-line">{model.explanation.explanation}</p>
      </div>
      <div>
        <h3 className="font-semibold text-slate-900">Recommended next step</h3>
        <p className="mt-1 whitespace-pre-line">{model.suggestion.suggestedFix}</p>
      </div>
    </div>
  );
}
