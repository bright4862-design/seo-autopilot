from pathlib import Path

SOURCE_PATH = Path("src/pages/CrawlStatus.jsx")
TEST_PATH = Path("tests/frontend/crawlStatusPipeline.test.mjs")


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one {label} match, found {count}.")
    return source.replace(old, new, 1)


source = SOURCE_PATH.read_text()

source = replace_once(
    source,
    'import { trackEvent } from "@/lib/analytics";\n',
    'import { trackEvent } from "@/lib/analytics";\nimport { selectFinalReviewFixes } from "@/lib/reviewContract";\n',
    "review contract import",
)
source = replace_once(
    source,
    'const SCAN_FUNCTION_NAME = "runRealScan";',
    'const SCAN_FUNCTION_NAME = "runAdvancedScan";',
    "scan function constant",
)
source = replace_once(
    source,
    '    indexable: !/noindex/i.test(page.robots_meta || ""),',
    '''    indexable:\n      typeof page.indexable === "boolean"\n        ? page.indexable\n        : !/noindex/i.test(page.robots_meta || ""),''',
    "page indexability storage",
)
source = replace_once(
    source,
    'function computeSimpleHealthScore(fixes, scanData = {}) {',
    '''function getAuthoritativeHealthScore(source = {}) {\n  const report = source.website_health_report || {};\n  const summary = source.scan_summary || {};\n  const candidates = [\n    source.health_score,\n    source.seo_score,\n    report.health_score,\n    report.score,\n    summary.health_score,\n    summary.score,\n  ];\n\n  for (const value of candidates) {\n    const number = Number(value);\n    if (Number.isFinite(number) && number >= 0 && number <= 100) {\n      return Math.round(number);\n    }\n  }\n\n  return null;\n}\n\nfunction computeSimpleHealthScore(fixes, scanData = {}) {''',
    "authoritative score helper",
)
source = replace_once(
    source,
    '''      let finalFixes = mappedSeoIssues;\n      let topActions = [];''',
    '''      let finalFixes = mappedSeoIssues;\n      let authoritativeHealthScore = getAuthoritativeHealthScore(scanData);\n      let topActions = [];''',
    "authoritative score state",
)
source = replace_once(
    source,
    '        scanMode === "deep" ? 90000 : 45000,',
    '        scanMode === "deep" ? 100000 : 70000,',
    "scanner request timeout",
)
source = replace_once(
    source,
    '''          base44.functions.invoke(AI_REVIEW_FUNCTION_NAME, {\n            business_name: activeProject.business_name,\n            business_type: activeProject.business_type,\n            city: activeProject.city,\n            website_url: activeProject.website_url,\n            crawled_pages: crawledPagesData,\n            raw_fixes: mappedSeoIssues,\n            competitor_results: competitorResultsForReview,\n            discovered_competitors: discoveredCompetitors,\n            scan_mode: scanMode,\n            crawl_warnings: scanData.crawl_warnings || [],\n          }),\n          30000,''',
    '''          base44.functions.invoke(AI_REVIEW_FUNCTION_NAME, {\n            scan: {\n              ...scanData,\n              business_name: activeProject.business_name,\n              business_type: activeProject.business_type,\n              city: activeProject.city,\n              website_url: activeProject.website_url,\n              project_id: activeProject.id,\n              crawl_job_id: job.id,\n              crawled_pages: crawledPagesData,\n              competitor_results: competitorResultsForReview,\n              discovered_competitors: discoveredCompetitors,\n              scan_mode: scanMode,\n              crawl_warnings: scanData.crawl_warnings || [],\n            },\n          }),\n          125000,''',
    "full scanner review payload",
)
source = replace_once(
    source,
    '''        if (aiData.success && aiFixes.length > 0) {\n          finalFixes = aiFixes.map(mapFindingToSeoIssue);\n          topActions = Array.isArray(aiData.top_recommended_actions)\n            ? aiData.top_recommended_actions\n            : [];\n          positiveFindings = Array.isArray(aiData.positive_findings)\n            ? aiData.positive_findings\n            : positiveFindings;\n          aiSummary =\n            typeof aiData.plain_english_summary === "string"\n              ? aiData.plain_english_summary\n              : "";\n        } else {\n          finalFixes = mappedSeoIssues;\n        }''',
    '''        if (aiData.success) {\n          finalFixes = selectFinalReviewFixes({\n            aiData,\n            aiFixes,\n            scannerFixes: findingsForMapping,\n            slimFix: mapFindingToSeoIssue,\n          });\n\n          const reviewScore = getAuthoritativeHealthScore(aiData);\n          if (reviewScore !== null) authoritativeHealthScore = reviewScore;\n\n          topActions = Array.isArray(aiData.top_recommended_actions)\n            ? aiData.top_recommended_actions\n            : [];\n          positiveFindings = Array.isArray(aiData.positive_findings)\n            ? aiData.positive_findings\n            : positiveFindings;\n          aiSummary =\n            typeof aiData.plain_english_summary === "string"\n              ? aiData.plain_english_summary\n              : "";\n        } else {\n          finalFixes = mappedSeoIssues;\n        }''',
    "authoritative review selection",
)
source = replace_once(
    source,
    '''\n      if (mappedSeoIssues.length > 0 && finalFixes.length === 0) {\n        finalFixes = mappedSeoIssues;\n      }\n''',
    "\n",
    "stale finding resurrection guard",
)
source = replace_once(
    source,
    '      const finalHealthScore = computeSimpleHealthScore(finalFixes, scanData);',
    '''      const finalHealthScore =\n        authoritativeHealthScore ??\n        computeSimpleHealthScore(finalFixes, scanData);''',
    "final health score selection",
)

SOURCE_PATH.write_text(source)

TEST_PATH.write_text(
    '''import assert from "node:assert/strict";\nimport { readFile } from "node:fs/promises";\nimport test from "node:test";\n\nconst source = await readFile(\n  new URL("../../src/pages/CrawlStatus.jsx", import.meta.url),\n  "utf8",\n);\n\ntest("dashboard invokes the frozen Python-first scanner", () => {\n  assert.match(source, /const SCAN_FUNCTION_NAME = "runAdvancedScan"/);\n  assert.doesNotMatch(source, /const SCAN_FUNCTION_NAME = "runRealScan"/);\n  assert.match(source, /scanMode === "deep" \? 100000 : 70000/);\n});\n\ntest("Python Review receives the complete scanner evidence contract", () => {\n  assert.match(source, /scan:\\s*{\\s*\\.\\.\\.scanData/);\n  assert.doesNotMatch(source, /raw_fixes:\\s*mappedSeoIssues/);\n  assert.match(source, /125000,\\s*"AI review"/);\n});\n\ntest("authoritative review results and scores are preserved", () => {\n  assert.match(source, /selectFinalReviewFixes\\s*\\(/);\n  assert.match(source, /authoritativeHealthScore \\?\\?\\s*computeSimpleHealthScore/);\n  assert.doesNotMatch(\n    source,\n    /mappedSeoIssues\\.length > 0 && finalFixes\\.length === 0/,\n  );\n});\n\ntest("stored crawl pages preserve scanner indexability", () => {\n  assert.match(source, /typeof page\\.indexable === "boolean"/);\n  assert.match(source, /\\? page\\.indexable/);\n});\n'''
)
