import { customerPriorityReason, priorityBucket } from "./fixRanking.js";
import { buildRepairGroupSummaries, repairSuggestion } from "./repairSuggestions.js";
import {
  REPAIR_PRESENTATION_MODES,
  explicitCanonicalActionPriorityOf,
  explicitCanonicalPriorityReasonOf,
  repairPresentationMode,
  repairSnapshotPresentationMode,
} from "./repairContractPresentation.js";

export const REPAIR_PRESENTATION_VERSION = "repair_presentation_v5_evidence_groups_canonical_export";

const SECTION_ORDER = ["fix_first", "important", "improve", "review"];

const SECTION_LABELS = Object.freeze({
  fix_first: "Fix first",
  important: "Important",
  improve: "Improve",
  review: "Review",
});

const VERIFICATION_LABELS = Object.freeze({
  verified_fixed: "Verified fixed",
  still_detected: "Still detected",
  came_back: "Came back",
  could_not_verify: "Could not verify",
  could_not_compare: "Could not compare",
  ready_to_verify: "Ready to verify with a rescan",
});

const VERIFICATION_KINDS = Object.freeze({
  verified_fixed: "verified",
  still_detected: "detected",
  came_back: "detected",
  could_not_verify: "uncertain",
  could_not_compare: "uncertain",
  ready_to_verify: "pending",
});

function clean(value = "") {
  return String(value || "").trim();
}

function affectedPages(item = {}) {
  const values = item.affectedPages || item.affected_pages || item.original?.affected_pages || [];
  return Array.isArray(values) ? values.filter(Boolean).map(String) : [];
}

function pageCount(item = {}) {
  const reported = Number(item.pageCount ?? item.page_count ?? item.original?.page_count ?? 0);
  return Math.max(Number.isFinite(reported) ? reported : 0, affectedPages(item).length);
}

function contextOf(item = {}) {
  return item.priorityContext || item.priority_context || item.original?.priority_context || {};
}

function familyOf(item = {}) {
  return clean(
    item.pageTemplateFamily
      || item.page_template_family
      || item.original?.page_template_family,
  ).toLowerCase();
}

function persistedSharedRepairConfirmedOf(item = {}) {
  const original = item?.original;
  if (!original || typeof original !== "object") return null;
  const originalContext = original.priorityContext || original.priority_context || {};
  return Boolean(
    original.sharedRepairConfirmed
      || original.shared_repair_confirmed
      || original.repairLeverageConfirmed
      || original.repair_leverage_confirmed
      || originalContext.shared_repair_confirmed,
  );
}

function sharedRepairConfirmedOf(item = {}) {
  if (repairPresentationMode(item) === REPAIR_PRESENTATION_MODES.CANONICAL) {
    const persisted = persistedSharedRepairConfirmedOf(item);
    if (persisted !== null) return persisted;
  }

  return Boolean(
    item.sharedRepairConfirmed
      || item.shared_repair_confirmed
      || item.repairLeverageConfirmed
      || item.repair_leverage_confirmed
      || contextOf(item).shared_repair_confirmed,
  );
}

function presentationActionPriorityOf(item = {}) {
  if (repairPresentationMode(item) === REPAIR_PRESENTATION_MODES.CANONICAL) {
    return explicitCanonicalActionPriorityOf(item);
  }
  return priorityBucket(item);
}

function presentationPriorityReasonOf(item = {}) {
  if (repairPresentationMode(item) === REPAIR_PRESENTATION_MODES.CANONICAL) {
    return explicitCanonicalPriorityReasonOf(item);
  }
  return customerPriorityReason(item);
}

export function repairSurfaceLabel(item = {}) {
  const explicit = clean(
    item.repairSurface
      || item.repair_surface
      || item.implementation_surface
      || item.original?.repair_surface,
  );
  if (explicit) {
    return explicit
      .replace(/[_-]+/g, " ")
      .replace(/\b\w/g, (letter) => letter.toUpperCase());
  }

  const family = familyOf(item);
  return ({
    homepage: "Homepage",
    product_page: "Product pages",
    collection_page: "Collection pages",
    activity_detail: "Activity pages",
    loan_program: "Loan pages",
    guide_article: "Guide pages",
    location_landing: "Location pages",
    booking_or_checkout: "Booking pages",
    // Matches the customer vocabulary used on the card itself: "conversion" and
    // "route boundary" are both internal names for things an owner recognises
    // by what they do.
    conversion: "Sign-up and contact pages",
    route_boundary: "Website sections",
    mixed: "Multiple page types",
    sitewide: "Site-wide",
  })[family] || "";
}

export function repairScopeSummary(item = {}) {
  const context = contextOf(item);
  const searchableAffected = Number(context.indexable_affected ?? 0);
  const searchableEligible = Number(context.indexable_checked_eligible ?? 0);
  if (searchableAffected > 0 && searchableEligible >= searchableAffected) {
    return `${searchableAffected} of ${searchableEligible} searchable pages checked`;
  }

  const affectedChecked = Number(context.affected_checked ?? 0);
  const checkedEligible = Number(context.checked_eligible ?? 0);
  if (affectedChecked > 0 && checkedEligible >= affectedChecked) {
    return `${affectedChecked} of ${checkedEligible} relevant pages checked`;
  }

  const count = pageCount(item);
  if (count === 1) return "1 page";
  if (count > 1) return `${count} pages`;
  return "";
}

export function repairLeverageSummary(item = {}) {
  const count = pageCount(item);
  const reason = presentationPriorityReasonOf(item).toLowerCase();
  if (!sharedRepairConfirmedOf(item) || count < 2) return "";
  if (reason.includes("one shared change")) return "";
  return `One shared change may improve ${count} affected pages`;
}

function comparisonContractStateOf(item = {}) {
  return clean(
    item.comparisonContractState
      || item.comparison_contract_state
      || item.repair_verification?.comparison_contract_state
      || item.original?.comparison_contract_state,
  ).toLowerCase();
}

function verificationStateOf(item = {}) {
  return clean(
    item.repairVerificationState
      || item.repair_verification_state
      || item.verification_state
      || item.original?.repair_verification_state,
  ).toLowerCase();
}

export function repairVerificationLabel(item = {}) {
  const state = verificationStateOf(item);
  if (state === "could_not_verify" && comparisonContractStateOf(item) === "incomparable") {
    return "Could not compare";
  }
  return VERIFICATION_LABELS[state] || "";
}

export function repairVerificationKind(item = {}) {
  const state = verificationStateOf(item);
  if (state === "could_not_verify" && comparisonContractStateOf(item) === "incomparable") {
    return "uncertain";
  }
  return VERIFICATION_KINDS[state] || "";
}

export function repairRowModel(item = {}) {
  const actionPriority = presentationActionPriorityOf(item);
  const sharedRepairConfirmed = sharedRepairConfirmedOf(item);
  return {
    version: REPAIR_PRESENTATION_VERSION,
    id: clean(item.id || item.fix_id || item.repair_fingerprint),
    title: clean(item.issueTitle || item.issue_title || item.title) || "Review this repair",
    actionPriority,
    sectionLabel: SECTION_LABELS[actionPriority] || "Important",
    surface: repairSurfaceLabel(item),
    scope: repairScopeSummary(item),
    reason: presentationPriorityReasonOf(item),
    leverage: repairLeverageSummary(item),
    verification: repairVerificationLabel(item),
    verificationKind: repairVerificationKind(item),
    affectedPageCount: pageCount(item),
    groupedFindingCount: Number(item.groupedFindingCount ?? item.grouped_finding_count ?? 0) || 0,
    sharedRepairConfirmed,
  };
}

/**
 * Attach the deterministic suggested fix to a presentation row.
 *
 * The suggestion is derived from evidence the repair already carries, so it is
 * additive: nothing on the item, the row model, or the persisted repair is
 * replaced by it.
 */
function presentationRow(item) {
  return { item, model: repairRowModel(item), suggestion: repairSuggestion(item) };
}

export function sectionCustomerRepairs(items = [], { initialFixFirstLimit = 3 } = {}) {
  const buckets = new Map(SECTION_ORDER.map((key) => [key, []]));
  for (const item of Array.isArray(items) ? items : []) {
    if (!item) continue;
    const row = presentationRow(item);
    const key = SECTION_ORDER.includes(row.model.actionPriority) ? row.model.actionPriority : "important";
    buckets.get(key).push(row);
  }

  return SECTION_ORDER
    .map((key) => {
      const bucketRows = buckets.get(key) || [];
      // Summary only. Every row stays visible with its own evidence; rows are
      // marked so the shared suggested fix is stated once by the summary
      // instead of repeating verbatim on each grouped row.
      const groups = buildRepairGroupSummaries(bucketRows);
      const groupedIds = new Set(groups.flatMap((group) => group.memberIds));
      const rows = bucketRows.map((row) => ({
        ...row,
        groupedUnderSummary: groupedIds.has(row.model.id),
      }));
      const visibleLimit = key === "fix_first" ? Math.max(1, Number(initialFixFirstLimit) || 3) : rows.length;
      return {
        key,
        label: SECTION_LABELS[key],
        rows: rows.slice(0, visibleLimit),
        hiddenRows: rows.slice(visibleLimit),
        hiddenCount: Math.max(0, rows.length - visibleLimit),
        totalCount: rows.length,
        groups,
      };
    })
    .filter((section) => section.totalCount > 0);
}

function snapshotModeMarker(items = []) {
  const list = Array.isArray(items) ? items.filter(Boolean) : [];
  if (list.length === 0) return "";

  const markers = list.map((item) => clean(
    item.repairSnapshotPresentationMode
      || item.repair_snapshot_presentation_mode,
  ));
  const present = markers.filter(Boolean);
  if (present.length === 0) return "";
  if (present.length !== list.length) return REPAIR_PRESENTATION_MODES.LEGACY;
  if (present.some((mode) => mode === REPAIR_PRESENTATION_MODES.UNSUPPORTED)) {
    return REPAIR_PRESENTATION_MODES.UNSUPPORTED;
  }
  if (present.every((mode) => mode === REPAIR_PRESENTATION_MODES.CANONICAL)) {
    return REPAIR_PRESENTATION_MODES.CANONICAL;
  }
  return REPAIR_PRESENTATION_MODES.LEGACY;
}

function presentationModeForItems(items = []) {
  const list = Array.isArray(items) ? items.filter(Boolean) : [];
  if (list.length === 0) return REPAIR_PRESENTATION_MODES.LEGACY;

  const markedSnapshotMode = snapshotModeMarker(list);
  const visibleRowsMode = repairSnapshotPresentationMode(list);
  if (!markedSnapshotMode) return visibleRowsMode;

  if (markedSnapshotMode === REPAIR_PRESENTATION_MODES.UNSUPPORTED) {
    return REPAIR_PRESENTATION_MODES.UNSUPPORTED;
  }
  if (markedSnapshotMode === REPAIR_PRESENTATION_MODES.LEGACY) {
    return REPAIR_PRESENTATION_MODES.LEGACY;
  }
  return visibleRowsMode;
}

/**
 * Safe integration seam for the live FixList page.
 *
 * The complete durable repair snapshot decides presentation authority. Workflow
 * state may hide rows from the visible list, but it must never change the
 * snapshot from legacy/mixed/unsupported to canonical (or vice versa).
 *
 * The preferred explicit API passes the full snapshot as the first argument and
 * `options.visibleItems` as the filtered customer work queue. The current live
 * page also receives an in-memory snapshot marker from `prepareCustomerFixes`,
 * so existing Done filtering cannot reclassify the saved scan before that caller
 * is migrated to the explicit form.
 */
export function buildFixListPresentation(snapshotItems = [], options = {}) {
  const snapshot = Array.isArray(snapshotItems) ? snapshotItems.filter(Boolean) : [];
  const visibleItems = Array.isArray(options.visibleItems)
    ? options.visibleItems.filter(Boolean)
    : snapshot;
  const mode = presentationModeForItems(snapshot);
  const canonical = mode === REPAIR_PRESENTATION_MODES.CANONICAL;
  const unsupported = mode === REPAIR_PRESENTATION_MODES.UNSUPPORTED;
  const { visibleItems: _visibleItems, ...sectionOptions } = options;

  const legacySections = !canonical && !unsupported && visibleItems.length > 0
    ? [{
      key: "legacy_prioritized",
      label: "Prioritized repairs",
      rows: visibleItems.map(presentationRow),
      hiddenRows: [],
      hiddenCount: 0,
      totalCount: visibleItems.length,
      groups: buildRepairGroupSummaries(visibleItems.map(presentationRow)),
    }]
    : [];

  return {
    version: REPAIR_PRESENTATION_VERSION,
    mode,
    canonical,
    unsupported,
    snapshotCount: snapshot.length,
    visibleCount: visibleItems.length,
    sections: canonical ? sectionCustomerRepairs(visibleItems, sectionOptions) : [],
    legacySections,
    legacyItems: canonical ? [] : visibleItems,
  };
}
