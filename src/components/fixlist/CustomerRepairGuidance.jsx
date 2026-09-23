import React, { useState } from "react";
import { buildImplementationPlan } from "../../lib/implementationPlan.js";
import { repairRoleExplanation, REPAIR_EXPLANATION_ROLES, REPAIR_ROLE_VIEW_COPY } from "../../lib/repairRoleExplanations.js";
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
  if (!model || model.plan.appliedDependencies.length === 0) return null;
  const { plan, byId } = model;
  return (
    <details className="mb-6 rounded-xl border border-hairline-soft bg-white/40 px-4 py-3">
      <summary className="cursor-pointer text-sm font-medium text-ink">Before you start</summary>
      <ul className="mt-3 space-y-4">
        {plan.appliedDependencies.map((edge) => (
          <li key={`${edge.tableEdgeId}:${edge.beforeFixId}:${edge.afterFixId}`} className="text-[13px] leading-relaxed text-ink-muted">
            <p>Complete <span className="font-medium text-ink">{rowTitle(byId.get(edge.beforeFixId))}</span> before <span className="font-medium text-ink">{rowTitle(byId.get(edge.afterFixId))}</span>.</p>
            <p className="mt-1">{edge.rationale}</p>
          </li>
        ))}
      </ul>
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
          {roleCopyCount < list.length ? <p className="mt-1 text-[12px] leading-relaxed text-ink-faint">Role guidance is available for {roleCopyCount} of {list.length} repairs.</p> : null}
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
