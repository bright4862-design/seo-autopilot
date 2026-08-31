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
 * The scan's own `repair_fingerprint` decides that wherever it recorded one:
 * it is the backend's statement of repair identity, and nothing re-derived
 * here outranks it.
 *
 * Everything below is the fallback for rows with no recorded fingerprint.
 *
 * The key is then the rule and the repair type the library derives from it. A
 * page family is deliberately not part of it: the classifier labelling one group
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
  // The scanner's own repair identity wins when it recorded one. Two persisted
  // rows carrying the same fingerprint are the same repair by the backend's
  // statement, which is stronger evidence than anything re-derived here, and a
  // production audit found ten sites rendering those as separate top-level
  // tasks.
  const fingerprint = repairFingerprintOf(item);
  if (fingerprint) return `fingerprint|${fingerprint}`;
  const rule = lower(item?.rule || item?.original?.rule);
  return `${rule}|${lower(repairTypeOf(item))}`;
}

/**
 * The persisted repair identity, or "" when the scan recorded none.
 *
 * Rows without a fingerprint are never merged *by* fingerprint: an absent
 * identity is not evidence that two repairs are the same one, so they fall back
 * to the rule/repair-type key rather than collapsing into a single unknown
 * bucket.
 */
export function repairFingerprintOf(item) {
  return clean(
    item?.repair_fingerprint
      || item?.repairFingerprint
      || item?.original?.repair_fingerprint,
  );
}

// A locale segment as it appears in a path: "fr", "de-at", "en-be". Derived
// from the URL only, and only used to label evidence the customer can already
// see in that URL -- it never becomes a claim the scanner did not record.
const LOCALE_SEGMENT = /^[a-z]{2}(-[a-z]{2})?$/;

function localeOf(page) {
  const path = clean(page).replace(/^https?:\/\/[^/]+/i, "");
  const first = path.split("/").filter(Boolean)[0];
  return first && LOCALE_SEGMENT.test(first.toLowerCase()) ? first.toLowerCase() : "";
}

/**
 * Child evidence groups for a merged action: one row per persisted card.
 *
 * The top-level card says what to change once; these preserve the template and
 * page distinctions the scan actually recorded, so collapsing the action never
 * costs evidence.
 */
function evidenceGroupsFor(members) {
  return members.flatMap((member) => {
    const raw = member?.raw_finding && typeof member.raw_finding === "object"
      ? member.raw_finding
      : {};
    const persisted = Array.isArray(raw.repair_evidence_groups)
      ? raw.repair_evidence_groups
      : [];
    if (persisted.length > 0) {
      return persisted.map((group) => {
        const pages = Array.isArray(group?.affected_urls)
          ? group.affected_urls.map(clean).filter(Boolean)
          : [];
        return {
          family: clean(group?.family),
          count: Math.max(Number(group?.count) || 0, pages.length),
          representativePage: clean(group?.representative_url) || pages[0] || "",
          affectedPages: pages,
          locale: clean(group?.locale),
          fixId: clean(group?.fix_id),
          priority: clean(group?.priority),
          actionPriority: clean(group?.action_priority),
          evidenceClass: clean(group?.evidence_class),
          evidenceStatus: clean(group?.evidence_status),
          verificationState: clean(group?.verification_state),
          repairVerificationState: clean(group?.repair_verification_state),
        };
      });
    }

    const pages = affectedOf(member);
    // A page with no market prefix is a disagreement, not an absence of one.
    // Filtering the empty results out first let ["/fr/page", "/about"] report
    // "fr", which claims a market for a page that never carried one.
    const locales = [...new Set(pages.map(localeOf))];
    return [{
      family: clean(member?.templateFamily || member?.page_template_family),
      count: countOf(member),
      representativePage: pages[0] || "",
      affectedPages: pages,
      // Only stated when every page in this group agrees, so the label is a
      // description of the evidence rather than a guess about the site.
      locale: locales.length === 1 && locales[0] ? locales[0] : "",
      fixId: clean(member?.fix_id || member?.id),
    }];
  });
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
        // One persisted row is still one row of evidence. Omitting the group
        // here made the per-row contract hold only for merged actions, so a
        // consumer reconciling children against a count saw nothing for every
        // unmerged card -- the same uniformity mergedFromFixIds already keeps.
        evidenceGroups: evidenceGroupsFor(members),
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
      evidenceGroups: evidenceGroupsFor(members),
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
  const priority = lower(item?.priority || item?.original?.priority) || "medium";
  const actionPriority = lower(item?.actionPriority || item?.action_priority || item?.original?.action_priority);
  const sharedRepairConfirmed = item?.sharedRepairConfirmed === true
    || item?.shared_repair_confirmed === true
    || item?.original?.shared_repair_confirmed === true;

  return {
    rule: lower(item?.rule || item?.original?.rule),
    priority,
    actionPriority,
    customerCategory: clean(copy.customerCategory)
      || clean(item?.customerCategory || item?.customer_category || item?.original?.customer_category)
      || "Website improvement",
    technicalLabel: clean(copy.technicalLabel),
    evidenceClass: lower(item?.evidenceClass || item?.evidence_class || item?.original?.evidence_class),
    sharedRepairConfirmed,
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
      // Present only on a merged action; a card built from one persisted row
      // has no children to reconcile against its own count.
      evidenceGroups: Array.isArray(item.evidenceGroups) ? item.evidenceGroups : [],
    },
  };
}

/** The customer-facing FixList: merged actions, each as five answers. */
export function buildRepairCards(items = []) {
  return mergeCustomerActions(items).map(buildRepairCard);
}
