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
import { evidenceLink } from "./evidenceUrl.js";
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
// Families that name the classifier's own bookkeeping rather than a kind of
// page an owner would recognise. "standard" is the default bucket: saying
// "6 standard pages" tells someone nothing they did not already know, and the
// unmapped-family fallback below would otherwise print the key verbatim.
const OPAQUE_FAMILIES = new Set(["unknown", "mixed", "unclassified", "other", "none", "standard", ""]);

/**
 * Family labels a customer can act on, in their own words.
 *
 * Two forms, because one does not fit both sentences. `one`/`many` are complete
 * noun phrases and are used when a card names a single kind of page: a family
 * whose own name already ends in "page" was previously handed to a template
 * that appended another one, producing "3 product page pages", and "homepage"
 * became "1 homepage page". `word` is the bare modifier used in the "across X
 * and Y pages" list, so it must never itself contain "page".
 *
 * The keys are app/extract.py classify_template's complete return set plus the
 * legacy names still held in persisted rows. "standard" and "unknown" are
 * absent deliberately -- see OPAQUE_FAMILIES.
 */
const FAMILY_WORDS = Object.freeze({
  activity_detail: { word: "activity", one: "activity page", many: "activity pages" },
  archive: { word: "archive", one: "archive page", many: "archive pages" },
  booking_or_checkout: { word: "checkout", one: "checkout page", many: "checkout pages" },
  calculator: { word: "calculator", one: "calculator page", many: "calculator pages" },
  category_listing: { word: "category", one: "category page", many: "category pages" },
  collection_page: { word: "collection", one: "collection page", many: "collection pages" },
  comparison_page: { word: "comparison", one: "comparison page", many: "comparison pages" },
  contact: { word: "contact", one: "contact page", many: "contact pages" },
  conversion: { word: "sign-up and contact", one: "sign-up or contact page", many: "sign-up and contact pages" },
  guide: { word: "guide", one: "guide", many: "guides" },
  guide_article: { word: "guide", one: "guide", many: "guides" },
  homepage: { word: "home", one: "homepage", many: "homepages" },
  legal_info: { word: "legal", one: "legal page", many: "legal pages" },
  loan_program: { word: "loan", one: "loan page", many: "loan pages" },
  location_landing: { word: "location", one: "location page", many: "location pages" },
  product_detail: { word: "product", one: "product page", many: "product pages" },
  product_page: { word: "product", one: "product page", many: "product pages" },
  qa: { word: "FAQ", one: "FAQ page", many: "FAQ pages" },
  route_boundary: { word: "section", one: "section page", many: "section pages" },
});

/**
 * The bare modifier for a family, or "" when this build cannot name it.
 *
 * An unmapped key used to be printed with its underscores swapped for spaces,
 * which is how "internal or auth pages" and "loan program pages" reached the
 * customer. Silence is the safe failure: a family this build does not know is
 * one it cannot describe, and the count still reaches the sentence through the
 * unnamed-pages branch below.
 */
function familyWord(family) {
  const entry = FAMILY_WORDS[familyKey(family)];
  return entry ? entry.word : "";
}

function familyKey(family) {
  const key = lower(family).replace(/\s+/g, "_");
  return OPAQUE_FAMILIES.has(key) ? "" : key;
}

/** The complete noun phrase for a family at a given count. */
function familyNoun(family, count) {
  const entry = FAMILY_WORDS[familyKey(family)];
  if (!entry) return "";
  return count === 1 ? entry.one : entry.many;
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
  const breakdown = Object.entries(breakdownOf(item));
  const named = breakdown
    .filter(([family]) => familyWord(family))
    .sort((a, b) => b[1] - a[1])
    .map(([family]) => familyWord(family));
  // Families the classifier cannot name still hold pages. Dropping them and
  // then reading the sentence as though the named families cover the whole
  // count is how "105 pages, 60 of them unclassified and 45 location pages"
  // became "105 location pages" -- a card claiming one family's identity for
  // pages that do not belong to it.
  const hasUnnamed = breakdown.length > named.length;

  if (named.length === 0) return `${count} ${noun} on your site.`;
  // One named family gets the complete noun phrase, so a label that is already
  // a kind of page ("homepage", "product page") is not handed another "pages".
  if (named.length === 1 && !hasUnnamed) {
    const only = breakdown.find(([family]) => familyWord(family));
    return `${count} ${familyNoun(only[0], count)}.`;
  }
  const listed = hasUnnamed ? [...named, "other"] : named;
  const spread = listed.length <= 3
    ? `${listed.slice(0, -1).join(", ")} and ${listed[listed.length - 1]}`
    : `${listed.slice(0, 3).join(", ")} and other`;
  return `${count} ${noun}, across ${spread} pages.`;
}

/**
 * Two persisted cards are one customer action when they are the same repair.
 *
 * The scan's own `repair_fingerprint` decides that wherever it recorded one:
 * it is the backend's statement of repair identity, and nothing re-derived
 * here outranks it.
 *
 * Rows with no recorded fingerprint remain separate. Missing identity cannot
 * prove that two findings are one customer action, even when their rule/type
 * labels happen to match.
 */
export function customerActionKey(item, fallbackRowIdentity = "") {
  // The scanner's own repair identity wins when it recorded one. Two persisted
  // rows carrying the same fingerprint are the same repair by the backend's
  // statement, which is stronger evidence than anything re-derived here.
  const fingerprint = repairFingerprintOf(item);
  if (fingerprint) return `fingerprint|${fingerprint}`;

  // An absent fingerprint is explicitly *not* evidence of shared repair
  // identity. Keep every such persisted row separate. Prefer its durable ID;
  // mergeCustomerActions supplies a deterministic per-input fallback for legacy
  // rows with no usable identifier.
  const rowIdentity = clean(
    item?.fix_id
      || item?.id
      || item?.original?.fix_id
      || item?.original?.id
      || fallbackRowIdentity,
  );
  return `row|${rowIdentity || "unidentified"}`;
}

/**
 * The persisted repair identity, or "" when the scan recorded none.
 *
 * Rows without a fingerprint are never merged: an absent identity is not
 * evidence that two repairs are the same one.
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

/** Customer-safe rows for the persisted child evidence inside one action. */
export function customerEvidenceGroupRows(card = {}, siteOrigin = "") {
  const groups = Array.isArray(card?.evidence?.evidenceGroups)
    ? card.evidence.evidenceGroups
    : [];
  return groups.map((group, index) => {
    const affectedPages = [...new Set(
      (Array.isArray(group?.affectedPages) ? group.affectedPages : [])
        .map(clean)
        .filter(Boolean),
    )];
    const representativePage = clean(group?.representativePage) || affectedPages[0] || "";
    const localeEvidence = affectedPages.length > 0
      ? affectedPages
      : representativePage ? [representativePage] : [];
    const locales = [...new Set(localeEvidence.map(localeOf))];
    const persistedLocale = lower(group?.locale);
    const locale = persistedLocale
      && locales.length === 1
      && locales[0] === persistedLocale
      ? persistedLocale
      : "";
    const family = clean(group?.family);
    return {
      id: clean(group?.fixId) || `evidence-group-${index + 1}`,
      family,
      // A standalone group heading, so it takes the complete noun phrase rather
      // than the bare modifier the "across X and Y pages" list needs -- the two
      // forms diverged when "homepage" stopped being usable as a modifier. It
      // is always the singular: the row prints its own count right beside it,
      // and "product pages · 3 pages" says the same thing twice.
      familyLabel: familyNoun(family, 1),
      locale,
      count: Math.max(Number(group?.count) || 0, affectedPages.length),
      representativePage,
      representativeLink: evidenceLink(representativePage, siteOrigin),
      affectedPages,
    };
  });
}

export function customerEvidenceGroupHeading(rows = []) {
  const count = Array.isArray(rows) ? rows.length : 0;
  return `Evidence groups (${count})`;
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
    const rawCandidate = member?.raw_finding ?? member?.original?.raw_finding;
    const raw = rawCandidate && typeof rawCandidate === "object"
      ? rawCandidate
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

  const sourceItems = Array.isArray(items) ? items : [];
  for (const [index, item] of sourceItems.entries()) {
    if (!item || typeof item !== "object") continue;
    const key = customerActionKey(item, `index:${index}`);
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
    status: lower(item?.status || item?.user_status || item?.original?.status || item?.original?.user_status),
    customerCategory: clean(copy.customerCategory)
      || clean(item?.customerCategory || item?.customer_category || item?.original?.customer_category)
      || "Website improvement",
    technicalLabel: clean(copy.technicalLabel),
    evidenceClass: lower(item?.evidenceClass || item?.evidence_class || item?.original?.evidence_class),
    // Read by the repeated-title hint. Persisted scope, not re-derived.
    pageScope: lower(item?.pageScope || item?.page_scope || item?.original?.page_scope),
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
      // Every canonical action has child evidence, including a single-row
      // action, so rendering and export use one uniform contract.
      evidenceGroups: Array.isArray(item.evidenceGroups) ? item.evidenceGroups : [],
    },
  };
}

/**
 * Scope wording for one card, from persisted evidence only.
 *
 * The order is a preference, not a fallback chain of equal options: a named
 * page family is the most useful thing a customer can be told, a recorded scope
 * is the next, a count is at least a number they can compare, and the evidence
 * class is the last thing that is still true. Nothing is derived from the
 * affected URLs -- reading "/products/" out of a path and calling the card
 * "Product pages" is a claim the scan never made, and wrong on any site that
 * uses that word for something else.
 */
function scopeHintFor(card = {}) {
  const families = Object.entries(card?.evidence?.familyBreakdown || {})
    .filter(([family]) => familyWord(family));
  if (families.length === 1) {
    const [family, count] = families[0];
    const noun = familyNoun(family, Number(count) === 1 ? 1 : 2);
    return noun ? noun.charAt(0).toUpperCase() + noun.slice(1) : "";
  }

  const scope = lower(card?.pageScope || card?.page_scope);
  if (scope === "sitewide") return "Across the site";
  if (scope === "section" || scope === "path_prefix") return "One section";

  const count = Number(card?.evidence?.pageCount || 0);
  if (count > 0) return `${count} specific ${count === 1 ? "page" : "pages"}`;

  const label = customerEvidenceClassLabel(card?.evidenceClass);
  return label || "";
}

const EVIDENCE_CLASS_LABELS = Object.freeze({
  verified: "Verified",
  observed: "Observed",
  inferred: "Inferred",
  reported: "Reported",
});

function customerEvidenceClassLabel(value) {
  return EVIDENCE_CLASS_LABELS[lower(value)] || "";
}

/**
 * Tell apart the cards that need telling apart, and only those.
 *
 * Identical titles do not prove identical repairs -- a redirect in a sitemap
 * and a redirect in a navigation link are different jobs -- so the cards stay
 * separate and the disambiguation is presentational. This runs after card
 * construction, never before grouping: moving it earlier would let a display
 * concern reach customerActionKey and start splitting rows the backend said
 * were one repair.
 *
 * A card whose title already stands alone gets nothing. A hint on every card
 * is noise, and noise is what the metadata line is competing with.
 */
export function withRepeatedTitleScopeHints(cards = []) {
  const counts = new Map();
  for (const card of cards) {
    const key = lower(card?.title);
    if (key) counts.set(key, (counts.get(key) || 0) + 1);
  }
  return cards.map((card) => ({
    ...card,
    scopeHint: counts.get(lower(card?.title)) > 1 ? scopeHintFor(card) : "",
  }));
}

/** The customer-facing FixList: merged actions, each as five answers. */
export function buildRepairCards(items = []) {
  return mergeCustomerActions(items).map(buildRepairCard);
}
