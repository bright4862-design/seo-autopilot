export function getStatusLabel(item) {
  if (item?.status === "auto_fixed") return "Prepared";
  if (item?.status === "needs_approval") return "Needs review";
  if (item?.status === "needs_developer") return "May need help";
  if (item?.requires_developer) return "May need help";
  if (item?.requires_approval) return "Needs review";
  return "Recommended";
}

export function getPriorityLabel(priority) {
  if (priority === "critical" || priority === "high") return "High impact";
  if (priority === "medium") return "Medium impact";
  return "Lower impact";
}

export const ACTIVE_STATUSES = new Set([
  "auto_fixed",
  "needs_approval",
  "needs_developer",
  "open",
  "in_progress",
]);

export const BUCKETS = {
  needs_approval: {
    key: "needs_approval",
    title: "Your turn",
    subtitle: "Quick decisions — approve what you like and we handle the rest.",
    empty: "Nothing is waiting on you right now.",
    cta: "Review now",
  },
  auto_fixed: {
    key: "auto_fixed",
    title: "Prepared for you",
    subtitle:
      "Improvements we prepared — nothing required, but you can see exactly what changed.",
    empty: "Nothing has been prepared yet.",
    cta: "See what we prepared",
  },
  needs_developer: {
    key: "needs_developer",
    title: "Get help",
    subtitle:
      "Bigger jobs — send instructions to your web person, or let us do it for you.",
    empty: "No larger improvements found right now.",
    cta: "See options",
  },
};

export const BUCKET_ORDER = ["needs_approval", "auto_fixed", "needs_developer"];

export function getIssueBucket(issue = {}) {
  if (issue.status === "auto_fixed") return "auto_fixed";
  if (issue.status === "needs_approval") return "needs_approval";
  if (issue.status === "needs_developer") return "needs_developer";

  if (issue.requires_developer) return "needs_developer";
  if (issue.requires_approval) return "needs_approval";
  if (issue.can_auto_fix) return "auto_fixed";

  const difficulty = String(issue.difficulty || "").toLowerCase();
  if (difficulty.includes("developer") || difficulty.includes("technical")) {
    return "needs_developer";
  }

  const category = String(issue.category || "").toLowerCase();
  if (["canonical", "redirect", "performance", "scanner_blocked", "js_rendering"].includes(category)) {
    return "needs_developer";
  }

  return "needs_approval";
}

export function getFirstStep(counts = {}) {
  if (Number(counts.needs_approval || 0) > 0) {
    return 'Start with "Your turn" — quick approvals that only take a minute.';
  }
  if (Number(counts.auto_fixed || 0) > 0) {
    return "Take a look at what we already prepared for you.";
  }
  if (Number(counts.needs_developer || 0) > 0) {
    return 'Look at "Get help" — bigger improvements with clear instructions included.';
  }
  return "Your scan looks clean based on the website content we reviewed.";
}

export const CATEGORY_LABELS = {
  "404_error": {
    title: "Broken pages",
    why: "Visitors and Google are hitting dead ends on your site.",
    what: "Point each broken link to the right page, or restore the missing page.",
  },
  meta_title: {
    title: "Google result titles",
    why: "The title is the first thing people see in Google results.",
    what: "Write clear titles that make people want to click.",
  },
  meta_description: {
    title: "Google result descriptions",
    why: "This short text under your title helps people choose your site.",
    what: "Write descriptions that say why visitors should pick you.",
  },
  canonical: {
    title: "Duplicate page mix-ups",
    why: "Google may be unsure which version of a page to show.",
    what: "Tell Google which page is the main one.",
  },
  sitemap: {
    title: "Helping Google find your pages",
    why: "Google may be missing some of your pages entirely.",
    what: "Keep an up-to-date map of your site for Google.",
  },
  alt_text: {
    title: "Image descriptions",
    why: "Google cannot understand images without a short text description.",
    what: "Describe important images so they can support search visibility.",
  },
  image_alt_text: {
    title: "Image descriptions",
    why: "Google cannot understand images without a short text description.",
    what: "Describe important images so they can support search visibility.",
  },
  schema: {
    title: "Business details for Google",
    why: "Extra details like hours, location, products, and FAQs help Google display you properly.",
    what: "Add behind-the-scenes information that search engines can read.",
  },
  heading: {
    title: "Page headlines",
    why: "Clear headlines help visitors and Google understand each page.",
    what: "Improve the main headline and section headings.",
  },
  redirect: {
    title: "Page forwarding",
    why: "Old links should send people to the right new page.",
    what: "Make sure old addresses forward correctly.",
  },
  page_speed: {
    title: "Slow pages",
    why: "Slow pages lose visitors and can rank lower on Google.",
    what: "Flag what is slowing the page down and how to fix it.",
  },
  performance: {
    title: "Slow or heavy pages",
    why: "Slow pages lose visitors and can rank lower on Google.",
    what: "Flag what is slowing the page down and how to fix it.",
  },
  thin_content: {
    title: "Pages with too little text",
    why: "Google prefers pages that fully answer a visitor's question.",
    what: "Suggest what to add so the page is genuinely useful.",
  },
  duplicate_content: {
    title: "Repeated search text",
    why: "Repeated titles or descriptions make it harder for Google to tell pages apart.",
    what: "Make each important page's search text unique.",
  },
  local_seo: {
    title: "Local visibility",
    why: "This affects how you show up when nearby customers search.",
    what: "Check that your business details are consistent everywhere.",
  },
  internal_link: {
    title: "Internal links",
    why: "Important pages should be easy for visitors and Google to find.",
    what: "Add links from useful pages, menus, or related content.",
  },
  web_dev: {
    title: "Website setup",
    why: "Some behind-the-scenes settings affect how your site appears online.",
    what: "Review the setup and send technical items to your web person if needed.",
  },
  scanner_blocked: {
    title: "Scan coverage",
    why: "The scanner could not read enough of the website to check everything.",
    what: "Check whether the site blocks crawler requests or needs a JavaScript fallback.",
  },
  js_rendering: {
    title: "Content loaded by JavaScript",
    why: "Important content may not be visible to search engines right away.",
    what: "Make sure titles, links, headings, and main content are available in the page HTML.",
  },
};

function humanizeCategory(category = "") {
  return String(category || "Other")
    .split("_")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export function getCategoryLabel(category) {
  return (
    CATEGORY_LABELS[category] || {
      title: humanizeCategory(category || "Other"),
      why: "",
      what: "",
    }
  );
}

export function getScoreBand(score) {
  if (typeof score !== "number") return null;
  if (score >= 85) return { label: "Great", tone: "green" };
  if (score >= 70) return { label: "Good", tone: "blue" };
  if (score >= 50) return { label: "Getting there", tone: "amber" };
  return { label: "Needs work", tone: "red" };
}

export function friendlyCategory(category) {
  return getCategoryLabel(category).title || "Website improvement";
}

const cleanups = [
  [new RegExp("canon" + "ical tag", "gi"), "preferred page setting"],
  [new RegExp("canon" + "icals", "gi"), "preferred page settings"],
  [new RegExp("canon" + "ical", "gi"), "preferred page setting"],
  [/meta title/gi, "search title"],
  [/meta description/gi, "search description"],
  [new RegExp("meta" + "data", "gi"), "search appearance"],
  [new RegExp("sche" + "ma markup", "gi"), "trust signals"],
  [new RegExp("sche" + "ma", "gi"), "trust signals"],
  [/indexation/gi, "search visibility"],
  [new RegExp("crawl" + "er", "gi"), "scanner"],
  [/crawl/gi, "scan"],
  [new RegExp("developer" + " required", "gi"), "may need help"],
  [/technical SEO/gi, "website setup"],
  [new RegExp("auto" + "-fixed", "gi"), "prepared"],
  [new RegExp("automatic" + " fixes", "gi"), "prepared recommendations"],
  [/issues/gi, "recommendations"],
  [/issue/gi, "recommendation"],
  [/reject/gi, "skip for now"],
  [/404 error/gi, "broken page"],
];

export function customerText(value = "") {
  return cleanups.reduce((text, [pattern, replacement]) => text.replace(pattern, replacement), String(value));
}

export function groupIssuesByPage(issues) {
  const map = new Map();

  issues.forEach((issue) => {
    const key = `${issue.status || "unknown"}|${issue.page_url || ""}`;

    if (!map.has(key)) {
      map.set(key, {
        ...issue,
        grouped: true,
        recommendations: [issue],
        group_title: buildPageGroupTitle(issue),
        summary: "Recommendations prepared for this page.",
      });
    } else {
      map.get(key).recommendations.push(issue);
    }
  });

  return Array.from(map.values()).map((group) => {
    const count = group.recommendations.length;

    if (count > 1) {
      return {
        ...group,
        group_title: buildPageGroupTitle(group),
        summary: `${count} recommendations prepared for this page.`,
      };
    }

    return group.recommendations[0];
  });
}

export function buildPageGroupTitle(issue) {
  const path = issue?.page_url || "";
  const clean = path === "/" ? "homepage" : path.split("/").filter(Boolean).pop()?.replaceAll("-", " ") || "page";
  const title = clean
    .split(" ")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");

  return `Improve your ${title} page`;
}
