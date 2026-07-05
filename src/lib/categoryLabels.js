const CATEGORY_DETAILS = {
  meta_title: {
    title: "Search titles",
    why: "clear page titles can help visitors understand what each page offers before they click.",
  },
  meta_description: {
    title: "Search descriptions",
    why: "strong descriptions can make search results more useful and persuasive.",
  },
  thin_content: {
    title: "Page content",
    why: "helpful page content gives visitors more reasons to trust and contact you.",
  },
  duplicate_content: {
    title: "Page clarity",
    why: "unique pages help visitors and search engines understand each page's purpose.",
  },
  canonical: {
    title: "Preferred-page settings",
    why: "clear preferred-page settings help search engines understand the main version of important pages.",
  },
  schema: {
    title: "Trust signals",
    why: "reviews, proof points, and structured trust signals can help people feel more confident.",
  },
  web_dev: {
    title: "Website setup",
    why: "small setup improvements can make the site easier for visitors and search engines to read.",
  },
  performance: {
    title: "Website speed",
    why: "faster pages usually create a better visitor experience.",
  },
  internal_link: {
    title: "Website links",
    why: "clear links help visitors and search engines find important pages.",
  },
  image_alt_text: {
    title: "Image descriptions",
    why: "better image descriptions can improve accessibility and give search engines more context.",
  },
};

export function getTopCategory(issues = []) {
  if (!issues.length) return null;

  const counts = new Map();

  for (const issue of issues) {
    const category = issue.category || "web_dev";
    counts.set(category, (counts.get(category) || 0) + 1);
  }

  const [topCategory] = Array.from(counts.entries()).sort((a, b) => b[1] - a[1])[0] || [];

  return CATEGORY_DETAILS[topCategory] || {
    title: "Website improvements",
    why: "these improvements can make your website clearer and more useful.",
  };
}