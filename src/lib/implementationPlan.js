/**
 * Deterministic implementation sequencing over already-canonical repair rows.
 *
 * The input row order is the canonical priority baseline. This module never
 * computes a competing priority score and never mutates a repair. Reordering is
 * permitted only by an explicit, versioned dependency edge whose evidence
 * predicate is satisfied. Cycles fail safely back to the canonical input order.
 */
export const IMPLEMENTATION_PLAN_VERSION = "implementation_plan_v1";
export const IMPLEMENTATION_DEPENDENCY_TABLE_VERSION = "implementation_dependencies_v1_final_url_first";

export const IMPLEMENTATION_DEPENDENCY_EDGES = Object.freeze([
  Object.freeze({
    tableVersion: IMPLEMENTATION_DEPENDENCY_TABLE_VERSION,
    id: "redirect_chain_before_sitemap_redirect",
    beforeRule: "redirect_chain",
    afterRule: "sitemap_redirect",
    requires: "verified_shared_root_cause",
    rationale: "Stabilize the final redirect destination before publishing that destination in the sitemap.",
  }),
  Object.freeze({
    tableVersion: IMPLEMENTATION_DEPENDENCY_TABLE_VERSION,
    id: "redirect_chain_before_internal_link_redirect",
    beforeRule: "redirect_chain",
    afterRule: "internal_link_redirect",
    requires: "verified_shared_root_cause",
    rationale: "Stabilize the final redirect destination before replacing internal links with that destination.",
  }),
]);

const ACTION_PRIORITY_RANK = Object.freeze({ fix_first: 4, important: 3, improve: 2, review: 1 });
const VERIFIED_ROOT_CAUSE_VERSION = "root_cause_evidence_v1_verified";
const VERIFIED_STATES = new Set(["confirmed", "verified"]);

function clean(value = "") {
  return String(value || "").trim();
}

function strictText(value) {
  return typeof value === "string" ? value.trim() : "";
}

function lower(value = "") {
  return strictText(value).toLowerCase();
}

function idOf(item = {}, index = 0) {
  return clean(item.id || item.fix_id || item.repair_fingerprint) || `row:${index}`;
}

function ruleOf(item = {}) {
  return lower(item.rule || item.rule_id || item.issue_type || item.original?.rule || item.original?.rule_id);
}

function actionPriorityOf(item = {}) {
  const value = lower(
    item.actionPriority
      || item.action_priority
      || item.priorityContext?.action_priority
      || item.priority_context?.action_priority
      || item.original?.action_priority,
  );
  return ACTION_PRIORITY_RANK[value] ? value : "";
}

function repairSurfaceOf(item = {}) {
  return lower(
    item.repairSurface
      || item.repair_surface
      || item.implementation_surface
      || item.original?.repair_surface,
  );
}

function remediationFamilyOf(item = {}) {
  return lower(item.remediationFamily || item.remediation_family || item.original?.remediation_family);
}

function pageFamilyOf(item = {}) {
  return lower(
    item.pageTemplateFamily
      || item.page_template_family
      || item.templateFamily
      || item.original?.page_template_family,
  );
}

function localScanIdentityValuesOf(item = {}) {
  return [
    item.scan_id,
    item.scanId,
    item.scan_run_id,
    item.scanRunId,
    item.original?.scan_id,
    item.original?.scanId,
    item.original?.scan_run_id,
    item.original?.scanRunId,
  ];
}

function matchesTrustedScanIdentity(item = {}, trustedScanId = "") {
  const trusted = strictText(trustedScanId);
  if (!trusted) return false;

  // Treat every published scan-identity alias as a consistency assertion. A
  // trusted value in one field must never hide a conflicting or malformed value
  // in another alias, including the original repair payload.
  for (const value of localScanIdentityValuesOf(item)) {
    if (value === undefined || value === null) continue;
    if (typeof value !== "string") return false;
    const local = value.trim();
    if (!local) continue;
    if (local !== trusted) return false;
  }
  return true;
}

function rootCauseEvidenceOf(item = {}, trustedScanId = "") {
  const evidence = item.rootCauseEvidence || item.root_cause_evidence || item.original?.root_cause_evidence;
  if (!evidence || typeof evidence !== "object" || Array.isArray(evidence)) return null;
  if (evidence.version !== VERIFIED_ROOT_CAUSE_VERSION) return null;
  if (!VERIFIED_STATES.has(lower(evidence.state))) return null;

  const rootCauseId = strictText(evidence.root_cause_id);
  if (!rootCauseId) return null;

  const refs = Array.isArray(evidence.evidence_refs)
    ? evidence.evidence_refs.map(strictText)
    : [];
  if (refs.length === 0 || refs.some((ref) => !ref)) return null;

  // B20 root-cause authority is scan-bound. A pure presentation/planning helper
  // cannot establish that boundary by itself, so callers must pass the exact
  // scan identity already authenticated by the owner-bound V8 reader. Missing
  // trusted identity fails closed. Repair-local identities, when present, are
  // consistency assertions only and must match exactly.
  if (!matchesTrustedScanIdentity(item, trustedScanId)) return null;

  return {
    rootCauseId,
    repairSurfaceId: strictText(evidence.repair_surface_id),
  };
}

function groupingKeyOf(item = {}, index = 0, trustedScanId = "") {
  const root = rootCauseEvidenceOf(item, trustedScanId);
  if (root) return `root_cause:${root.rootCauseId}`;

  // Surface/remediation grouping is presentation-only, but it still must be
  // bounded to the authenticated scan context. Missing trusted identity or a
  // conflicting repair-local identity fails closed to a singleton group rather
  // than allowing work from another run to be bundled together accidentally.
  if (!matchesTrustedScanIdentity(item, trustedScanId)) {
    return `repair:${idOf(item, index)}\u0000${index}`;
  }

  // A page/template family by itself is intentionally insufficient. Only an
  // explicit repair surface plus an explicit remediation family can form a
  // shared implementation group without verified root-cause evidence.
  const surface = repairSurfaceOf(item);
  const remediationFamily = remediationFamilyOf(item);
  if (surface && remediationFamily) return `surface:${surface}\u0000remediation:${remediationFamily}`;

  return `repair:${idOf(item, index)}\u0000${index}`;
}

function pairHasRequiredEvidence(left, right, edge) {
  if (edge.requires !== "verified_shared_root_cause") return false;
  return Boolean(left.rootCauseId && right.rootCauseId && left.rootCauseId === right.rootCauseId);
}

function normalizedEdge(edge = {}) {
  if (!edge || typeof edge !== "object" || Array.isArray(edge)) return null;
  const tableVersion = strictText(edge.tableVersion || edge.table_version);
  const id = strictText(edge.id);
  const beforeRule = lower(edge.beforeRule || edge.before_rule);
  const afterRule = lower(edge.afterRule || edge.after_rule);
  const requires = strictText(edge.requires);
  const rationale = strictText(edge.rationale);
  if (!tableVersion || !id || !beforeRule || !afterRule || !requires) return null;
  return { tableVersion, id, beforeRule, afterRule, requires, rationale };
}

function instantiateEdges(nodes, dependencyEdges, dependencyTableVersion) {
  const instantiated = [];
  const selectedTableVersion = strictText(dependencyTableVersion);
  if (!selectedTableVersion) return instantiated;

  for (const rawEdge of Array.isArray(dependencyEdges) ? dependencyEdges : []) {
    const edge = normalizedEdge(rawEdge);
    if (!edge || edge.tableVersion !== selectedTableVersion) continue;
    for (const before of nodes) {
      if (before.rule !== edge.beforeRule) continue;
      for (const after of nodes) {
        if (after.rule !== edge.afterRule || before.key === after.key) continue;
        if (!pairHasRequiredEvidence(before, after, edge)) continue;
        instantiated.push({
          id: `${edge.id}:${before.key}->${after.key}`,
          tableVersion: edge.tableVersion,
          tableEdgeId: edge.id,
          beforeKey: before.key,
          afterKey: after.key,
          beforeFixId: before.fixId,
          afterFixId: after.fixId,
          rationale: edge.rationale,
        });
      }
    }
  }
  return instantiated;
}

function stableTopologicalOrder(nodes, edges) {
  const byKey = new Map(nodes.map((node) => [node.key, node]));
  const prerequisites = new Map(nodes.map((node) => [node.key, []]));

  for (const edge of edges) {
    if (!byKey.has(edge.beforeKey) || !byKey.has(edge.afterKey)) continue;
    prerequisites.get(edge.afterKey).push(edge.beforeKey);
  }
  for (const requiredKeys of prerequisites.values()) {
    requiredKeys.sort((left, right) => byKey.get(left).canonicalIndex - byKey.get(right).canonicalIndex);
  }

  // Walk the canonical rows in order and pull only each row's prerequisites
  // forward. This avoids Kahn-style ready queues delaying a high-priority
  // dependent behind unrelated rows just because its prerequisite was later in
  // canonical order. A cycle still fails closed to the untouched input order.
  const state = new Map();
  const ordered = [];
  let cycleDetected = false;

  function visit(node) {
    const currentState = state.get(node.key) || 0;
    if (currentState === 2 || cycleDetected) return;
    if (currentState === 1) {
      cycleDetected = true;
      return;
    }

    state.set(node.key, 1);
    for (const prerequisiteKey of prerequisites.get(node.key) || []) {
      const prerequisite = byKey.get(prerequisiteKey);
      if (prerequisite) visit(prerequisite);
      if (cycleDetected) return;
    }
    state.set(node.key, 2);
    ordered.push(node);
  }

  for (const node of [...nodes].sort((a, b) => a.canonicalIndex - b.canonicalIndex)) {
    visit(node);
    if (cycleDetected) break;
  }

  return cycleDetected ? { ordered: nodes, cycleDetected: true } : { ordered, cycleDetected: false };
}

function groupOrderedNodes(ordered) {
  const groups = new Map();
  const sequence = [];
  ordered.forEach((node, planIndex) => {
    const key = node.groupingKey;
    if (!groups.has(key)) {
      const group = {
        key,
        firstPlanIndex: planIndex,
        repairIds: [],
        rules: [],
        repairSurface: node.repairSurface,
        remediationFamily: node.remediationFamily,
        rootCauseId: node.rootCauseId,
        pageFamilies: [],
      };
      groups.set(key, group);
      sequence.push(group);
    }
    const group = groups.get(key);
    group.repairIds.push(node.fixId);
    if (node.rule && !group.rules.includes(node.rule)) group.rules.push(node.rule);
    if (node.pageFamily && !group.pageFamilies.includes(node.pageFamily)) group.pageFamilies.push(node.pageFamily);
  });
  return sequence;
}

function inversionHasDependencyPath(ordered, edges) {
  const byKey = new Map(ordered.map((node) => [node.key, node]));
  const adjacency = new Map(ordered.map((node) => [node.key, []]));
  for (const edge of edges) adjacency.get(edge.beforeKey)?.push(edge.afterKey);

  function reachesCanonicalBoundary(fromKey, maxCanonicalIndex) {
    const seen = new Set();
    const stack = [...(adjacency.get(fromKey) || [])];
    while (stack.length) {
      const current = stack.pop();
      if (seen.has(current)) continue;
      seen.add(current);
      const node = byKey.get(current);
      if (node && node.canonicalIndex <= maxCanonicalIndex) return true;
      stack.push(...(adjacency.get(current) || []));
    }
    return false;
  }

  for (let left = 0; left < ordered.length; left += 1) {
    for (let right = left + 1; right < ordered.length; right += 1) {
      const a = ordered[left];
      const b = ordered[right];
      const aRank = ACTION_PRIORITY_RANK[a.actionPriority] || 0;
      const bRank = ACTION_PRIORITY_RANK[b.actionPriority] || 0;
      if (aRank >= bRank) continue;
      // Only a real priority inversion needs justification: the higher-priority
      // row originally preceded the lower-priority row in canonical order.
      if (a.canonicalIndex < b.canonicalIndex) continue;
      // A prerequisite may move ahead of unrelated rows only when it is needed
      // to unlock a dependent that was canonically at or before the row it
      // crossed. This keeps collateral movement tied to a real dependency.
      if (!reachesCanonicalBoundary(a.key, b.canonicalIndex)) return false;
    }
  }
  return true;
}

export function buildImplementationPlan(
  items = [],
  {
    dependencyEdges = IMPLEMENTATION_DEPENDENCY_EDGES,
    dependencyTableVersion = IMPLEMENTATION_DEPENDENCY_TABLE_VERSION,
    trustedScanId = "",
  } = {},
) {
  const rows = Array.isArray(items) ? items.filter(Boolean) : [];
  const nodes = rows.map((item, canonicalIndex) => {
    const rootCause = rootCauseEvidenceOf(item, trustedScanId);
    return {
      key: `node:${canonicalIndex}:${idOf(item, canonicalIndex)}`,
      item,
      fixId: idOf(item, canonicalIndex),
      rule: ruleOf(item),
      actionPriority: actionPriorityOf(item),
      canonicalIndex,
      repairSurface: repairSurfaceOf(item),
      remediationFamily: remediationFamilyOf(item),
      pageFamily: pageFamilyOf(item),
      rootCauseId: rootCause?.rootCauseId || "",
      groupingKey: groupingKeyOf(item, canonicalIndex, trustedScanId),
    };
  });

  const selectedDependencyTableVersion = strictText(dependencyTableVersion);
  const appliedEdges = instantiateEdges(nodes, dependencyEdges, selectedDependencyTableVersion);
  const topo = stableTopologicalOrder(nodes, appliedEdges);
  const ordered = topo.cycleDetected ? nodes : topo.ordered;
  const priorityMonotonicOrExplicit = topo.cycleDetected ? true : inversionHasDependencyPath(ordered, appliedEdges);

  return Object.freeze({
    version: IMPLEMENTATION_PLAN_VERSION,
    dependencyTableVersion: selectedDependencyTableVersion,
    cycleDetected: topo.cycleDetected,
    fallbackUsed: topo.cycleDetected,
    priorityMonotonicOrExplicit,
    orderedRepairIds: ordered.map((node) => node.fixId),
    appliedDependencies: topo.cycleDetected ? [] : appliedEdges.map((edge) => Object.freeze({
      tableVersion: edge.tableVersion,
      tableEdgeId: edge.tableEdgeId,
      beforeFixId: edge.beforeFixId,
      afterFixId: edge.afterFixId,
      rationale: edge.rationale,
    })),
    groups: groupOrderedNodes(ordered).map((group) => Object.freeze({
      ...group,
      repairIds: Object.freeze([...group.repairIds]),
      rules: Object.freeze([...group.rules]),
      pageFamilies: Object.freeze([...group.pageFamilies]),
    })),
  });
}
