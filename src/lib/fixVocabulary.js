function normalizedRule(item = {}) {
  return String(item.rule || item.original?.rule || "").trim().toLowerCase();
}

function normalizedCategory(item = {}) {
  return String(item.category || item.original?.category || "").trim().toLowerCase();
}

// "unknown" and "mixed" are classifier states, not page types. Naming one to a
// customer reads as a defect in the report rather than a fact about their site:
// "Add a search description to this unknown page" tells them nothing and sounds
// like the scan lost their URL. An uninformative classification falls back to
// the neutral wording the empty case already produces.
const UNINFORMATIVE_FAMILIES = new Set(["unknown", "mixed", "unclassified", "other", "none"]);

/** The family label as it reads inside a title. */
function titleFamily(label = "") {
  return label === "pages" ? "your pages" : label;
}

function familyLabel(item = {}) {
  const family = String(item.templateFamily || item.page_template_family || item.original?.page_template_family || "").trim().toLowerCase();
  if (UNINFORMATIVE_FAMILIES.has(family)) return "pages";
  const labels = {
    activity_detail: "activity pages",
    collection_page: "collection pages",
    homepage: "homepage",
    legal_info: "legal pages",
    // "standard pages" names the classifier's default bucket, not anything an
    // owner would call a page. The neutral word is the honest one.
    standard: "pages",
    // Without these the classifier's own key is shown with underscores
    // swapped for spaces -- "location landing pages", "guide article pages" --
    // which reads as internal vocabulary rather than the customer's.
    location_landing: "location pages",
    guide_article: "guide pages",
    product_detail: "product pages",
    category_listing: "category pages",
    booking_or_checkout: "checkout pages",
    route_boundary: "section pages",
    contact: "contact pages",
    qa: "FAQ pages",
    // "conversion pages" is marketing vocabulary. An owner knows these as the
    // pages where someone gets in touch or applies.
    conversion: "sign-up and contact pages",
    archive: "archive pages",
  };
  return labels[family] || (family ? `${family.replace(/_/g, " ")} pages` : "pages");
}

/**
 * The singular of a family label, for copy about one page.
 *
 * The word boundary matters: the bare fallback label is "pages" with no leading
 * space, so a " pages" pattern left it plural and produced "to this pages".
 */
function singularFamilyLabel(label = "") {
  return String(label).replace(/\bpages$/, "page");
}

/**
 * The template name inside a family label, or "" when there is none.
 *
 * The neutral fallback is the bare word "pages", which is not a template name.
 * Interpolating it produced "Fix the shared pages template once" -- a claim the
 * classifier never made. An empty result means the copy omits the phrase.
 */
function templateNameOf(label = "") {
  return String(label).replace(/\bpages$/, "").trim();
}

function affectedCount(item = {}) {
  const list = Array.isArray(item.affectedPages) ? item.affectedPages : Array.isArray(item.affected_pages) ? item.affected_pages : [];
  const reported = Number(item.pageCount ?? item.page_count ?? 0);
  return Math.max(list.length, Number.isFinite(reported) ? reported : 0);
}

const CATEGORY_LABELS = Object.freeze({
  indexability: "Search visibility",
  meta_description: "Search appearance",
  meta_title: "Search appearance",
  canonical: "Search visibility",
  thin_content: "Page content",
  internal_link: "Site navigation",
  sitemap: "Site discovery",
  schema: "Search appearance",
  performance: "Site experience",
  image_alt_text: "Images",
  alt_text: "Images",
  js_rendering: "Website setup",
});

export function customerPriorityLabel(priority = "") {
  const value = String(priority || "").toLowerCase();
  if (value === "critical") return "Fix first";
  if (value === "high") return "Fix next";
  if (value === "medium") return "Improve next";
  return "Worth checking";
}

export function customerHealthLabel(score, { unavailable = false, noHighConfidenceFindings = false } = {}) {
  if (unavailable) return "Score unavailable";
  if (noHighConfidenceFindings) return "Nothing urgent found";
  const value = Number(score);
  if (!Number.isFinite(value)) return "Website check";
  if (value >= 85) return "Looking good";
  if (value >= 70) return "Good foundation";
  if (value >= 50) return "Needs attention";
  return "Needs work";
}

export function customerScopeRelationshipLabel(value = "") {
  const relationship = String(value || "").trim();
  if (!relationship) return "";
  if (relationship === "sibling_sous_dossier") return "Related site section";
  return relationship
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^\w/, (char) => char.toUpperCase());
}
export function customerCategoryLabel(item = {}) {
  const rule = normalizedRule(item);
  if (rule === "potential_orphan_pages") return "Site navigation";
  if (rule === "redirect_chain") return "Page forwarding";
  if (rule.includes("canonical")) return "Search visibility";
  if (rule.includes("meta_description") || rule.includes("title")) return "Search appearance";
  if (rule.includes("h1")) return "Page content";
  return CATEGORY_LABELS[normalizedCategory(item)] || "Website improvement";
}

export function customerCopyForFix(item = {}) {
  const rule = normalizedRule(item);
  const count = affectedCount(item);
  const family = familyLabel(item);

  if (["missing_meta_description", "empty_meta_description", "malformed_meta_description", "meta_description_unusable"].includes(rule)) {
    const title = count > 1
      ? `Add search descriptions to ${titleFamily(family)}`
      : family === "homepage"
        ? "Add a search description to the homepage"
        : family !== "pages"
          ? `Add a search description to this ${singularFamilyLabel(family)}`
          : "Add a search description to this page";
    return {
      customerCategory: "Search appearance",
      title,
      explanation: count > 1
        ? `${count} pages in this group are missing a useful search description or outputting a blank one.`
        : "This page is missing a useful search description or outputs a blank one.",
      whyItMatters: "This is the short text that can appear below a page title in Google. If it is missing, Google may create its own version from the page.",
      recommendation: count > 1
        ? `Fix the shared ${templateNameOf(family) ? `${templateNameOf(family)} ` : ""}template once so each page creates its own clear search description.`
        : "Add a clear, page-specific search description that explains what the visitor can do on this page.",
      technicalLabel: "Meta description",
    };
  }

  if (rule === "redirect_chain") {
    const location = family === "homepage"
      ? "the homepage"
      : count > 1 && family !== "pages"
        ? family
        : count > 1
          ? "these pages"
          : "this page";
    const title = count > 1
      ? `Update redirects on ${location} to point directly to final URLs`
      : `Update ${location === "the homepage" ? "the homepage" : "this page's"} redirect to point directly to the final URL`;
    return {
      customerCategory: "Page forwarding",
      title,
      explanation: count > 1
        ? `${count} pages send visitors and search engines through extra addresses before reaching their final URLs.`
        : "This page sends visitors and search engines through more than one address before reaching the final URL.",
      whyItMatters: "Extra redirects add unnecessary steps and can slow down visitors and search engines reaching the right page.",
      recommendation: count > 1
        ? "Update each first redirect, internal link, or sitemap entry so it points directly to the final URL shown in the redirect evidence."
        : "Update the first redirect, internal link, or sitemap entry so it points directly to the final URL shown in the redirect evidence.",
      technicalLabel: "Redirect chain",
    };
  }

  if (rule === "internal_link_redirect") {
    const location = family === "homepage"
      ? "homepage"
      : count > 1 && family !== "pages"
        ? family
        : count > 1
          ? "affected pages"
          : "this page";
    return {
      customerCategory: "Site navigation",
      title: family === "homepage"
        ? "Update homepage links to use their final URLs"
        : count > 1
          ? `Update links on ${location} to use their final URLs`
          : "Update this page's links to use the final URLs",
      explanation: count > 1
        ? `${count} pages contain links that first go through a redirect instead of linking straight to the final URL.`
        : "This page contains a link that first goes through a redirect instead of linking straight to the final URL.",
      whyItMatters: "Direct internal links are simpler for visitors and search engines and avoid unnecessary redirect hops.",
      recommendation: "Replace each old internal link with the final destination URL shown in the redirect evidence.",
      technicalLabel: "Internal link redirect",
    };
  }

  if (rule === "sitemap_redirect") {
    return {
      customerCategory: "Site discovery",
      title: count > 1
        ? "Replace redirecting sitemap URLs with their final URLs"
        : "Replace the redirecting sitemap URL with its final URL",
      explanation: count > 1
        ? `${count} sitemap entries redirect instead of listing the final URLs directly.`
        : "This sitemap entry redirects instead of listing the final URL directly.",
      whyItMatters: "A sitemap should give search engines the preferred final URLs rather than make them follow redirects first.",
      recommendation: "Remove each redirecting sitemap entry and list only its final 200-status canonical URL.",
      technicalLabel: "Sitemap redirect",
    };
  }

  if (["duplicate_title_template", "duplicate_title_localized", "duplicate_title_query_variants", "duplicate_title"].includes(rule)) {
    return {
      customerCategory: "Search appearance",
      title: count > 1 && family !== "pages"
        ? `Give ${family} distinct page titles`
        : count > 1
          ? "Give these pages distinct page titles"
          : "Give this page a distinct title",
      explanation: count > 1
        ? `${count} pages use the same or nearly identical search title.`
        : "This page uses a search title that is repeated elsewhere.",
      whyItMatters: "Distinct titles help people and search engines tell similar pages apart before they click.",
      recommendation: count > 1
        ? `Update the shared ${templateNameOf(family) ? `${templateNameOf(family)} ` : ""}title pattern so each affected page describes its own topic or purpose.`
        : "Rewrite the page title so it clearly describes this page rather than repeating another page's title.",
      technicalLabel: "Repeated page title",
    };
  }

  if (rule === "title_over_pixel_limit" || rule.includes("long_title")) {
    return {
      customerCategory: "Search appearance",
      title: count > 1 ? "Shorten page titles that may be cut off in Google" : "Shorten a page title that may be cut off in Google",
      explanation: count > 1
        ? `${count} page titles are likely too wide to display fully in common search results.`
        : "This page title is likely too wide to display fully in common search results.",
      whyItMatters: "A shorter, clearer title is easier to scan and is less likely to be cut off before the important words appear.",
      recommendation: count > 1
        ? "Update the shared title pattern so each affected page keeps its main topic near the beginning and removes unnecessary wording."
        : "Shorten the title while keeping the page's main topic and intent clear.",
      technicalLabel: "Title width",
    };
  }

  if (rule === "missing_h1") {
    const title = count > 1
      ? `Add one clear main heading to ${titleFamily(family)}`
      : family === "homepage"
        ? "Add one clear main heading to the homepage"
        : family !== "pages"
          ? `Add one clear main heading to this ${singularFamilyLabel(family)}`
          : "Add one clear main heading to this page";
    return {
      customerCategory: "Page content",
      title,
      explanation: count > 1 ? `${count} pages do not have a clear main heading.` : "This page does not have a clear main heading.",
      whyItMatters: "A clear main heading helps visitors and search engines understand the page's main topic immediately.",
      recommendation: count > 1
        ? `Fix the shared ${templateNameOf(family) ? `${templateNameOf(family)} ` : ""}pattern so each affected page has one clear main heading.`
        : "Add one clear main heading that describes the page's main topic.",
      technicalLabel: "Missing H1",
    };
  }

  // Must precede the generic canonical branch below: rule.includes("canonical")
  // matches this rule too, and its copy told the customer to ADD a canonical URL
  // to pages that already have one. The defect is where the existing canonical
  // points, not that it is missing.
  if (rule === "canonical_target_noindex") {
    return {
      customerCategory: "Search visibility",
      title: "Point preferred-page settings at pages search engines can keep",
      explanation: "These pages name a preferred version that is blocked from search, so the version they point at cannot be indexed.",
      whyItMatters: "Naming a blocked page as the preferred one tells search engines to consolidate onto something they are not allowed to keep, so neither version earns credit.",
      recommendation: "Point each preferred-page setting at a page that is allowed in search, or remove the block from that page if it should appear.",
      technicalLabel: "Canonical URL",
    };
  }

  if (rule === "canonical_missing" || rule.includes("canonical")) {
    // "Canonical URL" is the correct technical name and it stays on the Check
    // line, where someone briefing a developer can find it. It has no business
    // in the headline: it is the loudest text on the card and the one line a
    // non-technical owner reads, and this card's own body already explains the
    // fix without the word.
    const title = count > 1 && family !== "pages"
      ? `Tell search engines which version of your ${family} to show`
      : count > 1
        ? "Tell search engines which version of these pages to show"
        : family === "homepage"
          ? "Tell search engines which version of your homepage to show"
          : "Tell search engines which version of this page to show";
    return {
      customerCategory: "Search visibility",
      title,
      explanation: count > 1
        ? `${count} pages do not clearly identify their preferred URL version.`
        : "This page does not clearly identify its preferred URL version.",
      whyItMatters: "When several URLs can show the same content, search engines need a clear signal about which version should get the credit.",
      recommendation: count > 1
        ? "Add the correct preferred-page setting to the shared template or affected pages."
        : "Add the correct preferred-page setting for this page.",
      technicalLabel: "Canonical URL",
    };
  }

  if (rule === "image_alt_text" || rule.includes("image_alt") || rule.includes("alt_text")) {
    const title = count > 1
      ? `Add image descriptions to ${titleFamily(family)}`
      : "Add descriptions to this page's images";
    return {
      customerCategory: "Images",
      title,
      explanation: "Images on these pages have no alt text, so screen readers and search engines have nothing to describe them with.",
      whyItMatters: "Alt text is how visitors using assistive technology understand an image, and it is the only thing search engines can read from it.",
      recommendation: count > 1
        ? "Add a short, specific description to each image, starting with the pages that matter most to visitors."
        : "Add a short, specific description to each image on this page.",
      technicalLabel: "Image alt text",
    };
  }

  if (rule === "redirect_destination_noindex") {
    return {
      customerCategory: "Page forwarding",
      title: "Fix redirects that lead to pages blocked from search",
      explanation: "These URLs redirect to a destination that tells search engines not to index it, so the redirect ends somewhere search engines will not keep.",
      whyItMatters: "A redirect into a blocked page throws away the value of the original URL: search engines follow it and then find nothing they are allowed to keep.",
      recommendation: "Point each redirect at a final page that is allowed in search, or remove the block from the destination if it should be indexed.",
      technicalLabel: "Redirect destination",
    };
  }

  if (rule === "redirect_destination_failed" || rule === "redirect_destination_blocked") {
    return {
      customerCategory: "Page forwarding",
      title: "Fix redirects that lead nowhere usable",
      explanation: "These URLs redirect to a destination that did not load successfully for the scanner.",
      whyItMatters: "Visitors and search engines following these links reach a dead end instead of the page you intended.",
      recommendation: "Point each redirect at a final page that returns successfully.",
      technicalLabel: "Redirect destination",
    };
  }

  if (rule === "potential_orphan_pages") {
    return {
      customerCategory: "Site navigation",
      title: count > 1 ? "Check whether these pages need more internal links" : "Check whether this page needs more internal links",
      explanation: count === 1
        ? "1 page was found in your sitemap but was not reached through links in the pages FixList checked."
        : `${count || "Some"} pages were found in your sitemap but were not reached through links in the pages FixList checked.`,
      whyItMatters: "Important pages should be easy for visitors and search engines to reach from the rest of your website.",
      recommendation: "Check these pages with a full internal-link crawl or Search Console, then add useful internal links to any important pages that are genuinely isolated.",
      technicalLabel: "Potential orphan pages",
    };
  }

  // The scanner writes its own customer-facing explanation for this rule, and
  // that text names which defect it actually found -- an unresolved placeholder,
  // another market's copy, or both. The browser cannot reconstruct that
  // distinction: `template_content_issue_types` is dropped before the fix
  // reaches it. So this branch supplies only what the scanner does not publish
  // -- the category, a readable technical label, and a title in customer
  // vocabulary -- and passes the specific findings through untouched.
  if (rule === "broken_location_template_content") {
    return {
      customerCategory: "Page content",
      title: count > 1
        ? "Fix the wrong or unfinished text on your location pages"
        : "Fix the wrong or unfinished text on this location page",
      explanation: item.explanation
        || item.plain_english_explanation
        || (count > 1
          ? `${count} location pages show text that was never filled in, or that names a different area than the page is for.`
          : "This location page shows text that was never filled in, or that names a different area than the page is for."),
      whyItMatters: item.whyItMatters
        || item.why_it_matters
        || "Visitors and search engines read this text to work out which area the page serves. Leftover placeholders or another area's name make the page look unfinished and blur which location it is for.",
      recommendation: item.recommendation
        || item.simple_next_step
        || item.recommended_value
        || "Fix the shared location template and the values it fills in, then check the example pages before publishing.",
      technicalLabel: "Location page template",
    };
  }

  return {
    customerCategory: customerCategoryLabel(item),
    title: item.title || item.issue_title || "Review this website improvement",
    explanation: item.explanation || item.plain_english_explanation || "FixList found something worth reviewing on this page.",
    whyItMatters: item.whyItMatters || item.why_it_matters || "Improving this can make the website clearer for visitors and search engines.",
    recommendation: item.recommendation || item.simple_next_step || item.recommended_value || "Review the affected page and make the recommended update.",
    technicalLabel: rule ? rule.replace(/_/g, " ") : "Technical detail",
  };
}

export function applyCustomerVocabulary(item = {}) {
  const copy = customerCopyForFix(item);
  return {
    ...item,
    customerCategory: copy.customerCategory,
    title: copy.title,
    explanation: copy.explanation,
    whyItMatters: copy.whyItMatters,
    recommendation: copy.recommendation,
    technicalLabel: copy.technicalLabel,
  };
}
