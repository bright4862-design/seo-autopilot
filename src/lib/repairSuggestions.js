/**
 * Deterministic repair suggestion layer.
 *
 * Pipeline position:
 *   website -> scanner -> findings + evidence -> prioritization -> THIS LAYER -> FixList UI
 *
 * This layer is the last step before presentation and the first one that is
 * allowed to be opinionated about what a customer should *do*. It reads the
 * repair the scanner already produced and answers the questions the finding
 * itself does not: what is the fix, where is it applied, how big is it, and
 * who does it.
 *
 * Hard boundaries:
 * - No crawler, scan logic, detection rule, scoring, ranking, or persistence
 *   behavior is involved. Nothing here can change what was found or its order.
 * - No field is written back onto a repair, a scan payload, or an entity. Only
 *   fields the payload already carries are read.
 * - No language model participates. Every value is a fixed table lookup plus
 *   evidence the scanner published, so one repair always yields one suggestion.
 * - Scanner-authored copy always wins. Where the scanner published its own
 *   remediation, role, or effort, that is shown and this table steps aside.
 */

/** Shape/behavior version of the suggestion model returned by this module. */
export const REPAIR_SUGGESTION_VERSION = "repair_suggestion_v1_deterministic";

/**
 * Content version of the suggestion library itself.
 *
 * Nothing persists this today. It is carried on every suggestion so that later
 * A/B tests, improvement tracking, customer feedback, and scan-to-scan
 * comparisons can say which wording a customer actually saw. Bump it whenever
 * the suggested-fix copy, scope, effort, or role guidance changes.
 */
export const REPAIR_SUGGESTION_LIBRARY_VERSION = "v1";

/**
 * Shown whenever the scanner reports a rule this library does not map yet.
 * The UI renders this instead of an empty or undefined suggested fix.
 */
export const REPAIR_SUGGESTION_FALLBACK = "Review this issue based on the evidence collected.";

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

/** Where the repair is applied. Deliberately three values, not a taxonomy. */
export const FIX_SCOPES = Object.freeze(["page", "template", "sitewide"]);

export const FIX_SCOPE_LABELS = Object.freeze({
  page: "Page",
  template: "Template",
  sitewide: "Sitewide",
});

export const EFFORT_LEVELS = Object.freeze(["low", "medium", "high"]);

export const EFFORT_LABELS = Object.freeze({
  low: "Low",
  medium: "Medium",
  high: "High",
});

export const REPAIR_ROLES = Object.freeze(["SEO manager", "Developer", "Content team"]);

/**
 * Exact scanner rule identifiers, mapped to the repair type a customer acts on.
 * Several scanner rules describe one customer repair; that collapsing happens
 * here rather than in a component, and never in the scanner.
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

/**
 * The suggestion table.
 *
 * `single` is used when the scan carries no evidence that one shared change
 * covers the repair; `shared` is used when it does. Some repairs are sitewide
 * in both cases because that is simply where the fix lives: a redirect chain is
 * repaired in link sources and redirect rules, not on the page that reports it.
 */
const SUGGESTION_LIBRARY = Object.freeze({
  [REPAIR_TYPES.MISSING_TITLE]: {
    label: "Missing page title",
    groupTitle: "Add missing page titles",
    single: {
      fixScope: "page",
      suggestedFix: "Add a page title that names what this page is about, in the words a visitor would use.",
      bestApproach: "Write the title directly on this page rather than changing a shared template.",
      effort: "low",
      role: "Content team",
    },
    shared: {
      fixScope: "template",
      groupFix: "Add titles in the shared template once.",
      suggestedFix: "Add a title rule to the template that builds these pages so every page generates its own title.",
      bestApproach: "Fix the shared template once instead of typing a title into each affected page.",
      effort: "medium",
      role: "Developer",
    },
  },
  [REPAIR_TYPES.DUPLICATE_TITLE]: {
    label: "Repeated page title",
    groupTitle: "Make page titles unique",
    single: {
      fixScope: "page",
      suggestedFix: "Rewrite this page's title so it describes this page instead of repeating another page's title.",
      bestApproach: "Edit the title on this page; no template change is needed for a single page.",
      effort: "low",
      role: "Content team",
    },
    shared: {
      fixScope: "template",
      groupFix: "Update the shared title pattern once.",
      suggestedFix: "Update the shared title pattern so it includes the field that makes each page different, such as the product, place, or topic name.",
      bestApproach: "Change the one title pattern rather than editing each page by hand.",
      effort: "medium",
      role: "SEO manager",
    },
  },
  [REPAIR_TYPES.MISSING_META_DESCRIPTION]: {
    label: "Missing search description",
    groupTitle: "Improve search descriptions",
    single: {
      fixScope: "page",
      suggestedFix: "Add a short search description to this page explaining what a visitor can do here.",
      bestApproach: "Write it directly on the page; a template change is not needed for one page.",
      effort: "low",
      role: "Content team",
    },
    shared: {
      fixScope: "template",
      groupFix: "Update shared templates once.",
      suggestedFix: "Update the page template to generate unique meta descriptions, so each page builds its own description from its own content.",
      bestApproach: "Update the shared templates once rather than writing a description for every affected page.",
      effort: "medium",
      role: "SEO manager",
    },
  },
  [REPAIR_TYPES.DUPLICATE_META_DESCRIPTION]: {
    label: "Repeated search description",
    groupTitle: "Make search descriptions unique",
    single: {
      fixScope: "page",
      suggestedFix: "Rewrite this page's search description so it is specific to this page.",
      bestApproach: "Edit the description on this page directly.",
      effort: "low",
      role: "Content team",
    },
    shared: {
      fixScope: "template",
      groupFix: "Update the shared description pattern once.",
      suggestedFix: "Change the template's description pattern so it pulls page-specific content instead of repeating one fixed sentence.",
      bestApproach: "Fix the shared description pattern once; hand-editing each page will drift back over time.",
      effort: "medium",
      role: "SEO manager",
    },
  },
  [REPAIR_TYPES.MISSING_H1]: {
    label: "Missing main heading",
    groupTitle: "Add clear main headings",
    single: {
      fixScope: "page",
      suggestedFix: "Add one clear main heading at the top of this page that states its main topic.",
      bestApproach: "Add the heading in the page editor for this page.",
      effort: "low",
      role: "Content team",
    },
    shared: {
      fixScope: "template",
      groupFix: "Add the heading to the shared template once.",
      suggestedFix: "Add one main heading to the template that builds these pages, filled from each page's own title field.",
      bestApproach: "Fix the shared template once so every page built from it gets a heading.",
      effort: "medium",
      role: "Developer",
    },
  },
  [REPAIR_TYPES.MULTIPLE_H1]: {
    label: "More than one main heading",
    groupTitle: "Reduce pages to one main heading",
    single: {
      fixScope: "page",
      suggestedFix: "Keep one main heading on this page and demote the others to sub-headings.",
      bestApproach: "Adjust the heading levels in this page's content.",
      effort: "low",
      role: "Content team",
    },
    shared: {
      fixScope: "template",
      groupFix: "Fix the shared template heading levels once.",
      suggestedFix: "Change the template or shared blocks so only the page title renders as the main heading and other blocks render as sub-headings.",
      bestApproach: "Fix the template or reusable block once; the duplicate heading is being generated, not typed.",
      effort: "medium",
      role: "Developer",
    },
  },
  [REPAIR_TYPES.CANONICAL_ISSUE]: {
    label: "Preferred URL not set clearly",
    groupTitle: "Confirm the preferred version of each page",
    single: {
      fixScope: "page",
      suggestedFix: "Set this page's preferred-URL setting to its own final, working address.",
      bestApproach: "Correct the setting on this page and confirm the target returns a normal 200 response.",
      effort: "low",
      role: "Developer",
    },
    shared: {
      fixScope: "template",
      groupFix: "Correct the preferred-URL rule once.",
      suggestedFix: "Correct the preferred-URL rule in the template or CMS field that generates it, so each page points at its own final address.",
      bestApproach: "Fix the one rule that generates these values instead of editing pages individually.",
      effort: "medium",
      role: "Developer",
    },
  },
  [REPAIR_TYPES.REDIRECT_CHAIN]: {
    label: "Unnecessary redirects",
    groupTitle: "Remove unnecessary redirects",
    // Sitewide in both cases: the repair lives in the links and redirect rules
    // that point at the old URL, which are rarely on the reported page.
    single: {
      fixScope: "sitewide",
      suggestedFix: "Replace internal links pointing to redirected URLs with the final destination URL.",
      bestApproach: "Fix the source links and redirect rules instead of manually editing individual URLs.",
      effort: "low",
      role: "Developer",
    },
    shared: {
      fixScope: "sitewide",
      groupFix: "Update link sources and redirect rules once.",
      suggestedFix: "Update the shared navigation, templates, and redirect rules so links point straight at the final URL in one hop.",
      bestApproach: "Fix the source links and templates instead of manually editing individual URLs.",
      effort: "medium",
      role: "Developer",
    },
  },
  [REPAIR_TYPES.BROKEN_INTERNAL_LINK]: {
    label: "Broken internal link",
    groupTitle: "Repair broken internal links",
    single: {
      fixScope: "page",
      suggestedFix: "Point this link at a working page, or restore the page it was meant to reach.",
      bestApproach: "Fix the link at its source page rather than adding a redirect to cover it.",
      effort: "low",
      role: "Content team",
    },
    shared: {
      fixScope: "sitewide",
      groupFix: "Fix the shared navigation block once.",
      suggestedFix: "Correct the shared navigation, footer, or template block that repeats this broken link across pages.",
      bestApproach: "One shared block is generating most of these links; fix it there rather than page by page.",
      effort: "medium",
      role: "Developer",
    },
  },
  [REPAIR_TYPES.HARD_TO_DISCOVER_PAGE]: {
    label: "Hard to discover page",
    groupTitle: "Make isolated pages easier to reach",
    single: {
      fixScope: "sitewide",
      suggestedFix: "Confirm whether this page still matters, then link to it from a related page or from your navigation.",
      bestApproach: "Decide first whether the page should exist; only then add links to it.",
      effort: "low",
      role: "SEO manager",
    },
    shared: {
      fixScope: "sitewide",
      groupFix: "Add one hub or listing page.",
      suggestedFix: "Add these pages to a listing, hub, or navigation block so they are reachable by following links from your homepage.",
      bestApproach: "Add one listing or hub page that links to the whole set rather than adding links one at a time.",
      effort: "medium",
      role: "SEO manager",
    },
  },
  [REPAIR_TYPES.SITEMAP_REDIRECT]: {
    label: "Sitemap lists non-final URLs",
    groupTitle: "List only final URLs in the sitemap",
    single: {
      fixScope: "sitewide",
      suggestedFix: "Replace this sitemap entry with the final URL it currently redirects to.",
      bestApproach: "Correct the sitemap source or generator, not the published file by hand.",
      effort: "low",
      role: "Developer",
    },
    shared: {
      fixScope: "sitewide",
      groupFix: "Fix the sitemap generator once.",
      suggestedFix: "Change the sitemap generator so it publishes each page's final working URL and drops redirected entries.",
      bestApproach: "Fix the generator once; hand-edited sitemaps are rebuilt and lose the change.",
      effort: "medium",
      role: "Developer",
    },
  },
  [REPAIR_TYPES.NOINDEX_ISSUE]: {
    label: "Page blocked from search",
    groupTitle: "Resolve pages blocked from search",
    single: {
      fixScope: "page",
      suggestedFix: "Confirm whether this page should appear in search. If it should, remove the setting that is keeping it out.",
      bestApproach: "Check the intent before changing anything: some pages are hidden deliberately.",
      effort: "low",
      role: "SEO manager",
    },
    shared: {
      fixScope: "sitewide",
      groupFix: "Correct the shared indexing rule once.",
      suggestedFix: "Review the template or site-wide rule applying this setting, and limit it to the pages that should genuinely stay out of search.",
      bestApproach: "One rule is affecting the whole group; correct that rule instead of overriding pages individually.",
      effort: "medium",
      role: "Developer",
    },
  },
  [REPAIR_TYPES.THIN_OR_DUPLICATE_TEMPLATE]: {
    label: "Thin or repeated page content",
    groupTitle: "Give near-identical pages their own content",
    single: {
      fixScope: "page",
      suggestedFix: "Add content to this page that a visitor could not get from any other page on the site.",
      bestApproach: "Expand this page directly, or merge it into the stronger page covering the same topic.",
      effort: "medium",
      role: "Content team",
    },
    shared: {
      fixScope: "template",
      groupFix: "Fix the template, then merge weak pages.",
      suggestedFix: "Change the template so each page renders its own details, and merge or remove the pages that cannot carry unique content.",
      bestApproach: "Decide which pages deserve to exist first, then fix the template that makes the survivors look identical.",
      effort: "high",
      role: "SEO manager",
    },
  },
});

/**
 * Used when the scanner reports a rule this library has no mapping for.
 *
 * Scope, effort, and role are deliberately empty. Inventing "Page · Low · SEO
 * manager" for a repair FixList does not recognize would be a confident guess,
 * and the point of this layer is that its output is knowable. The customer gets
 * an honest instruction and the repair's own evidence instead.
 */
const UNMAPPED_SUGGESTION = Object.freeze({
  label: "Unrecognized repair",
  groupTitle: "Repairs to review manually",
  single: Object.freeze({
    fixScope: "",
    suggestedFix: REPAIR_SUGGESTION_FALLBACK,
    bestApproach: "Use the evidence below to decide whether this is a single-page change or a shared template change.",
    effort: "",
    role: "",
  }),
  shared: Object.freeze({
    fixScope: "",
    groupFix: "",
    suggestedFix: REPAIR_SUGGESTION_FALLBACK,
    bestApproach: "Use the evidence below to decide whether this is a single-page change or a shared template change.",
    effort: "",
    role: "",
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
 * same way an explicit role string would be. Known synonyms are normalized into
 * the three-role vocabulary; anything else is passed through untouched, because
 * scanner text is evidence and this layer does not overwrite evidence.
 */
const ROLE_SYNONYMS = Object.freeze({
  "web developer": "Developer",
  "front-end developer": "Developer",
  "frontend developer": "Developer",
  developer: "Developer",
  engineering: "Developer",
  "content editor": "Content team",
  "content team": "Content team",
  copywriter: "Content team",
  marketing: "SEO manager",
  "seo manager": "SEO manager",
  seo: "SEO manager",
});

/**
 * The scanner's own bucket names are internal identifiers, not customer copy.
 *
 * Passing unknown text through is right for human role text a scanner might
 * legitimately publish ("Store manager"), but `your_web_person` reached FixList
 * cards verbatim because it was simply unknown to the synonym table.
 */
const INTERNAL_ROLE_TOKENS = Object.freeze({
  your_web_person: "Developer",
  web_person: "Developer",
  your_developer: "Developer",
  content_editor: "Content team",
  seo_specialist: "SEO manager",
  you: "You",
  owner: "You",
});

function normalizeRole(value = "") {
  const raw = clean(value);
  if (!raw) return "";
  const lowered = raw.toLowerCase();
  const known = ROLE_SYNONYMS[lowered] || INTERNAL_ROLE_TOKENS[lowered];
  if (known) return known;
  // A snake_case token that reached here is an internal identifier leaking, not
  // evidence. Falling back to empty lets the curated library role fill in,
  // which is always better copy than printing the enum.
  if (/^[a-z0-9]+(?:_[a-z0-9]+)+$/.test(lowered)) return "";
  return raw;
}

function scannerRoleOf(item = {}) {
  const explicit = clean(
    item.recommendedRole
      || item.recommended_role
      || item.who_can_do_this
      || item.original?.who_can_do_this,
  );
  if (explicit) return normalizeRole(explicit);
  if (item.needsHelp === true || lower(item.bucket) === "needs_developer") return "Developer";
  return "";
}

/**
 * Only the scanner may claim a time estimate. The library states effort as
 * low/medium/high and never invents an hour figure.
 */
function scannerEffortDetailOf(item = {}) {
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
 * Does the scan carry evidence that one shared change covers this repair?
 *
 * This reads published evidence only. A high page count alone is never treated
 * as proof that one template edit is sufficient.
 */
export function hasSharedRepairEvidence(item = {}) {
  if (sharedRepairConfirmedOf(item)) return true;
  const surface = repairSurfaceOf(item);
  if (surface && TEMPLATE_SURFACES.some((value) => surface.includes(value))) return true;
  const family = templateFamilyOf(item);
  return pageCountOf(item) > 1 && Boolean(family) && family !== "mixed";
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

/** Where this repair is applied: page, template, or sitewide. */
export function repairFixScope(item = {}) {
  const entry = repairSuggestionEntry(repairTypeOf(item)) || UNMAPPED_SUGGESTION;
  const variant = hasSharedRepairEvidence(item) ? entry.shared : entry.single;
  return clean(variant.fixScope);
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
 * supplies only the scope, effort, role, and approach the scanner does not
 * publish.
 */
export function repairSuggestion(item = {}) {
  const repairType = repairTypeOf(item);
  const entry = repairSuggestionEntry(repairType) || UNMAPPED_SUGGESTION;
  const suggestionAvailable = Boolean(repairType);
  const shared = hasSharedRepairEvidence(item);
  const variant = shared ? entry.shared : entry.single;
  const scannerFix = clean(
    item.recommendation
      || item.simple_next_step
      || item.recommended_value
      || item.original?.simple_next_step
      || item.original?.recommended_value,
  );

  const scannerRole = scannerRoleOf(item);
  const scannerEffortDetail = scannerEffortDetailOf(item);
  const effort = lower(variant.effort);
  const effortLabel = EFFORT_LABELS[effort] || "";
  const role = scannerRole || clean(variant.role);
  const fixScope = clean(variant.fixScope);

  return Object.freeze({
    version: REPAIR_SUGGESTION_VERSION,
    libraryVersion: REPAIR_SUGGESTION_LIBRARY_VERSION,
    repairType,
    suggestionAvailable,
    fallback: suggestionAvailable ? "" : REPAIR_SUGGESTION_FALLBACK,
    label: clean(entry.label),
    groupTitle: clean(entry.groupTitle),
    sharedRepairEvidence: shared,
    fixScope,
    fixScopeLabel: FIX_SCOPE_LABELS[fixScope] || "",
    suggestedFix: scannerFix || clean(variant.suggestedFix) || REPAIR_SUGGESTION_FALLBACK,
    suggestedFixSource: scannerFix
      ? "scanner_evidence"
      : (suggestionAvailable ? "fixlist_library" : "manual_review_fallback"),
    librarySuggestedFix: clean(variant.suggestedFix),
    bestApproach: clean(variant.bestApproach),
    // Short imperative used by a group summary, so the parent states the
    // shared action once instead of repeating the full sentence per row.
    groupFix: clean(variant.groupFix),
    effort,
    effortLabel,
    // Only ever a scanner-published estimate. The library does not guess hours.
    effortDetail: scannerEffortDetail,
    effortDisplay: effortLabel && scannerEffortDetail
      ? `${effortLabel} · ${scannerEffortDetail}`
      : effortLabel || scannerEffortDetail,
    role,
    roleSource: scannerRole ? "scanner_evidence" : (role ? "fixlist_library" : ""),
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
 * Summarize repairs that are the same shared problem.
 *
 * This is a read-only rollup for presentation. It never merges, hides,
 * reorders, or rewrites repairs: every repair it counts is still rendered as
 * its own row, with its own evidence, affected URLs, and detection details.
 * The evidence remains the source of truth; this only tells the customer that
 * one change covers several of the rows they are already looking at.
 */
export function buildRepairGroupSummaries(rows = [], { minimumRepairs = 2 } = {}) {
  const list = Array.isArray(rows) ? rows.filter(Boolean) : [];
  const groups = new Map();

  list.forEach((row) => {
    const item = row?.item || row;
    if (!item) return;
    const suggestion = row?.suggestion || repairSuggestion(item);
    if (!suggestion.suggestionAvailable || !suggestion.sharedRepairEvidence) return;

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
      fixScope: group.suggestion.fixScope,
      fixScopeLabel: group.suggestion.fixScopeLabel,
      effortDisplay: group.suggestion.effortDisplay,
      role: group.suggestion.role,
      fixOnce: group.suggestion.groupFix || group.suggestion.bestApproach,
      suggestion: group.suggestion,
    }));
}
