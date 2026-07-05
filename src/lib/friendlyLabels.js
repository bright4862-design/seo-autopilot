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

export function friendlyCategory(category) {
  const map = {
    meta_title: "Search title",
    meta_description: "Search description",
    canonical: "Preferred page setting",
    schema: "Trust signals",
    content: "Page content",
    thin_content: "Page content",
    "404_error": "Broken page",
    redirect: "Page redirect",
    competitor_gap: "Competitor gap",
    web_dev: "Website setup",
    performance: "Website speed",
    internal_link: "Website links",
    sitemap: "Website setup",
    robots_txt: "Website setup",
    js_rendering: "Website setup",
    duplicate_content: "Page content",
  };

  return map[category] || "Website improvement";
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