import React, { useState } from "react";
import { buildImplementationPlan } from "../../lib/implementationPlan.js";
import { repairRoleExplanation, REPAIR_EXPLANATION_ROLES, REPAIR_ROLE_VIEW_COPY } from "../../lib/repairRoleExplanations.js";
import { repairSuggestion } from "../../lib/repairSuggestions.js";
import { RepairRoleSelector } from "./RepairRoleView.jsx";

const text = (value) => typeof value === "string" ? value.trim() : "";
const object = (value) => value && typeof value === "object" && !Array.isArray(value);

function scanBound(items, cards, trustedScanId, sourceScanId, cardsScanId, authorityVerified) {
  if (authorityVerified !== true || !text(trustedScanId) || text(trustedScanId) !== trustedScanId) return false;
  // V8 authenticates the complete snapshot, not a fabricated identity on each
  // recommendation. Callers pass the producer identity for both populations.
  if (sourceScanId !== trustedScanId || cardsScanId !== trustedScanId) return false;
  if (!Array.isArray(items) || items.length === 0) return false;
  if (!Array.isArray(cards)) return false;
  return [...items, ...cards].every((item) => {
    if (!object(item)) return false;
    const identities = [item.scan_id, item.scanId, item.scan_run_id, item.scanRunId,
      item.original?.scan_id, item.original?.scanId, item.original?.scan_run_id, item.original?.scanRunId]
      .filter((value) => value !== undefined && value !== null && value !== "");
    return identities.every((value) => value === trustedScanId);
  });
}

function planFor(items, trustedScanId) {
  const byId = new Map();
  for (const item of items) {
    // Match the planner's documented identity precedence. Do not associate a
    // projected card by array index, rule, title, or a generated row identity.
    const id = text(item.id || item.fix_id || item.repair_fingerprint);
    if (!id || byId.has(id)) return null;
    byId.set(id, item);
  }
  const plan = buildImplementationPlan(items, { trustedScanId });
  if (!plan.priorityMonotonicOrExplicit || plan.orderedRepairIds.length !== byId.size
    || new Set(plan.orderedRepairIds).size !== byId.size
    || plan.orderedRepairIds.some((id) => !byId.has(id))) return null;
  return { plan, byId };
}

function rowTitle(item) {
  return text(item.title) || text(item.issue_title) || "Review this repair";
}

function ImplementationOrder({ items, trustedScanId }) {
  const model = planFor(items, trustedScanId);
  if (!model) return null;
  const { plan, byId } = model;
  return (
    <details className="mb-6 rounded-xl border border-hairline-soft bg-white/40 px-4 py-3">
      <summary className="cursor-pointer text-sm font-medium text-ink">Implementation order</summary>
      <p className="mt-2 max-w-[64ch] text-[13px] leading-relaxed text-ink-muted">
        {plan.appliedDependencies.length > 0
          ? "Some repairs need another step first. The reasons are shown below; the FixList still shows each repair’s priority."
          : "Work through the repairs in their existing priority order. Check each affected page before making a change."}
      </p>
      <ol className="mt-3 list-decimal space-y-4 pl-5">
        {plan.orderedRepairIds.map((id) => {
          const item = byId.get(id);
          const instruction = repairSuggestion(item).suggestedFix;
          const dependencies = plan.appliedDependencies.filter((edge) => edge.afterFixId === id);
          const group = plan.groups.find((entry) => entry.repairIds.includes(id));
          const related = group?.repairIds.filter((other) => other !== id) || [];
          return (
            <li key={id} className="pl-1 text-[13px] leading-relaxed text-ink-muted">
              <p className="font-medium text-ink">{rowTitle(item)}</p>
              {instruction ? <p className="mt-1 whitespace-pre-line">{instruction}</p> : null}
              {dependencies.map((edge) => (
                <p key={`${edge.tableEdgeId}:${edge.beforeFixId}`} className="mt-1">
                  First: {rowTitle(byId.get(edge.beforeFixId))}. {edge.rationale}
                </p>
              ))}
              {related.length > 0 ? (
                <p className="mt-1 text-ink-faint">Related work: {related.map((other) => rowTitle(byId.get(other))).join("; ")}.</p>
              ) : null}
            </li>
          );
        })}
      </ol>
    </details>
  );
}

/**
 * Controlled view for existing card renderers. Projected cards and planner
 * source rows stay separate; no index/rule/title join is performed. The caller
 * owns its existing instructions, evidence, grouping and card order.
 */
export function CustomerRepairGuidanceView({
  sourceItems = [], cards = [], trustedScanId = "", sourceScanId = "", cardsScanId = "", authorityVerified = false,
  role = "owner", onRoleChange, renderCards, renderCard,
}) {
  const list = Array.isArray(cards) ? cards : [];
  const trusted = scanBound(sourceItems, cards, trustedScanId, sourceScanId, cardsScanId, authorityVerified);
  const selectedRole = REPAIR_EXPLANATION_ROLES.includes(role) ? role : "owner";
  const roleView = REPAIR_ROLE_VIEW_COPY[selectedRole];
  const roleCopyCount = trusted ? list.filter((card) => object(card) && repairRoleExplanation(card, selectedRole).explanationAvailable).length : 0;
  const explanationForCard = (card) => {
    const fallback = { explanation: text(card?.whyItMatters), explanationAvailable: false, explanationHeading: "Why it matters" };
    if (!trusted || !object(card)) return fallback;
    const copy = repairRoleExplanation(card, selectedRole);
    return copy.explanationAvailable
      ? { explanation: copy.explanation, explanationAvailable: true, explanationHeading: roleView.heading }
      : fallback;
  };
  const context = { role: selectedRole, explanationForCard };
  const content = typeof renderCards === "function"
    ? renderCards(list, context)
    : typeof renderCard === "function"
      ? list.map((card, index) => <React.Fragment key={index}>{renderCard(card, { role: selectedRole, ...explanationForCard(card) })}</React.Fragment>)
      : null;
  return (
    <>
      {roleCopyCount > 0 && typeof onRoleChange === "function" ? (
        <div className="mb-5">
          <RepairRoleSelector role={selectedRole} onRoleChange={onRoleChange} />
          <p role="status" className="mt-2 text-[13px] leading-relaxed text-ink-muted"><span className="font-medium text-ink">{roleView.label} view.</span> {roleView.summary}</p>
          <p className="mt-1 text-[12px] leading-relaxed text-ink-faint">Findings and recommended changes stay the same.{roleCopyCount < list.length ? ` Role guidance is available for ${roleCopyCount} of ${list.length} repairs.` : ""}</p>
        </div>
      ) : null}
      {trusted && list.length > 0 ? <ImplementationOrder items={sourceItems} trustedScanId={trustedScanId} /> : null}
      {content}
    </>
  );
}

function StatefulGuidance(props) {
  const [role, setRole] = useState("owner");
  return <CustomerRepairGuidanceView {...props} role={role} onRoleChange={setRole} />;
}

/** Authority is established by the owner-bound reader, never by this view. */
export default function CustomerRepairGuidance(props) {
  return <StatefulGuidance key={props.trustedScanId} {...props} />;
}
