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
    return {
      customerCategory: "Search appearance",
      title: `Add search descriptions to ${family}`,
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
    return {
      customerCategory: "Page forwarding",
      title: "Remove extra redirects",
      explanation: "This page sends visitors and search engines through more than one address before reaching the final page.",
      whyItMatters: "Extra redirects add unnecessary steps and can slow down visitors and search engines reaching the right page.",
      recommendation: "Point the first redirect, internal links, and sitemap entries directly to the final destination.",
      technicalLabel: "Redirect chain",
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
    return {
      customerCategory: "Page content",
      title: count > 1 ? "Add a clear main heading to these pages" : "Add a clear main heading",
      explanation: count > 1 ? `${count} pages do not have a clear main heading.` : "This page does not have a clear main heading.",
      whyItMatters: "A clear main heading helps visitors and search engines understand the page's main topic immediately.",
      recommendation: count > 1
        ? "Fix the shared page pattern so each affected page has one clear main heading."
        : "Add one clear main heading that describes the page's main topic.",
      technicalLabel: "Missing H1",
    };
  }

  if (rule === "canonical_missing" || rule.includes("canonical")) {
    return {
      customerCategory: "Search visibility",
      title: count > 1 ? "Tell search engines which page versions are the main ones" : "Tell search engines which page version is the main one",
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
      title: "Check pages that may be hard to find",
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
