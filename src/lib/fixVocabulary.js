function normalizedRule(item = {}) {
  return String(item.rule || item.original?.rule || "").trim().toLowerCase();
}

function normalizedCategory(item = {}) {
  return String(item.category || item.original?.category || "").trim().toLowerCase();
}

function familyLabel(item = {}) {
  const family = String(item.templateFamily || item.page_template_family || item.original?.page_template_family || "").trim().toLowerCase();
  const labels = {
    activity_detail: "activity pages",
    collection_page: "collection pages",
    homepage: "homepage",
    legal_info: "legal pages",
    standard: "standard pages",
  };
  return labels[family] || (family ? `${family.replace(/_/g, " ")} pages` : "pages");
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
      ? `Add search descriptions to ${family}`
      : family === "homepage"
        ? "Add a search description to the homepage"
        : family !== "pages"
          ? `Add a search description to this ${family.replace(/ pages$/, " page")}`
          : "Add a search description to this page";
    return {
      customerCategory: "Search appearance",
      title,
      explanation: count > 1
        ? `${count} pages in this group are missing a useful search description or outputting a blank one.`
        : "This page is missing a useful search description or outputs a blank one.",
      whyItMatters: "This is the short text that can appear below a page title in Google. If it is missing, Google may create its own version from the page.",
      recommendation: count > 1
        ? `Fix the shared ${family.replace(/ pages$/, "")} template once so each page creates its own clear search description.`
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
        ? `Update the shared ${family.replace(/ pages$/, "")} title pattern so each affected page describes its own topic or purpose.`
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
      ? `Add one clear main heading to ${family}`
      : family === "homepage"
        ? "Add one clear main heading to the homepage"
        : family !== "pages"
          ? `Add one clear main heading to this ${family.replace(/ pages$/, " page")}`
          : "Add one clear main heading to this page";
    return {
      customerCategory: "Page content",
      title,
      explanation: count > 1 ? `${count} pages do not have a clear main heading.` : "This page does not have a clear main heading.",
      whyItMatters: "A clear main heading helps visitors and search engines understand the page's main topic immediately.",
      recommendation: count > 1
        ? `Fix the shared ${family.replace(/ pages$/, "")} pattern so each affected page has one clear main heading.`
        : "Add one clear main heading that describes the page's main topic.",
      technicalLabel: "Missing H1",
    };
  }

  if (rule === "canonical_missing" || rule.includes("canonical")) {
    const title = count > 1 && family !== "pages"
      ? `Tell search engines which ${family} are the main versions`
      : count > 1
        ? "Tell search engines which versions of these pages are the main ones"
        : family === "homepage"
          ? "Tell search engines which homepage URL is the main one"
          : "Tell search engines which version of this page is the main one";
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

  if (rule === "potential_orphan_pages") {
    return {
      customerCategory: "Site navigation",
      title: count > 1 ? "Check whether these pages need more internal links" : "Check whether this page needs more internal links",
      explanation: `${count || "Some"} pages were found in your sitemap but were not reached through links in the pages FixList checked.`,
      whyItMatters: "Important pages should be easy for visitors and search engines to reach from the rest of your website.",
      recommendation: "Check these pages with a full internal-link crawl or Search Console, then add useful internal links to any important pages that are genuinely isolated.",
      technicalLabel: "Potential orphan pages",
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
