import { customerPriorityReason, priorityBucket } from "./fixRanking.js";
import {
  REPAIR_PRESENTATION_MODES,
  repairPresentationContract,
} from "./repairContractPresentation.js";

export const REPAIR_PRESENTATION_VERSION = "repair_presentation_v1_compact_mobile";

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
  ready_to_verify: "Ready to verify",
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
    conversion: "Conversion pages",
    route_boundary: "Website routes",
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

export function repairVerificationLabel(item = {}) {
  const state = clean(
    item.repairVerificationState
      || item.repair_verification_state
      || item.verification_state
      || item.original?.repair_verification_state,
  ).toLowerCase();
  return VERIFICATION_LABELS[state] || "";
}

export function repairRowModel(item = {}) {
  const actionPriority = priorityBucket(item);
  return {
    version: REPAIR_PRESENTATION_VERSION,
    id: clean(item.id || item.fix_id || item.repair_fingerprint),
    title: clean(item.issueTitle || item.issue_title || item.title) || "Review this repair",
    actionPriority,
    sectionLabel: SECTION_LABELS[actionPriority] || "Important",
    surface: repairSurfaceLabel(item),
    scope: repairScopeSummary(item),
    reason: customerPriorityReason(item),
    verification: repairVerificationLabel(item),
    affectedPageCount: pageCount(item),
    groupedFindingCount: Number(item.groupedFindingCount ?? item.grouped_finding_count ?? 0) || 0,
    sharedRepairConfirmed: Boolean(
      item.sharedRepairConfirmed
        || item.shared_repair_confirmed
        || contextOf(item).shared_repair_confirmed,
    ),
  };
}

export function sectionCustomerRepairs(items = [], { initialFixFirstLimit = 3 } = {}) {
  const buckets = new Map(SECTION_ORDER.map((key) => [key, []]));
  for (const item of Array.isArray(items) ? items : []) {
    if (!item) continue;
    const model = repairRowModel(item);
    const key = SECTION_ORDER.includes(model.actionPriority) ? model.actionPriority : "important";
    buckets.get(key).push({ item, model });
  }

  return SECTION_ORDER
    .map((key) => {
      const rows = buckets.get(key) || [];
      const visibleLimit = key === "fix_first" ? Math.max(1, Number(initialFixFirstLimit) || 3) : rows.length;
      return {
        key,
        label: SECTION_LABELS[key],
        rows: rows.slice(0, visibleLimit),
        hiddenRows: rows.slice(visibleLimit),
        hiddenCount: Math.max(0, rows.length - visibleLimit),
        totalCount: rows.length,
      };
    })
    .filter((section) => section.totalCount > 0);
}

function presentationModeForItems(items = []) {
  const list = Array.isArray(items) ? items.filter(Boolean) : [];
  if (list.length === 0) return REPAIR_PRESENTATION_MODES.LEGACY;

  const contracts = list.map((item) => repairPresentationContract(item));
  if (contracts.some((contract) => contract.unsupported)) {
    return REPAIR_PRESENTATION_MODES.UNSUPPORTED;
  }
  if (contracts.every((contract) => contract.canonicalActionPriorityAllowed)) {
    return REPAIR_PRESENTATION_MODES.CANONICAL;
  }
  return REPAIR_PRESENTATION_MODES.LEGACY;
}

/**
 * Safe integration seam for the live FixList page.
 *
 * Canonical action-priority sections are enabled only when every displayed
 * repair explicitly carries a supported persisted contract. Historical rows
 * without a contract keep their frozen legacy ordering. Unknown future
 * contracts also fail closed instead of being silently interpreted by this UI.
 *
 * Mixed canonical/legacy data deliberately falls back as one legacy list so a
 * single saved scan is never presented using two competing ranking authorities.
 */
export function buildFixListPresentation(items = [], options = {}) {
  const list = Array.isArray(items) ? items.filter(Boolean) : [];
  const mode = presentationModeForItems(list);
  const canonical = mode === REPAIR_PRESENTATION_MODES.CANONICAL;
  const unsupported = mode === REPAIR_PRESENTATION_MODES.UNSUPPORTED;

  return {
    version: REPAIR_PRESENTATION_VERSION,
    mode,
    canonical,
    unsupported,
    sections: canonical ? sectionCustomerRepairs(list, options) : [],
    legacyItems: canonical ? [] : list,
  };
}
