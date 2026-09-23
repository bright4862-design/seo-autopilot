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
export const REPAIR_ROLE_EXPLANATION_LIBRARY_VERSION = "role_explanation_copy_v2_20260923_top8_missing_h1_actions";

export const REPAIR_EXPLANATION_ROLES = Object.freeze(["owner", "marketing", "seo", "developer"]);
export const REPAIR_EXPLANATION_FALLBACK = REPAIR_SUGGESTION_FALLBACK;

const ROLE_EXPLANATIONS = Object.freeze({
  sitemap_redirect: Object.freeze({
    owner: "Your sitemap is sending search engines through redirects instead of listing the final page addresses directly. Cleaning those entries makes the site easier to maintain and gives crawlers a clearer map.",
    marketing: "Some URLs submitted for discovery redirect before reaching the real page. Keep campaign and content destinations aligned with the final URLs so search visibility is not built on outdated addresses.",
    seo: "The XML sitemap contains redirecting URLs. Submit only final, indexable canonical destinations so sitemap signals agree with the URLs you want search engines to crawl and index.",
    developer: "The sitemap generator is emitting non-final URLs. Update its URL source or normalization so generated entries resolve directly to the intended 200-status canonical destinations.",
  }),
  image_alt_text: Object.freeze({
    owner: "FixList found a meaningful image without a usable text alternative. Adding a short description helps people who cannot see the image understand the information it contributes to the page.",
    marketing: "A meaningful image is missing its text alternative. Describe the information the image adds in the context of this page rather than repeating nearby copy or stuffing search terms.",
    seo: "Material image evidence shows a missing text alternative. Add concise, context-specific alt text for the informative image while continuing to leave genuinely decorative images empty.",
    developer: "Material image evidence shows a missing alt alternative. Expose a content-controlled alt value for the evidenced informative image; do not auto-fill filenames or change intentionally empty alt attributes on decorative images.",
  }),
  missing_h1: Object.freeze({
    owner: "FixList did not find an H1. Ask the page owner to confirm whether the visible headline is already the main heading; do not add a second headline until they check.",
    marketing: "FixList did not find an H1. Confirm that the visible headline clearly states the page’s purpose. If the wording is right, keep it and ask for H1 markup; otherwise write one clear main headline.",
    seo: "No H1 was found in the collected evidence. Check the rendered page for a descriptive main heading that matches its topic, then confirm it is marked as an H1 before recommending new copy.",
    developer: "No H1 was found in the collected evidence. Inspect the rendered DOM and the page or template source. If the approved headline already exists, mark it up as an H1; otherwise add it once and verify the final HTML.",
  }),
  canonical_missing: Object.freeze({
    owner: "This page does not clearly state which URL should be treated as its preferred version. Setting that preference helps prevent multiple addresses from competing as if they were different pages.",
    marketing: "The page is missing a preferred-URL signal. Keeping campaign, shared, and indexed versions aligned reduces the chance that visibility is split across alternate addresses.",
    seo: "No canonical URL was observed for this page. Add a self-referencing or otherwise intentionally selected canonical that points to the final indexable URL you want consolidated in search.",
    developer: "The document head is missing the canonical link signal. Emit a valid absolute canonical URL from the page/template using the final normalized URL and avoid pointing it through redirects or to a non-indexable target.",
  }),
  potential_orphan_pages: Object.freeze({
    owner: "These pages were found but appear difficult to reach by following links through the site. Decide which ones still matter, then make important pages easier for visitors to discover.",
    marketing: "Useful pages that sit outside normal navigation are less likely to receive internal traffic or support a customer journey. Confirm the pages are intentional before adding them to relevant hubs or journeys.",
    seo: "The crawl found pages with weak or missing internal-link discovery evidence. Review intent first, then add contextual or hub links to pages that should remain indexable rather than linking every detected URL indiscriminately.",
    developer: "Treat this as a discovery-graph issue, not proof that every listed page shares one template defect. For pages that should remain, add links from evidenced navigation, hub, or related-content surfaces and verify they become crawl-reachable.",
  }),
  internal_link_redirect: Object.freeze({
    owner: "Some links on your site send visitors through an unnecessary redirect before reaching the destination. Updating the links to point straight to the final page removes an avoidable extra step.",
    marketing: "Internal links are pointing at old addresses that redirect. Update recurring navigation and content links to the final destinations so journeys and campaign paths stay clean.",
    seo: "Internal links resolve through redirects instead of pointing directly to the final URL. Replace the source hrefs with their final destinations to reduce crawl hops and keep internal signals on the canonical URL.",
    developer: "Update the evidenced link sources to use the final destination URL directly. Prefer fixing shared navigation or template emitters where the repair surface proves they are responsible rather than adding another redirect rule.",
  }),
  failed_page: Object.freeze({
    owner: "FixList could not verify this page during the scan. Treat it as something to check again, not as proof that the page is permanently broken, until a repeat check confirms the failure.",
    marketing: "A page in the journey could not be verified during this scan. Before changing messaging or destinations, confirm the page is consistently unavailable and not just temporarily blocked or slow.",
    seo: "The page fetch was not successfully verified in this observation. Keep it in verification until repeated or structural evidence confirms a durable accessibility problem; one failed observation is not enough to call the URL broken.",
    developer: "The scanner recorded an unsuccessful page verification. Reproduce the request and inspect status, network, WAF/rate-limit, and origin behavior before treating it as a persistent defect or changing routing.",
  }),
  duplicate_title_template: Object.freeze({
    owner: "Several pages are using the same page title even though they represent different content. Making the titles distinct helps people and search engines tell the pages apart.",
    marketing: "A shared title pattern is making different pages look the same in search. Keep the brand pattern if useful, but include the page-specific product, place, topic, or offer that differentiates each result.",
    seo: "Multiple pages share a title through the detected title pattern. Make the template generate distinct, descriptive titles for each indexable page while preserving a consistent site convention.",
    developer: "The evidenced title template is collapsing different pages onto the same output. Add the correct page-specific field to the title generator and verify representative pages from the affected template family before rollout.",
  }),
});

function clean(value = "") {
  return typeof value === "string" ? value.trim() : "";
}

function hasOwn(source, key) {
  return Boolean(source && typeof source === "object" && Object.prototype.hasOwnProperty.call(source, key));
}

function consistentIdentifierOf(item = {}, topFields = [], originalFields = topFields) {
  let present = false;
  let selected = "";
  const sources = [
    [item, topFields],
    [item?.original, originalFields],
  ];

  for (const [source, fields] of sources) {
    if (!source || typeof source !== "object" || Array.isArray(source)) continue;
    for (const field of fields) {
      if (!hasOwn(source, field)) continue;
      present = true;
      const normalized = clean(source[field]).toLowerCase();
      if (!normalized) return { present: true, value: "" };
      if (selected && normalized !== selected) return { present: true, value: "" };
      selected = normalized;
    }
  }

  return { present, value: selected };
}

function ruleOf(item = {}) {
  const publishedRule = consistentIdentifierOf(item, ["rule", "rule_id", "ruleId"], ["rule", "rule_id"]);
  if (publishedRule.present) return publishedRule.value;
  return consistentIdentifierOf(item, ["issue_type"], ["issue_type"]).value;
}

/**
 * Return role-specific explanation copy without changing remediation or repair
 * evidence. Missing roles and unmapped rules fail to the existing generic
 * manual-review wording rather than guessing which audience/copy applies.
 */
export function repairRoleExplanation(item = {}, role = "") {
  const normalizedRole = clean(role).toLowerCase();
  const rule = ruleOf(item);
  const entry = Object.hasOwn(ROLE_EXPLANATIONS, rule) ? ROLE_EXPLANATIONS[rule] : null;
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
  const normalizedRule = clean(rule).toLowerCase();
  return Object.hasOwn(ROLE_EXPLANATIONS, normalizedRule) ? ROLE_EXPLANATIONS[normalizedRule] : null;
}
