from pathlib import Path
import re


def sub1(text, pattern, replacement, label, flags=0):
    updated, count = re.subn(pattern, replacement, text, count=1, flags=flags)
    if count != 1:
        raise SystemExit(f"{label}: expected one match, found {count}")
    return updated


path = Path("src/components/scan/ScanWebsiteForm.jsx")
text = path.read_text(encoding="utf-8")

needle = '''  const finalFixes = groupAndSortFixes((aiFixes.length > 0 ? aiFixes : scannerFixes).map(slimFix), { requestedPathPrefix }).slice(0, 120);
  const healthScore = getFirstNumber([aiData?.health_score, aiData?.seo_score, aiData?.website_health_report?.health_score, aiData?.scan_summary?.health_score, scanData?.health_score, scanData?.seo_score, scanData?.scan_summary?.score, scanData?.scan_summary?.health_score]);
'''
replacement = needle + '''  const noHighConfidenceFindings = aiData?.no_high_confidence_findings === true || finalFixes.length === 0;
  const healthGrade = aiData?.website_health_report?.health_grade || aiData?.health_grade || (noHighConfidenceFindings ? "No issues found in sample" : scoreLabel(healthScore));
  const nextBestStep = aiData?.website_health_report?.next_best_step || aiData?.next_best_step || (noHighConfidenceFindings ? "No high-confidence issues were found in this scanned sample. Consider a deeper crawl or manually reviewing key money pages." : "");
  const reviewLimitations = firstArray([aiData?.website_health_report?.limitations]);
  const limitation = aiData?.limitation || reviewLimitations[reviewLimitations.length - 1] || "";
'''
if needle not in text:
    raise SystemExit("merge variables not found")
text = text.replace(needle, replacement, 1)

text = text.replace(
    '    cms_action_plan: aiData?.cms_action_plan || aiData?.cms_plan || aiData?.implementation_plan || buildCmsActionPlan(cmsPlatform, cmsName, finalFixes),\n',
    '    cms_action_plan: noHighConfidenceFindings ? "No high-confidence fixes were found in the scanned sample. Consider a deeper crawl or a manual review of important business pages." : (aiData?.cms_action_plan || aiData?.cms_plan || aiData?.implementation_plan || buildCmsActionPlan(cmsPlatform, cmsName, finalFixes)),\n',
    1,
)

metadata = '''    ai_review_backend: aiData?.ai_review_backend || "",
    python_review_fallback_used: Boolean(aiData?.python_review_fallback_used),
'''
metadata_new = metadata + '''    no_high_confidence_findings: noHighConfidenceFindings,
    review_confidence_state: aiData?.review_confidence_state || (noHighConfidenceFindings ? "no_high_confidence_findings" : ""),
    zero_fix_confidence_version: aiData?.zero_fix_confidence_version || "",
    scan_status: aiData?.scan_status || (noHighConfidenceFindings ? "complete_no_high_confidence_findings" : "complete"),
    next_best_step: nextBestStep,
    limitation,
    health_grade: healthGrade,
'''
if text.count(metadata) < 2:
    raise SystemExit("metadata anchors not found")
text = text.replace(metadata, metadata_new, 2)

storage = '''function normalizeScanRecordForStorage(record) {
  const fixes = getRecommendations(record).map(slimFix);
  const pages = getPages(record).map(slimPage);
  const healthScore = getHealthScore(record);
  const incomplete = ["incomplete_evidence", "blocked_or_incomplete"].includes(record?.scan_status);
  const noHighConfidenceFindings = record?.no_high_confidence_findings === true || (fixes.length === 0 && !incomplete);
  return {
    ...record,
    id: record?.id || `scan_${Date.now()}`,
    created_at: record?.created_at || new Date().toISOString(),
    website_url: record?.website_url || "",
    website_key: normalizeWebsiteKey(record?.website_url || ""),
    business_name: record?.business_name || "",
    cms_platform: record?.cms_platform || "custom",
    cms_name: record?.cms_name || "Custom / Not sure",
    scan_mode: record?.scan_mode || "quick",
    health_score: Number(healthScore || 0),
    seo_score: Number(healthScore || 0),
    health_grade: record?.health_grade || record?.website_health_report?.health_grade || (noHighConfidenceFindings ? "No issues found in sample" : scoreLabel(healthScore)),
    no_high_confidence_findings: noHighConfidenceFindings,
    review_confidence_state: record?.review_confidence_state || (noHighConfidenceFindings ? "no_high_confidence_findings" : ""),
    zero_fix_confidence_version: record?.zero_fix_confidence_version || "",
    scan_status: record?.scan_status || (noHighConfidenceFindings ? "complete_no_high_confidence_findings" : "complete"),
    next_best_step: record?.next_best_step || record?.website_health_report?.next_best_step || "",
    limitation: record?.limitation || "",
    pages_crawled: Number(record?.pages_crawled || pages.length || 0),
    pages_found: Number(record?.pages_found || pages.length || 0),
    customer_summary: record?.customer_summary || record?.simple_summary || "",
    simple_summary: record?.simple_summary || record?.customer_summary || "",
    recommendations: fixes,
    fixes,
    findings: fixes,
    top_recommended_actions: fixes.slice(0, 5).map(fixToAction).map(slimAction),
    crawled_pages: pages,
    pages,
    scanned_pages: pages,
  };
}'''
text = sub1(text, r'function normalizeScanRecordForStorage\(record\) \{.*?\n\}', storage, "storage normalizer", re.S)

slim_ai = '''function slimAiData(ai = {}) {
  if (!ai) return null;
  const recommendations = getRecommendations(ai);
  return {
    success: ai.success,
    ai_provider: ai.ai_provider || ai.provider || ai.debug?.provider || "",
    ai_review_backend: ai.ai_review_backend || "",
    python_review_fallback_used: Boolean(ai.python_review_fallback_used),
    review_polish_version: ai.review_polish_version || "",
    group_dedup_version: ai.group_dedup_version || "",
    scoring_model: ai.scoring_model || ai.site_fingerprint?.scoring_model || "",
    no_high_confidence_findings: ai.no_high_confidence_findings === true,
    review_confidence_state: ai.review_confidence_state || "",
    zero_fix_confidence_version: ai.zero_fix_confidence_version || "",
    scan_status: ai.scan_status || "",
    next_best_step: ai.next_best_step || ai.website_health_report?.next_best_step || "",
    limitation: ai.limitation || "",
    health_grade: ai.health_grade || ai.website_health_report?.health_grade || "",
    ai_review_warning: ai.ai_review_warning || "",
    health_score: ai.health_score || ai.seo_score || ai.website_health_report?.health_score || ai.website_health_report?.score || 0,
    customer_summary: ai.customer_summary || ai.plain_english_summary || ai.summary || ai.website_health_report?.overall_explanation || "",
    website_health_report: slimHealthReport(ai.website_health_report || {}),
    site_fingerprint: ai.site_fingerprint || ai.scan_summary?.site_fingerprint || {},
    archetype_playbook: ai.archetype_playbook || {},
    top_recommended_actions: recommendations.slice(0, 5).map(fixToAction).map(slimAction),
    recommendations_count: recommendations.length,
    recommendations_preview: recommendations.slice(0, 18).map(slimFix),
    ai_rewrites_applied: ai.ai_rewrites_applied || 0,
  };
}'''
text = sub1(text, r'function slimAiData\(ai = \{\}\) \{.*?\n\}', slim_ai, "slim AI", re.S)

text = text.replace(
    '  const count = Array.isArray(fixes) ? fixes.length : 0;\n  const intro = `This website is marked as ${cmsName}. Start with the highest-impact SEO fixes first, then handle the easier cleanup tasks.`;\n',
    '  const count = Array.isArray(fixes) ? fixes.length : 0;\n  if (count === 0) return "No high-confidence fixes were found in the scanned sample. Consider a deeper crawl or a manual review of important business pages.";\n  const intro = `This website is marked as ${cmsName}. Start with the highest-impact SEO fixes first, then handle the easier cleanup tasks.`;\n',
    1,
)

group_title = '''function getTemplateGroupTitle(fix = {}, family = "template") {
  const rule = String(fix.rule || "").toLowerCase();
  const label = String(family || "template").replace(/_/g, " ");
  if (/rate_limited|blocked|429/.test(rule)) return `Check ${label} pages blocked by rate limiting`;
  if (/broken_page|404|410|server_error|5\\d\\d/.test(rule)) return fix.title || fix.issue_title || defaultTitle(fix.category);
  const value = `${fix.rule || ""} ${fix.category || ""} ${fix.title || ""}`.toLowerCase();
  if (value.includes("client") || value.includes("javascript") || value.includes("render")) return `Fix crawlable HTML for ${label} pages`;
  if (value.includes("route") || value.includes("index")) return `Review route-boundary indexing for ${label} pages`;
  if (value.includes("schema")) return `Add structured data to ${label} templates`;
  if (value.includes("h1")) return `Fix missing H1 headings on ${label} templates`;
  if (value.includes("alt")) return `Batch image descriptions on ${label} pages`;
  if (value.includes("description")) return `Batch meta descriptions on ${label} pages`;
  return `Fix repeated ${label} template issue`;
}'''
text = sub1(text, r'function getTemplateGroupTitle\(fix = \{\}, family = "template"\) \{.*?\}', group_title, "group title", re.S)

summary_line = '    customer_summary: clampText(record.customer_summary || record.simple_summary || record.scan_summary?.plain_english_summary || "", 1200),\n'
extra = summary_line + '''    no_high_confidence_findings: record.no_high_confidence_findings === true,
    review_confidence_state: record.review_confidence_state || "",
    zero_fix_confidence_version: record.zero_fix_confidence_version || "",
    scan_status: record.scan_status || "",
    next_best_step: record.next_best_step || record.website_health_report?.next_best_step || "",
    limitation: record.limitation || "",
    health_grade: record.health_grade || record.website_health_report?.health_grade || "",
'''
if summary_line not in text:
    raise SystemExit("compressed summary anchor not found")
text = text.replace(summary_line, extra, 1)
path.write_text(text, encoding="utf-8")
