export const STATUS_BADGES = {
  auto_fixed: ["Prepared", "bg-slate-100 text-slate-600 border-slate-200"],
  needs_approval: ["Needs review", "bg-slate-100 text-slate-600 border-slate-200"],
  needs_developer: ["May need help", "bg-slate-100 text-slate-600 border-slate-200"],
};

export const IMPACT_BADGES = {
  critical: "bg-slate-100 text-slate-600 border-slate-200",
  high: "bg-slate-100 text-slate-600 border-slate-200",
  medium: "bg-slate-100 text-slate-600 border-slate-200",
  low: "bg-slate-100 text-slate-600 border-slate-200",
};

export const FIX_TYPE_LABELS = {
  meta_title: "search title",
  meta_description: "search description",
  thin_content: "page content",
  canonical: "preferred page setting",
  "404_error": "broken page",
  schema: "trust signals",
};

export function pageName(url) {
  if (!url || url === "/") return "homepage";
  const seg = url.split("?")[0].split("/").filter(Boolean).pop() || "page";
  return seg.replace(/[-_]/g, " ").replace(/\b\w/g, c => c.toUpperCase()) + " page";
}

export function fixTypeLabel(issue) {
  return FIX_TYPE_LABELS[issue.category] || (issue.customer_category || "improvement").toLowerCase();
}