/**
 * Deterministic repair suggestion layer.
 *
 * FixList owns detection, prioritization, grouping, and the suggested fix. This
 * module is the suggested-fix half of that ownership: a pure, offline mapping
 * from the repair evidence the scanner already publishes to the action a
 * customer should take.
 *
 * Hard boundaries:
 * - No scanner, crawler, authority, or persistence behavior is involved.
 * - No new field is written back onto a repair or the authoritative scan
 *   payload. Only fields the payload already carries are read.
 * - No language model participates. Every value here is a fixed table lookup
 *   plus evidence the scanner already published, so the same repair always
 *   produces the same suggestion.
 * - Scanner-authored copy always wins. When the scanner published its own
 *   remediation text, it is preserved and this table is only the fallback.
 */

/** Shape/behavior version of the suggestion model returned by this module. */
export const REPAIR_SUGGESTION_VERSION = "repair_suggestion_v1_deterministic";

/**
 * Content version of the suggestion library itself.
 *
 * Nothing persists this today. It is carried on every suggestion so that later
 * A/B tests, improvement tracking, customer feedback, and scan-to-scan
 * comparisons can say which wording a customer actually saw. Bump it whenever
 * the suggested-fix copy, strategy, effort, or role guidance changes.
 */
export const REPAIR_SUGGESTION_LIBRARY_VERSION = "v1";

/**
 * Shown whenever the scanner reports a rule this library does not map yet.
 * The UI renders this instead of an empty or undefined suggested fix.
 */
export const REPAIR_SUGGESTION_FALLBACK = "Review this repair manually using the evidence below, then confirm the change with a fresh scan.";

export const REPAIR_TYPES = Object.freeze({
  MISSING_TITLE: "missing_title",
  DUPLICATE_TITLE: "duplicate_title",
  MISSING_META_DESCRIPTION: "missing_meta_description",
  DUPLICATE_META_DESCRIPTION: "duplicate_meta_description",
  MISSING_H1: "missing_h1",
  MULTIPLE_H1: "multiple_h1",
  CANONICAL_ISSUE: "canonical_issue",
  REDIRECT_CHAIN: "redirect_chain",
  BROKEN_INTERNAL_LINK: "broken_internal_link",
  HARD_TO_DISCOVER_PAGE: "hard_to_discover_page",
  SITEMAP_REDIRECT: "sitemap_redirect",
  NOINDEX_ISSUE: "noindex_issue",
  THIN_OR_DUPLICATE_TEMPLATE: "thin_or_duplicate_template",
});

export const FIX_STRATEGIES = Object.freeze({
  TEMPLATE: "template",
  PAGE: "page",
  CONTENT: "content",
  NAVIGATION: "navigation",
  SITE_CONFIG: "site_config",
  SITEMAP: "sitemap",
});

export const FIX_STRATEGY_LABELS = Object.freeze({
  template: "Fix the template once",
  page: "Fix this page",
  content: "Rewrite the page content",
  navigation: "Fix the internal links",
  site_config: "Fix the site or server configuration",
  sitemap: "Fix the sitemap",
});

export const EFFORT_LEVELS = Object.freeze(["Low", "Medium", "High"]);

/**
 * Exact scanner rule identifiers, mapped to the repair type a customer acts on.
 * Several scanner rules describe one customer repair; that collapsing happens
 * here rather than in a component.
 */
const RULE_REPAIR_TYPES = Object.freeze({
  missing_title: REPAIR_TYPES.MISSING_TITLE,
  empty_title: REPAIR_TYPES.MISSING_TITLE,
  title_missing: REPAIR_TYPES.MISSING_TITLE,
  missing_meta_title: REPAIR_TYPES.MISSING_TITLE,

  duplicate_title: REPAIR_TYPES.DUPLICATE_TITLE,
  duplicate_titles: REPAIR_TYPES.DUPLICATE_TITLE,
  duplicate_title_template: REPAIR_TYPES.DUPLICATE_TITLE,
  duplicate_title_localized: REPAIR_TYPES.DUPLICATE_TITLE,
  duplicate_title_query_variants: REPAIR_TYPES.DUPLICATE_TITLE,
  generic_fallback_title: REPAIR_TYPES.DUPLICATE_TITLE,

  missing_meta_description: REPAIR_TYPES.MISSING_META_DESCRIPTION,
  empty_meta_description: REPAIR_TYPES.MISSING_META_DESCRIPTION,
  malformed_meta_description: REPAIR_TYPES.MISSING_META_DESCRIPTION,
  meta_description_unusable: REPAIR_TYPES.MISSING_META_DESCRIPTION,

  duplicate_meta_description: REPAIR_TYPES.DUPLICATE_META_DESCRIPTION,
  duplicate_meta_descriptions: REPAIR_TYPES.DUPLICATE_META_DESCRIPTION,
  duplicate_description: REPAIR_TYPES.DUPLICATE_META_DESCRIPTION,

  missing_h1: REPAIR_TYPES.MISSING_H1,
  h1_missing: REPAIR_TYPES.MISSING_H1,
  empty_h1: REPAIR_TYPES.MISSING_H1,

  multiple_h1: REPAIR_TYPES.MULTIPLE_H1,
  multiple_h1s: REPAIR_TYPES.MULTIPLE_H1,
  duplicate_h1: REPAIR_TYPES.MULTIPLE_H1,

  canonical_missing: REPAIR_TYPES.CANONICAL_ISSUE,
  missing_canonical: REPAIR_TYPES.CANONICAL_ISSUE,
  canonical_chain: REPAIR_TYPES.CANONICAL_ISSUE,
  canonical_loop: REPAIR_TYPES.CANONICAL_ISSUE,
  canonical_conflict: REPAIR_TYPES.CANONICAL_ISSUE,
  canonical_mismatch: REPAIR_TYPES.CANONICAL_ISSUE,
  canonicalization: REPAIR_TYPES.CANONICAL_ISSUE,
  duplicate_route_casing: REPAIR_TYPES.CANONICAL_ISSUE,

  redirect_chain: REPAIR_TYPES.REDIRECT_CHAIN,
  redirect_loop: REPAIR_TYPES.REDIRECT_CHAIN,
  redirect_chain_limit_exceeded: REPAIR_TYPES.REDIRECT_CHAIN,
  internal_link_redirect: REPAIR_TYPES.REDIRECT_CHAIN,

  broken_page: REPAIR_TYPES.BROKEN_INTERNAL_LINK,
  broken_link: REPAIR_TYPES.BROKEN_INTERNAL_LINK,
  broken_internal_link: REPAIR_TYPES.BROKEN_INTERNAL_LINK,
  "404_error": REPAIR_TYPES.BROKEN_INTERNAL_LINK,
  soft_404: REPAIR_TYPES.BROKEN_INTERNAL_LINK,
  server_error: REPAIR_TYPES.BROKEN_INTERNAL_LINK,
  redirect_destination_failed: REPAIR_TYPES.BROKEN_INTERNAL_LINK,

  potential_orphan_pages: REPAIR_TYPES.HARD_TO_DISCOVER_PAGE,
  orphan_pages: REPAIR_TYPES.HARD_TO_DISCOVER_PAGE,
  orphan_page: REPAIR_TYPES.HARD_TO_DISCOVER_PAGE,

  sitemap_redirect: REPAIR_TYPES.SITEMAP_REDIRECT,
  sitemap_canonicalized_url: REPAIR_TYPES.SITEMAP_REDIRECT,

  noindex: REPAIR_TYPES.NOINDEX_ISSUE,
  noindex_page: REPAIR_TYPES.NOINDEX_ISSUE,
  unexpected_noindex: REPAIR_TYPES.NOINDEX_ISSUE,
  noindex_canonical_conflict: REPAIR_TYPES.NOINDEX_ISSUE,
  robots_directive_conflict: REPAIR_TYPES.NOINDEX_ISSUE,
  sitemap_indexability_conflict: REPAIR_TYPES.NOINDEX_ISSUE,
  redirect_destination_noindex: REPAIR_TYPES.NOINDEX_ISSUE,
  blocked_by_robots: REPAIR_TYPES.NOINDEX_ISSUE,

  thin_content: REPAIR_TYPES.THIN_OR_DUPLICATE_TEMPLATE,
  duplicate_content: REPAIR_TYPES.THIN_OR_DUPLICATE_TEMPLATE,
  near_duplicate_content: REPAIR_TYPES.THIN_OR_DUPLICATE_TEMPLATE,
  template_duplicate_content: REPAIR_TYPES.THIN_OR_DUPLICATE_TEMPLATE,
});

/**
 * Ordered fallbacks for scanner rules that are versioned or prefixed variants
 * of a rule already in the exact table. Order matters: the narrower duplicate
 * patterns must be tested before the broader field patterns.
 */
const RULE_PATTERNS = Object.freeze([
  [/duplicate.*meta_description|meta_description.*duplicate/, REPAIR_TYPES.DUPLICATE_META_DESCRIPTION],
  [/duplicate.*title|title.*duplicate/, REPAIR_TYPES.DUPLICATE_TITLE],
  [/^(missing|empty|malformed|unusable).*meta_description|meta_description.*(missing|empty|unusable)/, REPAIR_TYPES.MISSING_META_DESCRIPTION],
  [/noindex|robots_directive/, REPAIR_TYPES.NOINDEX_ISSUE],
  [/canonical/, REPAIR_TYPES.CANONICAL_ISSUE],
  [/sitemap.*(redirect|canonicalized)/, REPAIR_TYPES.SITEMAP_REDIRECT],
  [/redirect/, REPAIR_TYPES.REDIRECT_CHAIN],
  [/orphan/, REPAIR_TYPES.HARD_TO_DISCOVER_PAGE],
  [/multiple_h1|h1.*multiple/, REPAIR_TYPES.MULTIPLE_H1],
  [/h1/, REPAIR_TYPES.MISSING_H1],
  [/thin_content|duplicate_content/, REPAIR_TYPES.THIN_OR_DUPLICATE_TEMPLATE],
]);

const SUGGESTION_LIBRARY = Object.freeze({
  [REPAIR_TYPES.MISSING_TITLE]: {
    label: "Missing page title",
    groupTitle: "Add missing page titles",
    page: {
      fixStrategy: FIX_STRATEGIES.PAGE,
      suggestedFix: "Add a page title that names what this page is about, in the words a visitor would use.",
      bestApproach: "Write the title directly on this page rather than changing a shared template.",
      effort: "Low",
      effortDetail: "Under an hour",
      recommendedRole: "Content editor",
    },
    template: {
      fixStrategy: FIX_STRATEGIES.TEMPLATE,
      suggestedFix: "Add a title rule to the template that builds these pages so every page generates its own title.",
      bestApproach: "Fix the shared template once instead of typing a title into each affected page.",
      effort: "Medium",
      effortDetail: "2-4 hours",
      recommendedRole: "SEO manager with developer support",
    },
  },
  [REPAIR_TYPES.DUPLICATE_TITLE]: {
    label: "Repeated page title",
    groupTitle: "Make page titles unique",
    page: {
      fixStrategy: FIX_STRATEGIES.PAGE,
      suggestedFix: "Rewrite this page's title so it describes this page instead of repeating another page's title.",
      bestApproach: "Edit the title on this page; no template change is needed for a single page.",
      effort: "Low",
      effortDetail: "Under an hour",
      recommendedRole: "Content editor",
    },
    template: {
      fixStrategy: FIX_STRATEGIES.TEMPLATE,
      suggestedFix: "Update the shared title pattern so it includes the field that makes each page different, such as the product, place, or topic name.",
      bestApproach: "Change the one title pattern rather than editing each page by hand.",
      effort: "Medium",
      effortDetail: "2-4 hours",
      recommendedRole: "SEO manager with developer support",
    },
  },
  [REPAIR_TYPES.MISSING_META_DESCRIPTION]: {
    label: "Missing search description",
    groupTitle: "Improve search descriptions",
    page: {
      fixStrategy: FIX_STRATEGIES.PAGE,
      suggestedFix: "Add a short search description to this page explaining what a visitor can do here.",
      bestApproach: "Write it directly on the page; a template change is not needed for one page.",
      effort: "Low",
      effortDetail: "Under an hour",
      recommendedRole: "Content editor",
    },
    template: {
      fixStrategy: FIX_STRATEGIES.TEMPLATE,
      suggestedFix: "Add unique search descriptions to the page template generating these pages, so each page builds its own description from its own content.",
      bestApproach: "Update the shared templates once rather than writing a description for every affected page.",
      effort: "Medium",
      effortDetail: "1-2 hours per template",
      recommendedRole: "SEO manager",
    },
  },
  [REPAIR_TYPES.DUPLICATE_META_DESCRIPTION]: {
    label: "Repeated search description",
    groupTitle: "Make search descriptions unique",
    page: {
      fixStrategy: FIX_STRATEGIES.PAGE,
      suggestedFix: "Rewrite this page's search description so it is specific to this page.",
      bestApproach: "Edit the description on this page directly.",
      effort: "Low",
      effortDetail: "Under an hour",
      recommendedRole: "Content editor",
    },
    template: {
      fixStrategy: FIX_STRATEGIES.TEMPLATE,
      suggestedFix: "Change the template's description pattern so it pulls page-specific content instead of repeating one fixed sentence.",
      bestApproach: "Fix the shared description pattern once; hand-editing each page will drift back over time.",
      effort: "Medium",
      effortDetail: "2-4 hours",
      recommendedRole: "SEO manager with developer support",
    },
  },
  [REPAIR_TYPES.MISSING_H1]: {
    label: "Missing main heading",
    groupTitle: "Add clear main headings",
    page: {
      fixStrategy: FIX_STRATEGIES.PAGE,
      suggestedFix: "Add one clear main heading at the top of this page that states its main topic.",
      bestApproach: "Add the heading in the page editor for this page.",
      effort: "Low",
      effortDetail: "Under an hour",
      recommendedRole: "Content editor",
    },
    template: {
      fixStrategy: FIX_STRATEGIES.TEMPLATE,
      suggestedFix: "Add one main heading to the template that builds these pages, filled from each page's own title field.",
      bestApproach: "Fix the shared template once so every page built from it gets a heading.",
      effort: "Medium",
      effortDetail: "2-4 hours",
      recommendedRole: "Web developer",
    },
  },
  [REPAIR_TYPES.MULTIPLE_H1]: {
    label: "More than one main heading",
    groupTitle: "Reduce pages to one main heading",
    page: {
      fixStrategy: FIX_STRATEGIES.PAGE,
      suggestedFix: "Keep one main heading on this page and demote the others to sub-headings.",
      bestApproach: "Adjust the heading levels in this page's content.",
      effort: "Low",
      effortDetail: "Under an hour",
      recommendedRole: "Content editor",
    },
    template: {
      fixStrategy: FIX_STRATEGIES.TEMPLATE,
      suggestedFix: "Change the template or shared blocks so only the page title renders as the main heading and other blocks render as sub-headings.",
      bestApproach: "Fix the template or reusable block once; the duplicate heading is being generated, not typed.",
      effort: "Medium",
      effortDetail: "2-4 hours",
      recommendedRole: "Web developer",
    },
  },
  [REPAIR_TYPES.CANONICAL_ISSUE]: {
    label: "Preferred URL not set clearly",
    groupTitle: "Confirm the preferred version of each page",
    page: {
      fixStrategy: FIX_STRATEGIES.PAGE,
      suggestedFix: "Set this page's preferred-URL setting to its own final, working address.",
      bestApproach: "Correct the setting on this page and confirm the target returns a normal 200 response.",
      effort: "Low",
      effortDetail: "1-2 hours",
      recommendedRole: "Web developer",
    },
    template: {
      fixStrategy: FIX_STRATEGIES.TEMPLATE,
      suggestedFix: "Correct the preferred-URL rule in the template or CMS field that generates it, so each page points at its own final address.",
      bestApproach: "Fix the one rule that generates these values instead of editing pages individually.",
      effort: "Medium",
      effortDetail: "Half a day",
      recommendedRole: "Web developer",
    },
  },
  [REPAIR_TYPES.REDIRECT_CHAIN]: {
    label: "Unnecessary redirects",
    groupTitle: "Remove unnecessary redirects",
    page: {
      fixStrategy: FIX_STRATEGIES.NAVIGATION,
      suggestedFix: "Replace redirected internal links with the final destination URL and remove unnecessary redirect steps.",
      bestApproach: "Fix the source links and templates instead of manually editing individual URLs.",
      effort: "Low",
      effortDetail: "1-2 hours",
      recommendedRole: "Web developer",
    },
    template: {
      fixStrategy: FIX_STRATEGIES.TEMPLATE,
      suggestedFix: "Update the shared navigation, templates, and redirect rules so links point straight at the final URL in one hop.",
      bestApproach: "Fix the source links and templates instead of manually editing individual URLs.",
      effort: "Medium",
      effortDetail: "Half a day",
      recommendedRole: "Web developer",
    },
  },
  [REPAIR_TYPES.BROKEN_INTERNAL_LINK]: {
    label: "Broken internal link",
    groupTitle: "Repair broken internal links",
    page: {
      fixStrategy: FIX_STRATEGIES.NAVIGATION,
      suggestedFix: "Point this link at a working page, or restore the page it was meant to reach.",
      bestApproach: "Fix the link at its source page rather than adding a redirect to cover it.",
      effort: "Low",
      effortDetail: "1-2 hours",
      recommendedRole: "Web developer",
    },
    template: {
      fixStrategy: FIX_STRATEGIES.TEMPLATE,
      suggestedFix: "Correct the shared navigation, footer, or template block that repeats this broken link across pages.",
      bestApproach: "One shared block is generating most of these links; fix it there rather than page by page.",
      effort: "Medium",
      effortDetail: "Half a day",
      recommendedRole: "Web developer",
    },
  },
  [REPAIR_TYPES.HARD_TO_DISCOVER_PAGE]: {
    label: "Hard to discover page",
    groupTitle: "Make isolated pages easier to reach",
    page: {
      fixStrategy: FIX_STRATEGIES.NAVIGATION,
      suggestedFix: "Confirm whether this page still matters, then link to it from a related page or from your navigation.",
      bestApproach: "Decide first whether the page should exist; only then add links to it.",
      effort: "Low",
      effortDetail: "1-2 hours",
      recommendedRole: "SEO manager",
    },
    template: {
      fixStrategy: FIX_STRATEGIES.NAVIGATION,
      suggestedFix: "Add these pages to a listing, hub, or navigation block so they are reachable by following links from your homepage.",
      bestApproach: "Add one listing or hub page that links to the whole set rather than adding links one at a time.",
      effort: "Medium",
      effortDetail: "Half a day",
      recommendedRole: "SEO manager",
    },
  },
  [REPAIR_TYPES.SITEMAP_REDIRECT]: {
    label: "Sitemap lists non-final URLs",
    groupTitle: "List only final URLs in the sitemap",
    page: {
      fixStrategy: FIX_STRATEGIES.SITEMAP,
      suggestedFix: "Replace this sitemap entry with the final URL it currently redirects to.",
      bestApproach: "Correct the sitemap source or generator, not the published file by hand.",
      effort: "Low",
      effortDetail: "1-2 hours",
      recommendedRole: "Web developer",
    },
    template: {
      fixStrategy: FIX_STRATEGIES.SITEMAP,
      suggestedFix: "Change the sitemap generator so it publishes each page's final working URL and drops redirected entries.",
      bestApproach: "Fix the generator once; hand-edited sitemaps are rebuilt and lose the change.",
      effort: "Medium",
      effortDetail: "2-4 hours",
      recommendedRole: "Web developer",
    },
  },
  [REPAIR_TYPES.NOINDEX_ISSUE]: {
    label: "Page blocked from search",
    groupTitle: "Resolve pages blocked from search",
    page: {
      fixStrategy: FIX_STRATEGIES.SITE_CONFIG,
      suggestedFix: "Confirm whether this page should appear in search. If it should, remove the setting that is keeping it out.",
      bestApproach: "Check the intent before changing anything: some pages are hidden deliberately.",
      effort: "Low",
      effortDetail: "1-2 hours",
      recommendedRole: "SEO manager with developer support",
    },
    template: {
      fixStrategy: FIX_STRATEGIES.SITE_CONFIG,
      suggestedFix: "Review the template or site-wide rule applying this setting, and limit it to the pages that should genuinely stay out of search.",
      bestApproach: "One rule is affecting the whole group; correct that rule instead of overriding pages individually.",
      effort: "Medium",
      effortDetail: "Half a day",
      recommendedRole: "Web developer",
    },
  },
  [REPAIR_TYPES.THIN_OR_DUPLICATE_TEMPLATE]: {
    label: "Thin or repeated page content",
    groupTitle: "Give near-identical pages their own content",
    page: {
      fixStrategy: FIX_STRATEGIES.CONTENT,
      suggestedFix: "Add content to this page that a visitor could not get from any other page on the site.",
      bestApproach: "Expand this page directly, or merge it into the stronger page covering the same topic.",
      effort: "Medium",
      effortDetail: "2-4 hours",
      recommendedRole: "Content editor",
    },
    template: {
      fixStrategy: FIX_STRATEGIES.TEMPLATE,
      suggestedFix: "Change the template so each page renders its own details, and merge or remove the pages that cannot carry unique content.",
      bestApproach: "Decide which pages deserve to exist first, then fix the template that makes the survivors look identical.",
      effort: "High",
      effortDetail: "1-2 days",
      recommendedRole: "SEO manager with content support",
    },
  },
});

/**
 * Used when the scanner reports a rule this library has no mapping for.
 *
 * Effort, role, and strategy are deliberately empty here. Inventing "Low ·
 * 1-2 hours" for a repair FixList does not recognize would be a confident
 * guess, and the whole point of this layer is that its output is knowable.
 * The customer gets an honest fallback instruction and the repair's own
 * evidence instead.
 */
const UNMAPPED_SUGGESTION = Object.freeze({
  label: "Unrecognized repair",
  groupTitle: "Repairs to review manually",
  page: Object.freeze({
    fixStrategy: "",
    suggestedFix: REPAIR_SUGGESTION_FALLBACK,
    bestApproach: "Use the evidence below to decide whether this is a single-page change or a shared template change.",
    effort: "",
    effortDetail: "",
    recommendedRole: "",
  }),
  template: Object.freeze({
    fixStrategy: "",
    suggestedFix: REPAIR_SUGGESTION_FALLBACK,
    bestApproach: "Use the evidence below to decide whether this is a single-page change or a shared template change.",
    effort: "",
    effortDetail: "",
    recommendedRole: "",
  }),
});

function clean(value = "") {
  return String(value || "").trim();
}

function lower(value = "") {
  return clean(value).toLowerCase();
}

function ruleOf(item = {}) {
  return lower(
    item.rule
      || item.rule_id
      || item.ruleId
      || item.issue_type
      || item.original?.rule
      || item.original?.rule_id
      || item.original?.issue_type,
  );
}

function affectedPagesOf(item = {}) {
  const values = item.affectedPages
    || item.affected_pages
    || item.original?.affected_pages
    || [];
  return Array.isArray(values) ? values.filter(Boolean).map(String) : [];
}

function pageCountOf(item = {}) {
  const reported = Number(item.pageCount ?? item.page_count ?? item.original?.page_count ?? 0);
  return Math.max(Number.isFinite(reported) ? reported : 0, affectedPagesOf(item).length);
}

function templateFamilyOf(item = {}) {
  return lower(
    item.templateFamily
      || item.pageTemplateFamily
      || item.page_template_family
      || item.original?.page_template_family,
  );
}

function repairSurfaceOf(item = {}) {
  return lower(
    item.repairSurface
      || item.repair_surface
      || item.implementation_surface
      || item.original?.repair_surface,
  );
}

/**
 * Roles and effort the scanner already published outrank this library.
 *
 * `needs_developer` is a scanner bucket, not an inference, so it is honored the
 * same way an explicit role string would be.
 */
function scannerRoleOf(item = {}) {
  const explicit = clean(
    item.recommendedRole
      || item.recommended_role
      || item.who_can_do_this
      || item.original?.who_can_do_this,
  );
  if (explicit) return explicit;
  if (item.needsHelp === true || lower(item.bucket) === "needs_developer") return "Web developer";
  return "";
}

function scannerEffortOf(item = {}) {
  return clean(
    item.estimatedTime
      || item.estimated_time
      || item.time_estimate
      || item.original?.estimated_time,
  );
}

function sharedRepairConfirmedOf(item = {}) {
  const context = item.priorityContext || item.priority_context || item.original?.priority_context || {};
  return Boolean(
    item.sharedRepairConfirmed
      || item.shared_repair_confirmed
      || item.repairLeverageConfirmed
      || item.repair_leverage_confirmed
      || item.original?.shared_repair_confirmed
      || context?.shared_repair_confirmed,
  );
}

const TEMPLATE_SURFACES = Object.freeze([
  "template",
  "cms_field",
  "cms field",
  "shared_navigation",
  "shared navigation",
  "theme",
  "layout",
]);

/**
 * Decide whether the customer should be pointed at a template rather than a
 * page. This reads published evidence only; it never guesses from page count
 * alone that one template edit is sufficient.
 */
export function repairFixScope(item = {}) {
  if (sharedRepairConfirmedOf(item)) return "template";
  const surface = repairSurfaceOf(item);
  if (surface && TEMPLATE_SURFACES.some((value) => surface.includes(value))) return "template";
  const family = templateFamilyOf(item);
  if (pageCountOf(item) > 1 && family && family !== "mixed") return "template";
  return "page";
}

export function repairTypeOf(item = {}) {
  const rule = ruleOf(item);
  if (!rule) return "";
  const exact = RULE_REPAIR_TYPES[rule];
  if (exact) return exact;
  for (const [pattern, type] of RULE_PATTERNS) {
    if (pattern.test(rule)) return type;
  }
  return "";
}

export function repairSuggestionEntry(repairType = "") {
  return SUGGESTION_LIBRARY[lower(repairType)] || null;
}

/**
 * Build the customer-facing suggested fix for one repair.
 *
 * Every field a component can render is guaranteed to be a string. An
 * unrecognized rule returns `suggestionAvailable: false` with an explicit
 * `fallback`, so `undefined` can never reach the UI, and the interface can tell
 * a real recommendation apart from a manual-review placeholder.
 *
 * Scanner-published remediation copy is never discarded: when the repair
 * carries its own recommendation it becomes `suggestedFix`, and this table
 * supplies only the strategy, effort, role, and best-approach guidance the
 * scanner does not publish.
 */
export function repairSuggestion(item = {}) {
  const repairType = repairTypeOf(item);
  const entry = repairSuggestionEntry(repairType) || UNMAPPED_SUGGESTION;
  const suggestionAvailable = Boolean(repairType);
  const scope = repairFixScope(item);
  const variant = entry[scope] || entry.page;
  const scannerFix = clean(
    item.recommendation
      || item.simple_next_step
      || item.recommended_value
      || item.original?.simple_next_step
      || item.original?.recommended_value,
  );
  const fallback = suggestionAvailable ? "" : REPAIR_SUGGESTION_FALLBACK;
  const suggestedFix = scannerFix || clean(variant.suggestedFix) || REPAIR_SUGGESTION_FALLBACK;
  const scannerRole = scannerRoleOf(item);
  const scannerEffort = scannerEffortOf(item);
  const effort = clean(variant.effort);
  const effortDetail = scannerEffort || clean(variant.effortDetail);
  const recommendedRole = scannerRole || clean(variant.recommendedRole);
  const fixStrategy = clean(variant.fixStrategy);

  return Object.freeze({
    version: REPAIR_SUGGESTION_VERSION,
    libraryVersion: REPAIR_SUGGESTION_LIBRARY_VERSION,
    repairType,
    suggestionAvailable,
    fallback,
    label: clean(entry.label),
    groupTitle: clean(entry.groupTitle),
    fixScope: scope,
    fixStrategy,
    fixStrategyLabel: FIX_STRATEGY_LABELS[fixStrategy] || "",
    suggestedFix,
    suggestedFixSource: scannerFix
      ? "scanner_evidence"
      : (suggestionAvailable ? "fixlist_library" : "manual_review_fallback"),
    librarySuggestedFix: clean(variant.suggestedFix),
    bestApproach: clean(variant.bestApproach),
    effort,
    effortDetail,
    effortLabel: effort && effortDetail ? `${effort} · ${effortDetail}` : effort || effortDetail,
    effortSource: scannerEffort ? "scanner_evidence" : (effortDetail ? "fixlist_library" : ""),
    recommendedRole,
    recommendedRoleSource: scannerRole ? "scanner_evidence" : (recommendedRole ? "fixlist_library" : ""),
    affectedPageCount: pageCountOf(item),
  });
}

function normalizePageKey(value = "") {
  const raw = clean(value);
  if (!raw) return "";
  try {
    const url = new URL(raw, "https://fixlist.invalid");
    return `${url.pathname || "/"}${url.search || ""}`.replace(/\/$/, "") || "/";
  } catch {
    return raw.replace(/^https?:\/\/[^/]+/i, "").replace(/\/$/, "") || "/";
  }
}

function repairIdOf(item = {}) {
  return clean(item.id || item.fix_id || item.repair_fingerprint);
}

/**
 * Summarize repairs that are the same template problem.
 *
 * This is a read-only rollup for presentation. It never merges, hides,
 * reorders, or rewrites repairs: every underlying repair keeps its own row,
 * evidence, and priority. The summary only tells the customer that one shared
 * change covers several of the rows they are already looking at.
 */
export function buildRepairGroupSummaries(rows = [], { minimumRepairs = 2 } = {}) {
  const list = Array.isArray(rows) ? rows.filter(Boolean) : [];
  const groups = new Map();

  list.forEach((row) => {
    const item = row?.item || row;
    if (!item) return;
    const suggestion = row?.suggestion || repairSuggestion(item);
    if (!suggestion.suggestionAvailable || suggestion.fixScope !== "template") return;

    const key = suggestion.repairType;
    const found = groups.get(key) || {
      key: `repair-group:${key}`,
      repairType: key,
      title: suggestion.groupTitle,
      suggestion,
      repairCount: 0,
      memberIds: [],
      pages: new Set(),
      templates: new Set(),
      reportedPageCount: 0,
      pageEvidenceComplete: true,
    };

    found.repairCount += 1;
    const id = repairIdOf(item);
    if (id) found.memberIds.push(id);
    for (const page of affectedPagesOf(item)) {
      const pageKey = normalizePageKey(page);
      if (pageKey) found.pages.add(pageKey);
    }
    const reported = pageCountOf(item);
    found.reportedPageCount += reported;
    // A saved result can report more affected pages than it carries URLs for.
    // When that happens the deduplicated union undercounts, and the summary
    // must say "at least" rather than state an exact figure.
    if (affectedPagesOf(item).length < reported) found.pageEvidenceComplete = false;
    const family = templateFamilyOf(item);
    if (family) found.templates.add(family);
    groups.set(key, found);
  });

  const threshold = Math.max(2, Number(minimumRepairs) || 2);
  return Array.from(groups.values())
    .filter((group) => group.repairCount >= threshold)
    .map((group) => ({
      key: group.key,
      repairType: group.repairType,
      title: group.title,
      repairCount: group.repairCount,
      memberIds: group.memberIds,
      // Deduplicated: two repairs touching the same URL are one affected page,
      // never two. Summing reported counts would inflate the headline figure.
      pageCount: group.pages.size > 0 ? group.pages.size : group.reportedPageCount,
      pageCountExact: group.pages.size > 0 && group.pageEvidenceComplete,
      reportedPageCount: group.reportedPageCount,
      templateCount: group.templates.size,
      templates: Array.from(group.templates),
      fixOnce: group.suggestion.bestApproach,
      suggestion: group.suggestion,
    }));
}
