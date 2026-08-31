/**
 * The customer-facing shape of a repair card.
 *
 * A FixList card is an implementation plan, not an audit object. Every card
 * answers five things, in this order, before any technical evidence:
 *
 *   what is wrong -> why it matters -> where -> what to change -> who
 *
 * This module composes those five answers from the persisted, authoritative
 * fields and nothing else. It never invents a root cause, never claims a shared
 * template the backend did not record, and never rewrites evidence to read
 * better. Where the backend cannot support a claim, the claim is omitted.
 */
import { customerCopyForFix } from "./fixVocabulary.js";
import { repairSuggestion, repairTypeOf } from "./repairSuggestions.js";

const clean = (value) => (typeof value === "string" ? value.trim() : "");
const lower = (value) => clean(value).toLowerCase();

/**
 * Classifier states that are not page types.
 *
 * These are how the classifier records "I could not tell", so showing them is
 * telling the customer about our uncertainty in the vocabulary of our own
 * internals. They are dropped from customer scope wording; the underlying
 * counts stay in the evidence breakdown.
 */
const OPAQUE_FAMILIES = new Set(["unknown", "mixed", "unclassified", "other", "none", ""]);

/** Family labels a customer can act on, in their own words. */
const FAMILY_WORDS = Object.freeze({
  legal_info: "legal",
  location_landing: "location",
  guide_article: "guide",
  contact: "contact",
  standard: "standard",
  homepage: "homepage",
  product_detail: "product",
  category_listing: "category",
  booking_or_checkout: "checkout",
  qa: "FAQ",
  archive: "archive",
  conversion: "conversion",
  route_boundary: "section",
  collection_page: "collection",
  activity_detail: "activity",
});

function familyWord(family) {
  const key = lower(family).replace(/\s+/g, "_");
  if (OPAQUE_FAMILIES.has(key)) return "";
  return FAMILY_WORDS[key] || key.replace(/_/g, " ");
}

const affectedOf = (item) => {
  const list = Array.isArray(item?.affectedPages) ? item.affectedPages : item?.affected_pages;
  return Array.isArray(list) ? list.map(clean).filter(Boolean) : [];
};

const countOf = (item) => {
  const declared = Number(item?.pageCount ?? item?.page_count ?? 0);
  return Math.max(affectedOf(item).length, Number.isFinite(declared) ? declared : 0);
};

function breakdownOf(item) {
  const raw = item?.familyBreakdown || item?.family_breakdown;
  if (raw && typeof raw === "object" && !Array.isArray(raw)) {
    const entries = Object.entries(raw)
      .map(([family, count]) => [family, Number(count) || 0])
      .filter(([, count]) => count > 0);
    if (entries.length > 0) return Object.fromEntries(entries);
  }
  const family = clean(item?.templateFamily || item?.page_template_family);
  const count = countOf(item);
  return family && count > 0 ? { [family]: count } : {};
}

/**
 * Where the problem is, in one sentence.
 *
 * The count alone is what the current cards repeat twice without helping. This
 * says how many and *which kinds of page*, and only names the kinds the
 * classifier actually identified -- so an opaque classification simply drops out
 * of the sentence rather than surfacing as "mixed pages".
 */
export function whereLine(item) {
  const count = countOf(item);
  if (count <= 0) return "";
  const noun = count === 1 ? "page" : "pages";
  const named = Object.entries(breakdownOf(item))
    .filter(([family]) => familyWord(family))
    .sort((a, b) => b[1] - a[1])
    .map(([family]) => familyWord(family));

  if (named.length === 0) return `${count} ${noun} on your site.`;
  if (named.length === 1) return `${count} ${named[0]} ${noun}.`;
  const spread = named.length <= 3
    ? `${named.slice(0, -1).join(", ")} and ${named[named.length - 1]}`
    : `${named.slice(0, 3).join(", ")} and other`;
  return `${count} ${noun}, across ${spread} pages.`;
}

/**
 * Two persisted cards are one customer action when they are the same repair.
 *
 * The key is the rule and the repair type the library derives from it. A page
 * family is deliberately not part of it: the classifier labelling one group
 * "legal" and another "standard" says nothing about whether the customer
 * performs one change or two, and splitting on it is what turned one repair
 * into several tasks.
 *
 * The instruction text is not part of it either, for the same reason -- the
 * scanner's grouped wording interpolates the family, so keying on it would
 * reintroduce the split through the back door.
 *
 * repairType is kept in the key rather than assumed away: it is the library's
 * own statement of what kind of repair this is, so if one rule ever maps to two
 * repair types by context, those stay two actions on evidence rather than on a
 * label.
 */
export function customerActionKey(item) {
  const rule = lower(item?.rule || item?.original?.rule);
  return `${rule}|${lower(repairTypeOf(item))}`;
}

/** Merge persisted cards that are one customer action, keeping all evidence. */
export function mergeCustomerActions(items = []) {
  const order = [];
  const groups = new Map();

  for (const item of Array.isArray(items) ? items : []) {
    if (!item || typeof item !== "object") continue;
    const key = customerActionKey(item);
    if (!groups.has(key)) {
      groups.set(key, { lead: item, members: [] });
      order.push(key);
    }
    const group = groups.get(key);
    group.members.push(item);
    // The card that already speaks for the most pages leads, so the merged card
    // keeps the wording written for the larger evidence set.
    if (countOf(item) > countOf(group.lead)) group.lead = item;
  }

  return order.map((key) => {
    const { lead, members } = groups.get(key);
    // A card built from one persisted row is still traceable to that row. The
    // evidence panel promises the persisted IDs behind every action, and
    // returning the lead untouched left the four single-row Ike actions with an
    // empty list -- traceability that held only for merged cards.
    if (members.length === 1) {
      const existing = Array.isArray(lead.mergedFromFixIds)
        ? lead.mergedFromFixIds.map(clean).filter(Boolean)
        : [];
      return {
        ...lead,
        mergedFromFixIds: existing.length > 0 ? existing : [clean(lead.fix_id || lead.id)].filter(Boolean),
      };
    }

    const affected = [];
    const seen = new Set();
    for (const member of members) {
      for (const page of affectedOf(member)) {
        if (!seen.has(page)) {
          seen.add(page);
          affected.push(page);
        }
      }
    }
    const breakdown = {};
    for (const member of members) {
      for (const [family, count] of Object.entries(breakdownOf(member))) {
        breakdown[family] = (breakdown[family] || 0) + count;
      }
    }
    // page_count is the sum of what each card proved, not the length of a list
    // that may be capped: merging must not shrink a total the scan established.
    const declared = members.reduce((total, member) => total + countOf(member), 0);
    // A merged card genuinely has no single family, so it must stop carrying
    // the lead's. Left in place, the copy would title the card after one family
    // and claim "fix the shared standard template once" for pages spanning
    // three -- naming a shared template the evidence does not support.
    const namedFamilies = Object.keys(breakdown).filter((family) => familyWord(family));
    const spansFamilies = namedFamilies.length > 1;
    return {
      ...lead,
      ...(spansFamilies ? { templateFamily: "", page_template_family: "" } : {}),
      affectedPages: affected,
      affected_pages: affected,
      pageCount: Math.max(declared, affected.length),
      page_count: Math.max(declared, affected.length),
      familyBreakdown: breakdown,
      family_breakdown: breakdown,
      mergedFromFixIds: members.map((member) => clean(member.fix_id || member.id)).filter(Boolean),
    };
  });
}

/**
 * The five answers, composed from persisted fields only.
 *
 * `who` is always a human label: the scanner's own bucket names are internal
 * identifiers and never appear.
 */
export function buildRepairCard(item = {}) {
  const copy = customerCopyForFix(item) || {};
  const suggestion = repairSuggestion(item);
  const affected = affectedOf(item);

  return {
    title: clean(copy.title) || clean(item.title) || clean(item.issue_title) || "Review this recommendation",
    whyItMatters: clean(copy.whyItMatters) || clean(item.whyItMatters) || clean(item.why_it_matters),
    where: whereLine(item),
    whatToChange: clean(copy.recommendation) || clean(suggestion.suggestedFix),
    who: clean(suggestion.role) || (item.needsHelp ? "Developer" : "You"),
    effort: clean(suggestion.effortDetail) || clean(suggestion.effortLabel),
    // Evidence is not hidden, only ordered after the action.
    evidence: {
      affectedPages: affected,
      pageCount: countOf(item),
      familyBreakdown: breakdownOf(item),
      representativePages: affected.slice(0, 3),
      mergedFromFixIds: Array.isArray(item.mergedFromFixIds) ? item.mergedFromFixIds : [],
    },
  };
}

/** The customer-facing FixList: merged actions, each as five answers. */
export function buildRepairCards(items = []) {
  return mergeCustomerActions(items).map(buildRepairCard);
}
