# SEO Autopilot — Global Functions & Architecture Report

Generated: 2026-07-05

This coded documentation file reports on the app’s global backend functions, frontend architecture, scan pipeline, entity model, operational constraints, and recommended next architecture improvements.

---

## 1. Product mission

SEO Autopilot is an AI-powered SEO assistant for small business owners. It scans a business website, extracts SEO and content signals, prepares plain-English recommendations, compares competitors, and gives customers a Fix List, Scan Report, Website Improvements view, Competitor Gaps view, and service lead-capture path.

The app should feel like a guided SEO assistant, not a raw crawler dashboard. Customer-facing language should stay simple: use “search title” instead of “meta title”, “search description” instead of “meta description”, and “preferred-page settings” instead of “canonical” unless a developer-facing technical detail is needed.

---

## 2. High-level system architecture

```text
User enters website details
  -> Scan Website frontend flow
  -> CrawlJob created / scan progress displayed
  -> runAdvancedScan backend function
  -> HTML crawl + deterministic issue detection
  -> grouped_findings returned
  -> frontend maps grouped_findings into SeoIssue-ready records
  -> aiReviewScan rewrites, groups, and prioritizes recommendations
  -> final customer-safe SeoIssue records are saved
  -> CrawledPage records are saved
  -> CrawlJob and BusinessProject are updated
  -> scanCompetitors runs if competitor URLs exist
  -> customer sees Fix List / Reports / Competitor Gaps / Website Improvements
```

Canonical intelligence pipeline:

```text
Crawler -> Deterministic Rules -> AI Strategist -> Customer UI
```

Critical rule:

```text
Do not show raw_findings directly to customers. Customers should only see AI-reviewed fixes or safe grouped findings.
```

---

## 3. Frontend route architecture

Router file: `src/App.jsx`

```text
/                 Landing
/login            Login
/register         Register
/forgot-password  ForgotPassword
/reset-password   ResetPassword
/onboarding       Onboarding
/dashboard        FixList
/crawl-status     CrawlStatus / Scan Website
/issues           Issues
/metadata         Metadata
/redirects        Redirects
/canonicals       Canonicals
/js-rendering     JsRendering
/competitors      Competitor Gaps
/developer        Website Improvements
/reports          Scan Report
/assistant        Assistant
/billing          Billing
/admin            Admin
```

Protected routes are nested under `ProtectedRoute`, and dashboard pages render inside `DashboardLayout`.

Main customer navigation:

```text
Fix List
Scan Website
Competitor Gaps
Website Improvements
Scan Report
Billing
```

---

## 4. Backend function inventory

Current backend functions:

```text
aiReviewScan
runAdvancedScan
runRealScan
scanCompetitors
startCrawl
getCrawlStatus
generateReport
```

Primary active scan path:

```text
runAdvancedScan -> frontend grouped finding mapper -> aiReviewScan -> SeoIssue records
```

Legacy scan path:

```text
runRealScan -> fixes -> aiReviewScan -> SeoIssue records
```

`runRealScan` remains in the codebase but is no longer the primary Scan Website frontend call.

---

# 5. Function: runAdvancedScan

Path: `base44/functions/runAdvancedScan/entry.ts`

Purpose: current advanced HTML crawler and deterministic SEO analyzer. It crawls accessible HTML pages, extracts structured signals, detects issues, groups repeated findings, calculates a health score, and returns a rich scan result.

Authentication pattern:

```js
const base44 = createClientFromRequest(req);
const user = await base44.auth.me();
if (!user) return Response.json({ success: false, error: "Unauthorized" }, { status: 401 });
```

Input contract:

```json
{
  "website_url": "https://example.com",
  "business_name": "Example Business",
  "business_type": "Dentist",
  "city": "Austin",
  "project_id": "project id",
  "crawl_job_id": "crawl job id",
  "competitors": []
}
```

Important constants:

```js
const MAX_PAGES = 50;
const MAX_LINKS_PER_PAGE = 120;
const BATCH_SIZE = 6;
const FETCH_TIMEOUT_MS = 12000;
const USER_AGENT = "SEO-Autopilot/1.0";
```

Output contract:

```json
{
  "success": true,
  "website_url": "https://example.com",
  "normalized_url": "https://example.com/",
  "domain": "example.com",
  "pages_crawled": 42,
  "pages_found": 61,
  "health_score": 82,
  "crawled_pages": [],
  "raw_findings": [],
  "grouped_findings": [],
  "broken_links": [],
  "site_summary": {
    "positives": [],
    "total_findings": 0,
    "important_pages_found": 0,
    "pages_with_faq": 0,
    "pages_with_trust_signals": 0,
    "pages_with_calls_to_action": 0,
    "competitors_provided": 0,
    "html_only_scan": true,
    "javascript_rendering_used": false
  },
  "crawl_warnings": []
}
```

Crawl behavior:

```text
- Starts from the normalized URL.
- Performs breadth-first crawling.
- Fetches pages in small batches.
- Follows internal links only.
- Skips assets such as images, PDFs, CSS, JS, fonts, videos, and archives.
- Avoids low-value utility paths.
- Stops at MAX_PAGES.
```

Utility paths normally excluded from SEO recommendations:

```text
/cart, /checkout, /login, /signin, /signup, /register, /account, /search, /privacy, /terms, /thank-you, /thankyou, /payment, /admin, /wp-admin, /reset, /forgot, /cookie, /legal, /disclaimer, /tag/, /category/, /author/
```

Important page patterns:

```text
/, service, services, product, products, loan, loans, program, programs, pricing, packages, about, location, locations, area, areas, contact, book, appointment, consultation, repair, installation, menu, treatment, treatments
```

Page signals extracted:

```json
{
  "url": "",
  "original_url": "",
  "final_url": "",
  "status_code": 200,
  "content_type": "text/html",
  "redirected": false,
  "title": "",
  "meta_description": "",
  "h1": "",
  "h2s": [],
  "h3s": [],
  "canonical_url": "",
  "robots_meta": "",
  "word_count": 0,
  "visible_text_sample": "",
  "internal_links": [],
  "external_links": [],
  "images": [],
  "has_faq": false,
  "faq_questions": [],
  "has_schema": false,
  "schema_types": [],
  "has_phone": false,
  "has_email": false,
  "cta_phrases": [],
  "trust_signals": [],
  "placeholder_text": [],
  "is_utility_page": false,
  "is_important_page": true,
  "fetch_error": ""
}
```

Raw finding categories emitted by `runAdvancedScan`:

```text
broken_page, meta_title, meta_description, page_heading, canonical, thin_content, placeholder_text, faq_gap, cta_gap, trust_signal_gap, duplicate_search_titles
```

Because `SeoIssue.category` has a fixed enum, the frontend maps advanced categories into supported categories:

```js
const CATEGORY_MAP = {
  broken_page: "404_error",
  page_heading: "thin_content",
  placeholder_text: "web_dev",
  faq_gap: "thin_content",
  cta_gap: "thin_content",
  trust_signal_gap: "schema",
  duplicate_search_titles: "duplicate_content",
};
```

Deterministic findings generated:

```text
- Broken or unreachable pages.
- Missing search titles.
- Weak search titles.
- Missing search descriptions on important pages.
- Poor-length search descriptions.
- Missing main page heading.
- Missing preferred-page settings on important pages.
- Thin content on important pages.
- Placeholder-like text such as gvar, undefined, null, NaN, [object Object], {{ }}, lorem ipsum, or placeholder.
- Missing FAQ/customer questions.
- Missing clear call to action.
- Missing trust signals.
- Duplicate search titles.
```

Grouping behavior:

```json
{
  "type": "site_level",
  "category": "canonical",
  "customer_category": "Website setup",
  "status": "needs_developer",
  "priority": "medium",
  "difficulty": "developer",
  "issue_title": "Review preferred-page settings across important pages",
  "affected_pages": ["/page-one", "/page-two"]
}
```

Health score logic:

```text
Start at 100.
High / critical finding: -8
Medium finding: -5
Low finding: -2
Clamp between 0 and 100.
```

---

# 6. Function: aiReviewScan

Path: `base44/functions/aiReviewScan/entry.ts`

Purpose: AI strategist layer that receives deterministic scan findings and turns them into a shorter, customer-ready action plan.

Input contract:

```json
{
  "business_name": "",
  "business_type": "",
  "city": "",
  "website_url": "",
  "crawled_pages": [],
  "raw_fixes": [],
  "competitor_results": []
}
```

Output contract:

```json
{
  "success": true,
  "plain_english_summary": "",
  "top_recommended_actions": [
    { "title": "", "reason": "", "priority": "high" }
  ],
  "cleaned_fixes": [],
  "grouped_page_recommendations": [],
  "ignored_low_value_pages": [],
  "positive_findings": []
}
```

AI review responsibilities:

```text
- Filter low-value utility pages.
- Deduplicate repeated fixes.
- Group related page-level items.
- Rewrite raw findings into plain English.
- Avoid technical jargon.
- Start with strengths before cleanup items.
- Avoid promising ranking improvements.
- Avoid saying fixes were published or completed.
- Use “prepared”, “recommended”, “review”, and “may help”.
```

Important prompt guardrails:

```text
Do not overwhelm the user.
Do not show duplicate issues.
Ignore low-value utility pages unless broken.
Prioritize homepage, service pages, product pages, location pages, about page, and conversion pages.
Do not say anything was fixed or published.
Do not promise rankings.
Merge related issues for the same page into one grouped recommendation.
Make the output feel like a smart assistant reviewed the site, not a raw crawler report.
Be balanced: start with what the site already does well.
```

Special AI handling:

```text
Preferred-page settings: if raw fixes include duplicate-page / canonical findings, keep them merged as one fix titled “Review preferred-page settings across important pages”.
Placeholder-like content: if placeholder text is flagged, keep it as one high-priority developer fix titled “Important numbers may not be showing correctly to search engines”.
Search descriptions: for homepage and service pages, write descriptions specific to the business and page.
```

---

# 7. Function: runRealScan

Path: `base44/functions/runRealScan/entry.ts`

Purpose: older HTML scanner retained as a legacy scanner/reference implementation. The active Scan Website frontend flow now calls `runAdvancedScan` first.

Legacy capabilities:

```text
- Crawls up to 25 pages.
- Extracts title, description, H1, canonical, word count, placeholder hits, and links.
- Generates deterministic issues.
- Groups placeholder text and preferred-page settings.
- Returns fixes, crawled_pages, summary, health_score, pages_crawled, and issues_found.
```

Legacy output:

```json
{
  "business_name": "",
  "website_url": "",
  "health_score": 0,
  "pages_crawled": 0,
  "issues_found": 0,
  "crawled_pages": [],
  "fixes": [],
  "summary": {
    "we_can_fix": 0,
    "needs_approval": 0,
    "needs_developer": 0
  }
}
```

Current status:

```text
Deprecated in the primary frontend flow. Kept as fallback/reference scanner.
```

---

# 8. Function: scanCompetitors

Path: `base44/functions/scanCompetitors/entry.ts`

Purpose: crawls saved competitor websites, computes benchmark metrics, updates `Competitor` records, and creates `CompetitorInsight` records when competitors outperform the customer.

Input contract:

```json
{
  "project_id": "",
  "business_type": "",
  "city": "",
  "customer_pages": []
}
```

Competitor metrics:

```json
{
  "pages_crawled": 0,
  "service_pages_count": 0,
  "title_quality_score": 0,
  "meta_coverage_pct": 0,
  "content_depth_score": 0,
  "faq_usage": false,
  "schema_usage": false,
  "broken_links_count": 0
}
```

Insight triggers:

```text
Competitors have more dedicated service pages
Competitors use clearer search titles
Competitors have better search descriptions
Competitors may answer more customer questions
Your site has more broken pages
```

Output contract:

```json
{
  "customer": {},
  "competitors": [],
  "insights": []
}
```

Operational behavior:

```text
- Reads Competitor records for the project.
- Crawls each competitor sequentially.
- Updates competitor metric fields.
- Deletes previous CompetitorInsight records for the project.
- Creates fresh insights.
```

---

# 9. Function: startCrawl

Path: `base44/functions/startCrawl/entry.ts`

Purpose: creates a queued `CrawlJob` record.

Input contract:

```json
{ "projectId": "" }
```

Output contract:

```json
{
  "success": true,
  "crawl_job_id": "",
  "message": "Crawl job created and queued. In production, this triggers the external crawler API."
}
```

Current role: lightweight job creator. The main Scan Website frontend currently orchestrates scan work directly.

---

# 10. Function: getCrawlStatus

Path: `base44/functions/getCrawlStatus/entry.ts`

Purpose: fetches a single `CrawlJob` by ID.

Input contract:

```json
{ "crawlJobId": "" }
```

Output contract:

```json
{ "success": true, "crawlJob": {} }
```

---

# 11. Function: generateReport

Path: `base44/functions/generateReport/entry.ts`

Purpose: creates a saved `Report` record from current project and issue data.

Input contract:

```json
{ "projectId": "" }
```

Process:

```text
Load BusinessProject -> load SeoIssue records -> count prepared/review/developer items -> create Report -> return Report
```

Report summary template:

```text
SEO scan of {website_url} found {issues.length} total issues. {fixed} simple fixes were prepared for review, {approval} need review, and {developer} require developer work.
```

---

# 12. Entity architecture

## BusinessProject

Stores one website/business profile.

```json
{
  "business_name": "",
  "website_url": "",
  "business_type": "",
  "city": "",
  "service_area": "",
  "main_services": "",
  "cms_platform": "Unknown",
  "status": "active",
  "seo_score": 0,
  "last_crawl_at": "",
  "next_crawl_at": "",
  "subscription_plan": "free",
  "owner_user_id": ""
}
```

Relationships:

```text
BusinessProject.id -> CrawlJob.project_id
BusinessProject.id -> SeoIssue.project_id
BusinessProject.id -> CrawledPage.project_id
BusinessProject.id -> DeveloperRecommendation.project_id
BusinessProject.id -> Competitor.project_id
BusinessProject.id -> Report.project_id
BusinessProject.id -> LeadRequest.project_id
```

## CrawlJob

Tracks scan lifecycle and metrics.

```json
{
  "project_id": "",
  "status": "queued",
  "crawl_type": "full",
  "pages_found": 0,
  "pages_crawled": 0,
  "js_pages_rendered": 0,
  "started_at": "",
  "completed_at": "",
  "error_message": "",
  "seo_score": 0,
  "issues_found": 0,
  "owner_user_id": ""
}
```

Statuses:

```text
queued, crawling_html, rendering_js, checking_metadata, checking_canonicals, checking_sitemap, checking_redirects, benchmarking_competitors, generating_recommendations, complete, failed
```

## CrawledPage

Stores page-level crawl output.

```json
{
  "project_id": "",
  "crawl_job_id": "",
  "url": "",
  "status_code": 200,
  "title": "",
  "meta_description": "",
  "h1": "",
  "canonical_url": "",
  "word_count": 0,
  "indexable": true,
  "in_sitemap": false,
  "rendered_title": "",
  "rendered_meta_description": "",
  "rendered_canonical": "",
  "js_difference_detected": false,
  "owner_user_id": ""
}
```

## SeoIssue

Stores final customer-visible recommendations.

```json
{
  "project_id": "",
  "crawl_job_id": "",
  "page_url": "",
  "category": "meta_title",
  "customer_category": "Search title",
  "priority": "medium",
  "status": "open",
  "difficulty": "easy",
  "issue_title": "",
  "plain_english_explanation": "",
  "why_it_matters": "",
  "current_value": "",
  "recommended_value": "",
  "ai_recommendation": "",
  "confidence_score": 90,
  "can_auto_fix": false,
  "requires_approval": false,
  "requires_developer": false,
  "owner_user_id": ""
}
```

Supported categories:

```text
meta_title, meta_description, 404_error, redirect, canonical, sitemap, robots_txt, js_rendering, internal_link, thin_content, duplicate_content, schema, performance, web_dev
```

Supported statuses:

```text
open, auto_fixed, needs_approval, approved, rejected, needs_developer, in_progress, completed
```

## DeveloperRecommendation

Stores implementation-oriented recommendations.

```text
Categories: quick_fix, cms_seo_setup, technical_seo, website_structure, content_pages, speed_mobile, rebuild_migration
Packages: diy, 500_cleanup, custom_rebuild
```

## Competitor

Stores competitor URLs and benchmark metrics.

```json
{
  "service_pages_count": 0,
  "title_quality_score": 0,
  "meta_coverage_pct": 0,
  "content_depth_score": 0,
  "faq_usage": false,
  "schema_usage": false,
  "broken_links_count": 0
}
```

## CompetitorInsight

Stores plain-English competitor gaps.

```json
{
  "insight_title": "",
  "explanation": "",
  "recommended_action": "",
  "impact": "medium"
}
```

## Report

Stores generated SEO scan reports.

```json
{
  "project_id": "",
  "crawl_job_id": "",
  "summary": "",
  "fixed_count": 0,
  "approval_count": 0,
  "developer_count": 0,
  "competitor_summary": "",
  "next_steps": "",
  "seo_score": 0,
  "owner_user_id": ""
}
```

## LeadRequest

Stores service requests, cleanup inquiries, rebuild inquiries, and waitlist leads.

```json
{
  "project_id": "",
  "name": "",
  "email": "",
  "business_name": "",
  "website_url": "",
  "request_type": "cleanup",
  "selected_plan": "",
  "message": "",
  "scan_summary": {},
  "selected_help_options": [],
  "status": "new"
}
```

## AnalyticsEvent

Stores internal-only product analytics.

```json
{
  "owner_user_id": "",
  "project_id": "",
  "event_name": "",
  "event_category": "scan",
  "page": "",
  "metadata": {},
  "created_at": ""
}
```

Analytics categories:

```text
auth, onboarding, scan, recommendation, competitor, report, help, billing, assistant
```

---

# 13. Frontend scan orchestration

Main page: `src/pages/CrawlStatus.jsx`

`handleScan(form)`:

```text
create/update BusinessProject -> delete/recreate Competitor records -> simulateScan(null, project)
```

`simulateScan`:

```text
1. Track scan_started.
2. Create CrawlJob if needed.
3. Delete existing SeoIssue records for the project.
4. Step through progress labels.
5. Mark CrawlJob complete for UI progress.
6. Call runAdvancedScan.
7. Map grouped_findings to SeoIssue-shaped records.
8. Pass mapped findings into aiReviewScan.
9. Use AI-reviewed fixes if available, otherwise grouped mapped findings.
10. Save CrawledPage records.
11. Run scanCompetitors if scan succeeded.
12. Save SeoIssue records.
13. Rebuild DeveloperRecommendation records from developer fixes.
14. Update CrawlJob counts, score, and error state.
15. Update BusinessProject last_crawl_at and seo_score.
16. Track scan_completed.
```

Finding normalization requires these fields:

```js
{
  project_id,
  crawl_job_id,
  owner_user_id,
  page_url,
  category,
  customer_category,
  priority,
  status,
  difficulty,
  issue_title,
  plain_english_explanation,
  why_it_matters,
  current_value,
  recommended_value,
  ai_recommendation,
  confidence_score,
  can_auto_fix,
  requires_approval,
  requires_developer
}
```

Affected pages handling:

```text
The current SeoIssue schema does not include metadata/details. If grouped_findings include affected_pages, the frontend appends those pages into ai_recommendation.
```

---

# 14. Customer-facing page responsibilities

```text
FixList.jsx: displays saved SeoIssue records grouped into Prepared, Needs review, and May need help.
CrawlStatus.jsx: collects website/project/competitor input and runs scans.
Competitors.jsx: shows competitor benchmark insights and comparison table.
Developer.jsx: shows implementation-oriented recommendations from developer-required fixes.
Reports.jsx: generates and displays saved SEO reports and PDF exports.
Billing.jsx: displays pricing and opens lead request modals.
Admin.jsx: admin-only analytics and lead review.
Assistant.jsx: SEO assistant conversation interface.
```

---

# 15. Analytics architecture

Internal analytics lives in:

```text
base44/entities/AnalyticsEvent.jsonc
src/lib/analytics.js
```

Example tracked events:

```text
scan_page_viewed
scan_started
scan_completed
scan_failed
fix_list_viewed
keyword_gap_analysis_started
keyword_gap_analysis_completed
request_help_clicked
```

Analytics is internal-only and does not rely on cookies or third-party analytics.

---

# 16. Observed current data status

Recent global data snapshot:

```json
{
  "BusinessProject": 4,
  "CrawlJob": 8,
  "SeoIssue": 10,
  "CrawledPage": 89,
  "DeveloperRecommendation": 8,
  "MetadataRecommendation": 2,
  "RedirectRecommendation": 4,
  "Competitor": 4,
  "CompetitorInsight": 0,
  "KeywordGapAnalysis": 0,
  "Report": 5,
  "LeadRequest": 0,
  "AnalyticsEvent": 11
}
```

Latest observed project:

```json
{
  "business_name": "Center street lending",
  "website_url": "https://www.centerstreetlending.com/",
  "status": "active",
  "seo_score": 80,
  "subscription_plan": "free"
}
```

Observed current project note:

```text
The project had crawled page records, but the latest crawl job had no saved score or issue count at the time of reporting. The current project had no saved SeoIssue records at the time of reporting.
```

---

# 17. Known constraints

HTML-only scanning:

```text
The crawler fetches server-returned HTML. It does not render JavaScript.
```

No real website editing:

```text
The app prepares recommendations. It does not currently publish changes into WordPress, Shopify, Wix, Webflow, or other CMS platforms.
```

No Search Console integration:

```text
Google Search Console is not connected. Current scans use crawl-accessible website data only.
```

Payments not connected:

```text
Billing UI exists, but payment checkout is not connected. Stripe is the available provider for the current workspace region.
```

---

# 18. Security model

Backend functions use request-scoped Base44 auth:

```js
const base44 = createClientFromRequest(req);
const user = await base44.auth.me();
```

Most functions require a logged-in user and return `401 Unauthorized` otherwise.

Entity access is primarily scoped by:

```text
owner_user_id == current user id
created_by_id == current user id
admin role
```

Admin-only areas include analytics read/update/delete and admin dashboards.

---

# 19. Recommended next architecture improvements

## 19.1 Add metadata/details support to SeoIssue

Problem:

```text
Grouped findings can include affected_pages, but SeoIssue has no metadata/details field.
```

Recommended schema addition:

```json
{
  "details": {
    "type": "object",
    "additionalProperties": true
  },
  "affected_pages": {
    "type": "array",
    "items": { "type": "string" }
  }
}
```

Benefit:

```text
Avoids stuffing affected page lists into ai_recommendation and improves reports/grouped fix modals.
```

## 19.2 Persist admin-only scan diagnostics

Potential entity: `ScanDiagnostic`

```json
{
  "project_id": "",
  "crawl_job_id": "",
  "raw_findings_count": 0,
  "grouped_findings_count": 0,
  "broken_links_count": 0,
  "crawl_warnings": [],
  "site_summary": {},
  "created_at": ""
}
```

Customer UI should still not show raw findings.

## 19.3 Replace simulated progress with real status updates

Future direction:

```text
CrawlJob.status should be updated by backend function/workflow stages. Frontend should poll getCrawlStatus or subscribe to CrawlJob changes.
```

## 19.4 Add JavaScript-rendering scanner tier

Future direction:

```text
HTML scan first -> if placeholder text/thin content/JS suspicion is found, run JS-rendered scan on selected important pages -> compare HTML vs rendered output -> store js_difference_detected fields.
```

## 19.5 Connect Search Console

Future integration would add:

```text
Queries, impressions, clicks, average position, page-level search performance, and real keyword gap prioritization.
```

---

# 20. Coded reference: primary scan pipeline pseudocode

```js
async function runSeoScan(project, job, currentUser) {
  await SeoIssue.deleteMany({ project_id: project.id });

  const advancedScanResponse = await functions.invoke("runAdvancedScan", {
    website_url: project.website_url,
    business_name: project.business_name,
    business_type: project.business_type,
    city: project.city,
    project_id: project.id,
    crawl_job_id: job.id,
  });

  const scanData = advancedScanResponse.data;
  const groupedFindings = scanData.grouped_findings || [];
  const crawledPages = scanData.crawled_pages || [];
  const mappedSeoIssues = groupedFindings.map(mapGroupedFindingToSeoIssue);

  const aiReviewed = await functions.invoke("aiReviewScan", {
    business_name: project.business_name,
    business_type: project.business_type,
    city: project.city,
    website_url: project.website_url,
    crawled_pages: crawledPages,
    raw_fixes: mappedSeoIssues,
    competitor_results: [],
  });

  const finalFixes = aiReviewed.data?.success
    ? aiReviewed.data.cleaned_fixes
    : mappedSeoIssues;

  await CrawledPage.bulkCreate(
    crawledPages.map((page) => ({
      ...mapCrawledPageForStorage(page),
      project_id: project.id,
      crawl_job_id: job.id,
      owner_user_id: currentUser.id,
    }))
  );

  await SeoIssue.bulkCreate(
    finalFixes.map((fix) => ({
      ...fix,
      project_id: project.id,
      crawl_job_id: job.id,
      owner_user_id: currentUser.id,
    }))
  );

  await CrawlJob.update(job.id, {
    status: "complete",
    pages_found: scanData.pages_found,
    pages_crawled: scanData.pages_crawled,
    seo_score: scanData.health_score,
    issues_found: finalFixes.length,
    completed_at: new Date().toISOString(),
  });

  await BusinessProject.update(project.id, {
    last_crawl_at: new Date().toISOString(),
    seo_score: scanData.health_score,
  });
}
```

---

# 21. Final architecture summary

The app is organized around a layered SEO intelligence pipeline:

```text
HTML crawler -> deterministic SEO analyzer -> AI strategist -> saved customer recommendations -> customer dashboard
```

The primary active scan function is `runAdvancedScan`. The AI strategist is `aiReviewScan`. Final customer-facing recommendations live in `SeoIssue`. The most important next architecture improvement is adding structured details/affected_pages support to `SeoIssue` so grouped findings can be stored cleanly without embedding diagnostic details inside recommendation text.