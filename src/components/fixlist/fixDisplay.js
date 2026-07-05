export const STATUS_BADGES = {
  auto_fixed: ["Prepared", "bg-green-50 text-green-700 border-green-200"],
  needs_approval: ["Needs your approval", "bg-amber-50 text-amber-700 border-amber-200"],
  needs_developer: ["Needs a developer", "bg-purple-50 text-purple-700 border-purple-200"],
};

export const IMPACT_BADGES = {
  critical: "bg-red-50 text-red-700 border-red-200",
  high: "bg-red-50 text-red-600 border-red-200",
  medium: "bg-amber-50 text-amber-700 border-amber-200",
  low: "bg-gray-50 text-gray-600 border-gray-200",
};

export const FIX_TYPE_LABELS = {
  meta_title: "title",
  meta_description: "description",
  thin_content: "content",
  canonical: "duplicate page signal",
  "404_error": "broken page",
};

export function pageName(url) {
  if (!url || url === "/") return "homepage";
  const seg = (url.split("?")[0].split("/").filter(Boolean).pop() || "page");
  return seg.replace(/[-_]/g, " ").replace(/\b\w/g, c => c.toUpperCase()) + " page";
}

export function fixTypeLabel(issue) {
  return FIX_TYPE_LABELS[issue.category] || (issue.customer_category || "improvement").toLowerCase();
}