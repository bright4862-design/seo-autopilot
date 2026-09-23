import { REPAIR_SUGGESTION_FALLBACK } from "./repairSuggestions.js";

/**
 * Deterministic role-specific explanation copy for FixList repairs.
 *
 * This module is presentation-only. It never replaces scanner-authored
 * remediation, changes repair priority, or writes to a repair. Runtime output
 * is a fixed table lookup keyed by the scanner rule and the selected viewer
 * role. Copy is authored/reviewed before commit; there is no runtime model call.
 */
export const REPAIR_ROLE_EXPLANATION_VERSION = "repair_role_explanation_v1";
export const REPAIR_ROLE_EXPLANATION_LIBRARY_VERSION = "role_explanation_copy_v3_20260923_top11";

export const REPAIR_EXPLANATION_ROLES = Object.freeze(["owner", "marketing", "seo", "developer"]);
export const REPAIR_EXPLANATION_FALLBACK = REPAIR_SUGGESTION_FALLBACK;

export const REPAIR_ROLE_VIEW_COPY = Object.freeze({
  owner: Object.freeze({ label: "Owner / CEO", heading: "Business decision", summary: "Decide what needs attention and what to ask your team to check." }),
  marketing: Object.freeze({ label: "Marketing", heading: "Content review", summary: "Focus on page messaging, visitor journeys and content changes." }),
  seo: Object.freeze({ label: "SEO", heading: "SEO review", summary: "Review the search implications and checks behind each repair." }),
  developer: Object.freeze({ label: "Developer", heading: "Implementation guidance", summary: "Focus on where to make each change and how to verify it." }),
});

const ROLE_EXPLANATIONS = Object.freeze({
  redirect_chain: Object.freeze({
    owner: "This address takes more than one redirect to reach its destination. Confirm which page it should open, then ask your website maintainer to remove unnecessary stops. Keep any redirects needed for routing or tracking.",
    marketing: "Check that the redirect chain ends at the intended page for visitors or a campaign. Confirm any tracking requirements before asking for a direct route, then test the links people use to reach it.",
    seo: "Review the reported chain and confirm the intended final destination, its indexability and canonical signal. Remove unnecessary hops where appropriate, then check the response sequence again.",
    developer: "Trace the redirect rules serving the reported address. Once the destination is confirmed, consolidate unnecessary hops in the responsible routing layer, preserve required paths and query parameters, and retest the full response sequence.",
  }),
  meta_description_unusable: Object.freeze({
    owner: "The scan found a missing or unusable search description. Ask your content editor to confirm each affected page’s purpose and supply an accurate summary. This gives search engines a description to consider; it does not guarantee the text they will show.",
    marketing: "Write a short, accurate summary of what each affected page offers and why someone would visit it. Use page-specific details instead of repeating one description everywhere; search engines may still choose other text for a search result.",
    seo: "Check whether each affected description is missing, empty or malformed, then review its relevance to the page and search intent. A valid description gives search engines a snippet option; it does not guarantee a particular snippet or a ranking improvement.",
    developer: "Inspect the affected page’s HTML document head and the CMS field or template that emits its meta description. Check the reported missing, empty or malformed value, correct the responsible source, and verify the generated HTML after publishing.",
  }),
  title_over_pixel_limit: Object.freeze({
    owner: "These page titles may be too wide to appear in full in search results. Agree on the key message for each page, then ask your content editor to remove wording that adds little value. Keep the title accurate and easy to recognize.",
    marketing: "Keep the page’s distinctive offer, topic or location near the start of the title. Remove repetition or unnecessary brand wording while preserving a natural, accurate message; the displayed search title may still vary.",
    seo: "Review the flagged title’s pixel width and put its most useful identifying terms early. Check intent, distinctiveness and readability rather than enforcing a fixed character count; search engines may truncate or rewrite the displayed title.",
    developer: "Inspect the final title element and the CMS field or template that generates it. If repeated suffixes or template text add unnecessary width, adjust that source with the content owner and check representative generated titles after publishing.",
  }),
  sitemap_redirect: Object.freeze({
    owner: "The scan found redirects in your sitemap, the list of page addresses you give search engines. Ask whoever maintains it to check the destinations and list the intended final addresses directly.",
    marketing: "Some sitemap entries redirect to another address. Confirm that each destination is the page you want people to discover before updating the entries.",
    seo: "The scan found redirecting sitemap URLs. Check that each final destination is the intended indexable canonical URL before replacing the sitemap entry.",
    developer: "Trace the affected sitemap entries to their source. Once the intended destinations are confirmed, update the stored URLs or generator responsible and check the sitemap again.",
  }),
  image_alt_text: Object.freeze({
    owner: "The scan found an informative image without a usable text alternative. Add a short description of what it communicates so people who cannot see it can access that information.",
    marketing: "Check what the flagged image adds to the page. Write alt text that conveys that information in context; an image used only for decoration can keep an empty alt attribute.",
    seo: "Review the flagged image in context before writing alt text. Describe its purpose clearly, avoid keyword stuffing, and preserve empty alt attributes for purely decorative images.",
    developer: "Inspect the flagged image and its alt attribute. For an informative image, supply a meaningful value from the content source; preserve intentionally empty alt attributes for decorative images.",
  }),
  missing_h1: Object.freeze({
    owner: "The scan did not find an H1, the code label for a main heading. A headline may already be visible; ask your website editor to check how it is marked up.",
    marketing: "The scan did not find an H1. Check the existing headline before writing a new one: it should express the page’s purpose and be marked up as its main heading.",
    seo: "No H1 was found in the collected page evidence. Check the page before adding one, then use a descriptive main heading that matches its topic.",
    developer: "No H1 was found in the collected page evidence. Check the HTML and rendered page; if a main headline already exists, use the appropriate heading markup rather than adding a duplicate.",
  }),
  canonical_missing: Object.freeze({
    owner: "The scan did not find a canonical signal, which tells search engines your preferred page address. Ask your website maintainer whether one is needed and which address it should name.",
    marketing: "The scan did not find a preferred-page address signal. Confirm which version of the content should represent this page in search before requesting a canonical change.",
    seo: "No canonical was observed in the collected evidence. Review the intended indexable URL and any existing canonical signals before deciding whether to add or correct one.",
    developer: "The scan did not find a canonical signal. Check the document head and HTTP headers first; if a canonical is needed, emit the intended absolute URL and verify the target and consistency.",
  }),
  potential_orphan_pages: Object.freeze({
    owner: "The scan found limited evidence of links leading to these pages within the pages checked. Review how visitors should reach the pages that matter; links may exist outside this scan.",
    marketing: "These pages may be hard to discover from the pages checked. Review where they belong in the visitor journey and add relevant links where useful; the scan does not cover every possible route.",
    seo: "The sampled crawl found weak or missing incoming-link evidence for these pages. Confirm their purpose and review links beyond the sample before classifying them as orphaned.",
    developer: "Review incoming links for the listed pages, including sources outside the crawl sample. If links are needed, update the appropriate navigation or content source and verify that the crawler can follow them.",
  }),
  internal_link_redirect: Object.freeze({
    owner: "The scan found links that take an extra step through a redirect. Check that the destination is still the right page before asking for those links to point there directly.",
    marketing: "Some internal links redirect before reaching their destination. Confirm the intended visitor journey, including any tracking or routing needs, before changing the linked addresses.",
    seo: "The scan found internal links that redirect. Check the intended destination and redirect purpose before updating source links to an appropriate final URL.",
    developer: "Inspect the reported source links and redirect behavior. Where a direct link is appropriate, update the responsible content or template and verify the destination; keep intentional routing requirements intact.",
  }),
  failed_page: Object.freeze({
    owner: "FixList could not verify this page during the scan. Check it again before deciding what needs fixing; this result alone does not show that visitors cannot open it.",
    marketing: "The scan could not verify this page. Test the visitor journey before replacing links or changing campaign destinations; a scanner failure may not affect visitors.",
    seo: "The page could not be verified in this scan. Review the failure evidence and repeat the check before classifying it as a persistent availability or crawl-access problem.",
    developer: "Reproduce the failed request and inspect the response, network conditions, server logs, and bot or rate-limit rules. Establish the cause before changing routing or declaring the page unavailable.",
  }),
  duplicate_title_template: Object.freeze({
    owner: "The scan found pages with matching or repeated title patterns. Check whether they serve different purposes; distinct pages should have titles that help people tell them apart.",
    marketing: "Review the repeated titles against each page’s purpose. For distinct pages, include the product, place, topic, or offer that makes each useful while keeping any helpful brand wording.",
    seo: "Review the pages grouped by the repeated title pattern. Confirm which should be distinct indexable pages before changing titles; the pattern alone does not establish the cause.",
    developer: "Trace the repeated titles to their content fields or generation logic. If a shared template causes the repetition, add the appropriate page-specific field and check representative pages before rollout.",
  }),
});

function clean(value = "") {
  return String(value || "").trim();
}

function ruleOf(item = {}) {
  return clean(
    item.rule
      || item.rule_id
      || item.ruleId
      || item.issue_type
      || item.original?.rule
      || item.original?.rule_id
      || item.original?.issue_type,
  ).toLowerCase();
}

/**
 * Return role-specific explanation copy without changing remediation or repair
 * evidence. Missing roles and unmapped rules fail to the existing generic
 * manual-review wording rather than guessing which audience/copy applies.
 */
export function repairRoleExplanation(item = {}, role = "") {
  const normalizedRole = clean(role).toLowerCase();
  const rule = ruleOf(item);
  const entry = ROLE_EXPLANATIONS[rule];
  const roleSupported = REPAIR_EXPLANATION_ROLES.includes(normalizedRole);
  const explanation = roleSupported ? clean(entry?.[normalizedRole]) : "";
  const explanationAvailable = Boolean(explanation);

  return Object.freeze({
    version: REPAIR_ROLE_EXPLANATION_VERSION,
    libraryVersion: REPAIR_ROLE_EXPLANATION_LIBRARY_VERSION,
    rule,
    role: roleSupported ? normalizedRole : "",
    explanationAvailable,
    explanation: explanation || REPAIR_EXPLANATION_FALLBACK,
    explanationSource: explanationAvailable ? "fixlist_role_library" : "manual_review_fallback",
    fallback: explanationAvailable ? "" : REPAIR_EXPLANATION_FALLBACK,
  });
}

export function roleExplanationEntry(rule = "") {
  return ROLE_EXPLANATIONS[clean(rule).toLowerCase()] || null;
}
