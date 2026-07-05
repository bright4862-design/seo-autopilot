import { base44 } from "@/api/base44Client";

const VALID_CATEGORIES = ["meta_title", "meta_description", "404_error", "redirect", "canonical", "sitemap", "robots_txt", "js_rendering", "internal_link", "thin_content", "duplicate_content", "schema", "performance", "web_dev"];
const VALID_STATUSES = ["auto_fixed", "needs_approval", "needs_developer"];

// AI review step: filters, groups, rewrites and prioritizes the raw scan fixes.
// Returns null when the AI review can't be used (caller falls back to raw fixes).
export async function reviewFixesWithAi({ project, crawledPages, rawFixes }) {
  let competitors = [];
  try {
    competitors = await base44.entities.Competitor.filter({ project_id: project.id });
  } catch (e) {}

  const res = await base44.functions.invoke("aiReviewScan", {
    business_name: project.business_name,
    business_type: project.business_type,
    city: project.city,
    website_url: project.website_url,
    crawled_pages: crawledPages.map(p => ({
      url: p.url, status: p.status_code || 0, title: p.title || "",
      meta_description: p.meta_description || "", word_count: p.word_count || 0,
    })),
    raw_fixes: rawFixes,
    competitor_results: competitors.map(c => ({
      name: c.name, website_url: c.website_url, service_pages: c.service_pages_count,
      title_quality: c.title_quality_score, description_coverage: c.meta_coverage_pct,
      content_depth: c.content_depth_score,
    })),
  });

  const ai = res.data || {};
  const cleaned = Array.isArray(ai.cleaned_fixes)
    ? ai.cleaned_fixes.filter(f => f && f.page_url && f.issue_title && VALID_CATEGORIES.includes(f.category) && VALID_STATUSES.includes(f.status))
    : [];
  if (!ai.success || cleaned.length === 0) return null;

  return {
    fixes: cleaned,
    topActions: Array.isArray(ai.top_recommended_actions) ? ai.top_recommended_actions : [],
  };
}

export function computeHealthScore(fixes) {
  let score = 100;
  for (const f of fixes) {
    if (f.priority === "critical" || f.priority === "high") score -= 8;
    else if (f.priority === "medium") score -= 5;
    else score -= 2;
  }
  return Math.max(score, 0);
}

export function summarizeFixes(fixes) {
  return {
    we_can_fix: fixes.filter(f => f.status === "auto_fixed").length,
    needs_approval: fixes.filter(f => f.status === "needs_approval").length,
    needs_developer: fixes.filter(f => f.requires_developer === true).length,
  };
}