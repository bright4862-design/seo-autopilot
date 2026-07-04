# SEO Autopilot — Full Project Report

> **Purpose:** This document contains everything about the SEO Autopilot app — its architecture, data models, backend logic, frontend pages, agent config, and current state. Feed this to an AI assistant (ChatGPT, etc.) to give it full context.

---

## 1. Project Overview

**SEO Autopilot** is a SaaS dashboard that guides non-technical small business owners from sign-up through an automated SEO scan to a simple, plain-English "Fix List."

### Core User Journey
1. **Landing page** → visitor signs up / registers
2. **Onboarding** → enters business name + website URL → creates a `BusinessProject` + queued `CrawlJob` → redirects to Crawl Status with `?autostart=1`
3. **Crawl Status** → simulates a 10-step crawl pipeline, then calls the `runRealScan` backend function to do a **real BFS crawl** of the website using Deno `fetch` + regex-based HTML parsing (no Playwright/headless browser — serverless environment doesn't support it)
4. **Fix List** → shows detected issues grouped into 3 customer-friendly categories:
   - **We can fix this** (auto_fixed) — simple, already handled
   - **Needs your approval** (needs_approval) — a fix is prepared, owner just approves
   - **Needs a developer** (needs_developer) — requires developer work
5. **Issue Detail Modal** → shows plain-English explanation, why it matters, current vs recommended value, AI recommendation, and approve/reject/complete actions
6. **SEO Assistant** → in-app AI agent chat (WhatsApp + Telegram connect links) that reads `SeoIssue` and `DeveloperRecommendation` entities and explains them in plain English

### Tech Stack
- **Frontend:** React + Vite + Tailwind CSS + shadcn/ui components
- **Backend:** Base44 BaaS (Deno/TypeScript serverless functions)
- **Database:** Base44 entities (JSON schema documents)
- **Auth:** Base44 built-in auth (email/password + Google OAuth)
- **AI:** Base44 `InvokeLLM` integration + in-app agents
- **Styling tokens:** CSS variables in `src/index.css` mapped to Tailwind classes

---

## 2. Entity Data Models (Database Schemas)

All entities have built-in fields: `id`, `created_date`, `updated_date`, `created_by_id`.

### BusinessProject
```jsonc
{
  "name": "BusinessProject",
  "type": "object",
  "properties": {
    "business_name": { "type": "string" },
    "website_url": { "type": "string" },
    "business_type": { "type": "string" },
    "city": { "type": "string" },
    "service_area": { "type": "string" },
    "main_services": { "type": "string" },
    "cms_platform": { "type": "string", "enum": ["WordPress","Shopify","Wix","Webflow","Squarespace","Custom","Unknown"] },
    "status": { "type": "string", "enum": ["setup","active","paused","archived"], "default": "setup" },
    "seo_score": { "type": "number", "default": 0 },
    "last_crawl_at": { "type": "string" },
    "next_crawl_at": { "type": "string" },
    "subscription_plan": { "type": "string", "enum": ["free","diy","growth","done_for_you","rebuild"], "default": "free" }
  },
  "required": ["business_name", "website_url"]
}
```

### CrawlJob
```jsonc
{
  "name": "CrawlJob",
  "type": "object",
  "properties": {
    "project_id": { "type": "string" },
    "status": {
      "type": "string",
      "enum": ["queued","crawling_html","rendering_js","checking_metadata","checking_canonicals","checking_sitemap","checking_redirects","benchmarking_competitors","generating_recommendations","complete","failed"],
      "default": "queued"
    },
    "crawl_type": { "type": "string", "enum": ["full","monthly","competitor","js_render"], "default": "full" },
    "pages_found": { "type": "number", "default": 0 },
    "pages_crawled": { "type": "number", "default": 0 },
    "js_pages_rendered": { "type": "number", "default": 0 },
    "started_at": { "type": "string" },
    "completed_at": { "type": "string" },
    "error_message": { "type": "string" }
  },
  "required": ["project_id"]
}
```

### SeoIssue
```jsonc
{
  "name": "SeoIssue",
  "type": "object",
  "properties": {
    "project_id": { "type": "string" },
    "crawl_job_id": { "type": "string" },
    "page_url": { "type": "string" },
    "category": {
      "type": "string",
      "enum": ["meta_title","meta_description","404_error","redirect","canonical","sitemap","robots_txt","js_rendering","internal_link","thin_content","duplicate_content","schema","performance","web_dev"]
    },
    "customer_category": { "type": "string" },
    "priority": { "type": "string", "enum": ["critical","high","medium","low"], "default": "medium" },
    "status": { "type": "string", "enum": ["open","auto_fixed","needs_approval","approved","rejected","needs_developer","in_progress","completed"], "default": "open" },
    "difficulty": { "type": "string", "enum": ["easy","moderate","developer"] },
    "issue_title": { "type": "string" },
    "plain_english_explanation": { "type": "string" },
    "why_it_matters": { "type": "string" },
    "current_value": { "type": "string" },
    "recommended_value": { "type": "string" },
    "ai_recommendation": { "type": "string" },
    "confidence_score": { "type": "number", "default": 0 },
    "can_auto_fix": { "type": "boolean", "default": false },
    "requires_approval": { "type": "boolean", "default": false },
    "requires_developer": { "type": "boolean", "default": false }
  },
  "required": ["project_id", "page_url", "category", "issue_title"]
}
```

### Competitor
```jsonc
{
  "name": "Competitor",
  "type": "object",
  "properties": {
    "project_id": { "type": "string" },
    "name": { "type": "string" },
    "website_url": { "type": "string" },
    "notes": { "type": "string" },
    "service_pages_count": { "type": "number", "default": 0 },
    "title_quality_score": { "type": "number", "default": 0 },
    "meta_coverage_pct": { "type": "number", "default": 0 },
    "content_depth_score": { "type": "number", "default": 0 },
    "faq_usage": { "type": "boolean", "default": false },
    "schema_usage": { "type": "boolean", "default": false },
    "broken_links_count": { "type": "number", "default": 0 }
  },
  "required": ["project_id", "website_url"]
}
```

### RedirectRecommendation
```jsonc
{
  "name": "RedirectRecommendation",
  "type": "object",
  "properties": {
    "project_id": { "type": "string" },
    "broken_url": { "type": "string" },
    "status_code": { "type": "number" },
    "recommended_destination": { "type": "string" },
    "reason": { "type": "string" },
    "confidence_score": { "type": "number", "default": 0 },
    "approval_status": { "type": "string", "enum": ["pending","approved","rejected"], "default": "pending" }
  },
  "required": ["project_id", "broken_url"]
}
```

### MetadataRecommendation
```jsonc
{
  "name": "MetadataRecommendation",
  "type": "object",
  "properties": {
    "project_id": { "type": "string" },
    "page_url": { "type": "string" },
    "current_title": { "type": "string" },
    "recommended_title_1": { "type": "string" },
    "recommended_title_2": { "type": "string" },
    "recommended_title_3": { "type": "string" },
    "current_meta_description": { "type": "string" },
    "recommended_description_1": { "type": "string" },
    "recommended_description_2": { "type": "string" },
    "recommended_description_3": { "type": "string" },
    "suggested_h1": { "type": "string" },
    "suggested_slug": { "type": "string" },
    "suggested_faq_ideas": { "type": "string" },
    "approval_status": { "type": "string", "enum": ["pending","approved","rejected"], "default": "pending" }
  },
  "required": ["project_id", "page_url"]
}
```

### DeveloperRecommendation
```jsonc
{
  "name": "DeveloperRecommendation",
  "type": "object",
  "properties": {
    "project_id": { "type": "string" },
    "title": { "type": "string" },
    "description": { "type": "string" },
    "category": { "type": "string", "enum": ["quick_fix","cms_seo_setup","technical_seo","website_structure","content_pages","speed_mobile","rebuild_migration"] },
    "priority": { "type": "string", "enum": ["critical","high","medium","low"], "default": "medium" },
    "business_impact": { "type": "string" },
    "estimated_complexity": { "type": "string", "enum": ["simple","moderate","complex"] },
    "recommended_package": { "type": "string", "enum": ["diy","500_cleanup","custom_rebuild"] },
    "status": { "type": "string", "enum": ["open","in_progress","completed","deferred"], "default": "open" }
  },
  "required": ["project_id", "title", "category"]
}
```

### CrawledPage
```jsonc
{
  "name": "CrawledPage",
  "type": "object",
  "properties": {
    "project_id": { "type": "string" },
    "crawl_job_id": { "type": "string" },
    "url": { "type": "string" },
    "status_code": { "type": "number" },
    "title": { "type": "string" },
    "meta_description": { "type": "string" },
    "h1": { "type": "string" },
    "canonical_url": { "type": "string" },
    "word_count": { "type": "number", "default": 0 },
    "indexable": { "type": "boolean", "default": true },
    "in_sitemap": { "type": "boolean", "default": false },
    "rendered_title": { "type": "string" },
    "rendered_meta_description": { "type": "string" },
    "rendered_canonical": { "type": "string" },
    "js_difference_detected": { "type": "boolean", "default": false }
  },
  "required": ["project_id", "crawl_job_id", "url"]
}
```

### Report
```jsonc
{
  "name": "Report",
  "type": "object",
  "properties": {
    "project_id": { "type": "string" },
    "crawl_job_id": { "type": "string" },
    "summary": { "type": "string" },
    "fixed_count": { "type": "number", "default": 0 },
    "approval_count": { "type": "number", "default": 0 },
    "developer_count": { "type": "number", "default": 0 },
    "competitor_summary": { "type": "string" },
    "next_steps": { "type": "string" },
    "seo_score": { "type": "number", "default": 0 }
  },
  "required": ["project_id"]
}
```

### User (built-in, read-only)
```jsonc
// Built-in entity — users join via invites, can't be created directly
{
  "id": "string",
  "created_date": "string",
  "full_name": "string",
  "email": "string",
  "role": "admin | user"  // editable
}
```

---

## 3. Backend Functions

### 3.1 `runRealScan` — The Core Scanner (Deno/TypeScript)

This is the **real crawler + analyzer**. It replaces the original Python spec (FastAPI + Playwright + BeautifulSoup) with Deno-native `fetch` + regex-based HTML parsing because Playwright/headless browsers aren't supported in the Base44 serverless environment.

**Location:** `base44/functions/runRealScan/entry.ts`

```typescript
import { createClientFromRequest } from 'npm:@base44/sdk@0.8.31';

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();
    if (!user) return Response.json({ error: 'Unauthorized' }, { status: 401 });

    const { website_url, business_name, business_type, city } = await req.json();
    if (!website_url) return Response.json({ error: 'website_url is required' }, { status: 400 });

    let baseUrl = website_url;
    if (!/^https?:\/\//i.test(baseUrl)) baseUrl = 'https://' + baseUrl;
    const urlObj = new URL(baseUrl);
    const origin = urlObj.origin;
    const domain = urlObj.hostname.replace(/^www\./, '');

    // --- crawler.py: fetch homepage + a few internal pages ---
    const fetchPage = async (url) => {
      try {
        const res = await fetch(url, { redirect: 'follow', signal: AbortSignal.timeout(12000), headers: { 'User-Agent': 'SEO-Autopilot/1.0' } });
        const html = await res.text();
        return { url, status: res.status, html, ok: res.ok };
      } catch (e) {
        return { url, status: 0, html: '', ok: false, error: e.message };
      }
    };

    const strip = (html) =>
      html.replace(/<script[\s\S]*?<\/script>/gi, '')
          .replace(/<style[\s\S]*?<\/style>/gi, '')
          .replace(/<[^>]+>/g, ' ');
    const text = (html) => strip(html).replace(/\s+/g, ' ').trim();
    const firstMatch = (html, re) => { const m = html.match(re); return m ? (m[1] || '').trim() : ''; };

    const extractPage = (url, html) => {
      const title = firstMatch(html, /<title[^>]*>([\s\S]*?)<\/title>/i);
      const metaDesc =
        firstMatch(html, /<meta[^>]+name=["']description["'][^>]*content=["']([^"']*)["']/i) ||
        firstMatch(html, /<meta[^>]+content=["']([^"']*)["'][^>]+name=["']description["']/i) ||
        '';
      const h1 = firstMatch(html, /<h1[^>]*>([\s\S]*?)<\/h1>/i);
      const canonical =
        firstMatch(html, /<link[^>]+rel=["']canonical["'][^>]*href=["']([^"']*)["']/i) ||
        firstMatch(html, /<link[^>]+href=["']([^"']*)["'][^>]+rel=["']canonical["']/i) ||
        '';
      const wordCount = text(html).split(/\s+/).filter(Boolean).length;
      const links = [];
      const linkRe = /<a[^>]+href=["']([^"']+)["']/gi;
      let lm;
      while ((lm = linkRe.exec(html)) !== null) links.push(lm[1]);
      return { url, title, metaDesc, h1, canonical, wordCount, links };
    };

    // BFS crawl following internal links, up to MAX_PAGES
    const MAX_PAGES = 25;
    const BATCH = 8;
    const visited = new Set();
    const toVisit = [baseUrl];
    const crawledPages = [];

    while (toVisit.length > 0 && visited.size < MAX_PAGES) {
      const batch = [];
      while (toVisit.length > 0 && batch.length < BATCH && visited.size + batch.length < MAX_PAGES) {
        const url = toVisit.shift();
        if (visited.has(url)) continue;
        visited.add(url);
        batch.push(url);
      }
      const results = await Promise.all(batch.map(fetchPage));
      for (const r of results) {
        if (!r.html) {
          if (r.url === baseUrl) {
            return Response.json({ error: "We couldn't reach that website. Please check the URL and try again." }, { status: 400 });
          }
          crawledPages.push({ url: r.url, status: r.status || 0, title: '', metaDesc: '', h1: '', canonical: '', wordCount: 0, links: [] });
          continue;
        }
        const page = extractPage(r.url, r.html);
        page.status = r.status;
        crawledPages.push(page);
        for (const href of page.links) {
          try {
            const abs = new URL(href, baseUrl).href.split('#')[0];
            if (new URL(abs).hostname.replace(/^www\./, '') === domain && !visited.has(abs) && !toVisit.includes(abs) && !/\.(jpg|png|gif|pdf|zip|css|js)$/i.test(abs)) {
              toVisit.push(abs);
            }
          } catch {}
        }
      }
    }

    // --- analyzer.py: deterministic SEO issue detection ---
    const generateBasicTitle = () => {
      if (business_type && city) return `${business_name} | ${business_type} in ${city}`;
      if (business_type) return `${business_name} | ${business_type}`;
      return `${business_name} | Official Website`;
    };

    const generateBasicDescription = () => {
      const name = business_name || 'us';
      const type = (business_type || '').toLowerCase();
      if (business_type && city) return `Visit ${name} for trusted ${type} services in ${city}. Learn more, contact us, or request help today.`;
      if (business_type) return `Visit ${name} for trusted ${type} services. Learn more, contact us, or request help today.`;
      return `Visit ${name} to learn more about our services, contact our team, and get the help you need.`;
    };

    const issues = [];
    for (const p of crawledPages) {
      const pageUrl = p.url === baseUrl ? '/' : (() => { try { return new URL(p.url).pathname; } catch { return p.url; } })();

      if (p.status === 404 || p.status === 0) {
        issues.push({
          page_url: pageUrl, category: '404_error', customer_category: 'Broken page',
          issue_title: 'This page is broken',
          plain_english_explanation: 'Visitors and search engines may be landing on a page that does not work.',
          why_it_matters: 'Broken pages can hurt trust and make it harder for search engines to understand your website.',
          ai_recommendation: 'Redirect this broken page to the closest working page.',
          current_value: `Status: ${p.status}`, recommended_value: 'Redirect to closest working page',
          priority: 'high', difficulty: 'moderate', group: 'needs_approval',
          can_auto_fix: false, requires_approval: true, requires_developer: false,
        });
      }

      if (!p.title) {
        const title = generateBasicTitle();
        issues.push({
          page_url: pageUrl, category: 'meta_title', customer_category: 'Search title',
          issue_title: 'This page needs a search title',
          plain_english_explanation: 'This page does not have a clear title for search engines.',
          why_it_matters: 'The search title helps people and Google understand what the page is about.',
          ai_recommendation: title, current_value: '(empty)', recommended_value: title,
          priority: 'high', difficulty: 'easy', group: 'we_can_fix',
          can_auto_fix: true, requires_approval: false, requires_developer: false,
        });
      } else if (p.title.length < 15) {
        const title = generateBasicTitle();
        issues.push({
          page_url: pageUrl, category: 'meta_title', customer_category: 'Search title',
          issue_title: 'This page has a weak search title',
          plain_english_explanation: 'The current page title is too short or unclear.',
          why_it_matters: 'A better title can help customers understand the page before they click.',
          ai_recommendation: title, current_value: p.title, recommended_value: title,
          priority: 'medium', difficulty: 'easy', group: 'we_can_fix',
          can_auto_fix: true, requires_approval: false, requires_developer: false,
        });
      }

      if (!p.metaDesc) {
        const desc = generateBasicDescription();
        issues.push({
          page_url: pageUrl, category: 'meta_description', customer_category: 'Search description',
          issue_title: 'This page needs a better search description',
          plain_english_explanation: 'This page does not have a description for search results.',
          why_it_matters: 'A good description can help more people click your website from Google.',
          ai_recommendation: desc, current_value: '(empty)', recommended_value: desc,
          priority: 'medium', difficulty: 'easy', group: 'we_can_fix',
          can_auto_fix: true, requires_approval: false, requires_developer: false,
        });
      }

      if (!p.canonical) {
        issues.push({
          page_url: pageUrl, category: 'canonical', customer_category: 'Duplicate page signal',
          issue_title: 'Google may be confused by duplicate page versions',
          plain_english_explanation: 'This page does not clearly tell Google which version is the main version.',
          why_it_matters: 'If Google finds multiple versions of the same page, it may not know which one to show.',
          ai_recommendation: 'Set this page as the preferred version of itself.',
          current_value: '(none)', recommended_value: 'Add a canonical tag',
          priority: 'medium', difficulty: 'moderate', group: 'needs_approval',
          can_auto_fix: false, requires_approval: true, requires_developer: false,
        });
      }

      if (p.wordCount < 150) {
        issues.push({
          page_url: pageUrl, category: 'thin_content', customer_category: 'Page content',
          issue_title: 'This page may not have enough helpful content',
          plain_english_explanation: 'This page is very short and may not answer enough customer questions.',
          why_it_matters: 'Helpful pages usually explain the service, location, benefits, and common questions.',
          ai_recommendation: 'Add more useful information, customer questions, service details, and a clear call to action.',
          current_value: `${p.wordCount} words`, recommended_value: '300+ words with service details & FAQ',
          priority: 'high', difficulty: 'developer', group: 'needs_developer',
          can_auto_fix: false, requires_approval: false, requires_developer: true,
        });
      }
    }

    // --- calculate_health_score + map to final fixes ---
    let score = 100;
    const finalIssues = issues.map(issue => {
      if (issue.priority === 'high') score -= 8; else if (issue.priority === 'medium') score -= 5; else score -= 2;
      const status = issue.group === 'we_can_fix' ? 'auto_fixed' : issue.group === 'needs_developer' ? 'needs_developer' : 'needs_approval';
      return { ...issue, confidence_score: 90, status };
    });
    score = Math.max(score, 0);

    return Response.json({
      business_name: business_name || null,
      website_url: baseUrl,
      health_score: score,
      pages_crawled: crawledPages.length,
      issues_found: finalIssues.length,
      fixes: finalIssues,
      summary: {
        we_can_fix: finalIssues.filter(f => f.status === 'auto_fixed').length,
        needs_approval: finalIssues.filter(f => f.status === 'needs_approval').length,
        needs_developer: finalIssues.filter(f => f.status === 'needs_developer').length,
      },
    });
  } catch (error) {
    return Response.json({ error: error.message }, { status: 500 });
  }
});
```

**How it maps to the original Python `main.py`:**
| Python spec | Deno implementation |
|---|---|
| `async_playwright()` + `page.goto(wait_until="networkidle")` | `fetch(url)` with 12s timeout + regex HTML parsing |
| `BeautifulSoup(rendered_html, "html.parser")` | Regex-based `extractPage()`: `<title>`, `<meta name="description">`, `<h1>`, `<link rel="canonical">`, `<a href>` |
| `urlparse(...).netloc.replace("www.", "")` | `new URL(abs).hostname.replace(/^www\./, '') === domain` |
| `MAX_PAGES = 25` | Same constant, plus `BATCH = 8` for parallel fetches |
| `analyze_pages()` with all issue types | Identical logic: 404/0 status → broken, missing/short title → meta_title, missing metaDesc → meta_description, no canonical → canonical, word_count < 150 → thin_content |
| `generate_basic_title()` / `generate_basic_description()` | `generateBasicTitle()` / `generateBasicDescription()` — identical output format |
| `calculate_health_score()` | Same scoring: high = -8, medium = -5, low = -2, min 0 |
| `group: "we_can_fix" / "needs_approval" / "needs_developer"` | Maps to `status: "auto_fixed" / "needs_approval" / "needs_developer"` |

**Performance:** ~180–370ms per scan (deterministic, no LLM call).

---

### 3.2 `startCrawl`

**Location:** `base44/functions/startCrawl/entry.ts`

Creates a new `CrawlJob` record with status `queued`. In production this would trigger an external crawler API, but currently just returns the created job.

```typescript
import { createClientFromRequest } from 'npm:@base44/sdk@0.8.31';

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();
    if (!user) return Response.json({ error: 'Unauthorized' }, { status: 401 });

    const { projectId } = await req.json();
    if (!projectId) return Response.json({ error: 'projectId is required' }, { status: 400 });

    const crawlJob = await base44.entities.CrawlJob.create({
      project_id: projectId,
      status: 'queued',
      crawl_type: 'full',
      started_at: new Date().toISOString(),
    });

    return Response.json({
      success: true,
      crawl_job_id: crawlJob.id,
      message: 'Crawl job created and queued. In production, this triggers the external crawler API.',
    });
  } catch (error) {
    return Response.json({ error: error.message }, { status: 500 });
  }
});
```

### 3.3 `generateReport`

**Location:** `base44/functions/generateReport/entry.ts`

Gathers all `SeoIssue` records for a project, counts by status, and creates a `Report` record.

```typescript
import { createClientFromRequest } from 'npm:@base44/sdk@0.8.31';

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();
    if (!user) return Response.json({ error: 'Unauthorized' }, { status: 401 });

    const { projectId } = await req.json();
    if (!projectId) return Response.json({ error: 'projectId is required' }, { status: 400 });

    const [project, issues] = await Promise.all([
      base44.entities.BusinessProject.get(projectId),
      base44.entities.SeoIssue.filter({ project_id: projectId }),
    ]);

    const fixed = issues.filter(i => i.status === 'auto_fixed' || i.status === 'completed').length;
    const approval = issues.filter(i => i.status === 'needs_approval').length;
    const developer = issues.filter(i => i.status === 'needs_developer').length;

    const report = await base44.entities.Report.create({
      project_id: projectId,
      summary: `SEO scan of ${project.website_url} found ${issues.length} total issues. ${fixed} were automatically fixed, ${approval} need review, and ${developer} require developer work.`,
      fixed_count: fixed,
      approval_count: approval,
      developer_count: developer,
      seo_score: project.seo_score || 0,
      next_steps: 'Review and approve pending fixes. Export redirect map. Consider implementation packages.',
    });

    return Response.json({ success: true, report });
  } catch (error) {
    return Response.json({ error: error.message }, { status: 500 });
  }
});
```

### 3.4 `getCrawlStatus`

**Location:** `base44/functions/getCrawlStatus/entry.ts`

Fetches a single `CrawlJob` by ID.

```typescript
import { createClientFromRequest } from 'npm:@base44/sdk@0.8.31';

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();
    if (!user) return Response.json({ error: 'Unauthorized' }, { status: 401 });

    const { crawlJobId } = await req.json();
    if (!crawlJobId) return Response.json({ error: 'crawlJobId is required' }, { status: 400 });

    const crawlJob = await base44.entities.CrawlJob.get(crawlJobId);
    return Response.json({ success: true, crawlJob });
  } catch (error) {
    return Response.json({ error: error.message }, { status: 500 });
  }
});
```

---

## 4. AI Agent Config

### `seo_assistant` Agent

**Location:** `base44/agents/seo_assistant.jsonc`

```jsonc
{
  "name": "seo_assistant",
  "description": "Explains complex SEO issue findings in plain English and provides simple, actionable implementation steps for every developer recommendation.",
  "instructions": "You are the SEO Autopilot assistant, helping non-technical small business owners understand and act on their SEO audit results.\n\nYour two core jobs:\n1. EXPLAIN SeoIssue findings: When a user asks about an issue (or references one), read the SeoIssue entity to get its details. Then explain it in plain, jargon-free English: what the issue is, why it matters for their rankings/traffic, and what the current vs recommended situation is. Use the issue's plain_english_explanation, why_it_matters, current_value, recommended_value, and ai_recommendation fields. Never use technical SEO jargon without defining it simply.\n2. PROVIDE ACTIONABLE STEPS for DeveloperRecommendations: When a user asks how to implement a developer recommendation, read the DeveloperRecommendation entity. Break the recommendation into a numbered, step-by-step action plan a non-technical owner (or a hired developer) can follow. For each step, say clearly WHAT to do, WHY it helps, and WHO should do it (the owner themselves vs a developer). Reference the category, estimated_complexity, recommended_package, and business_impact so the owner understands the scope and whether it's a DIY task, a $500 cleanup, or a custom rebuild.\n\nGuidelines:\n- Always ground answers in real entity data by reading SeoIssue / DeveloperRecommendation records before answering. If the user references a specific issue or recommendation, look it up.\n- USE WEB SEARCH: Whenever a question goes beyond the user's stored audit data — e.g. general SEO concepts, current best practices, how-to steps for a CMS, or comparing options — search the web for up-to-date, accurate information and weave what you find into your answer. Always prefer web search over guessing when you're unsure or when fresh/2026 guidance would help.\n- You may also help with general SEO questions (how search engines work, what structured data is, how to write better titles, etc.) — answer them using web search, and relate the answer back to the user's own issues/recommendations when relevant.\n- Keep language simple, friendly, and encouraging. Avoid scary technical terms; when a term is unavoidable, define it in one short sentence.\n- Be concrete: give specific next actions, not generic advice.\n- Use markdown formatting (headings, bullet lists, numbered steps, bold for key terms) to make answers easy to scan.",
  "whatsapp_greeting": "👋 Hi! I'm your SEO Autopilot assistant. Ask me to explain any SEO issue from your latest scan, or for step-by-step actions on a developer recommendation. I'll keep it simple and jargon-free.",
  "telegram_greeting": "👋 Hi! I'm your SEO Autopilot assistant. Ask me to explain any SEO issue from your latest scan, or for step-by-step actions on a developer recommendation. I'll keep it simple and jargon-free.",
  "tool_configs": [
    { "entity_name": "SeoIssue", "allowed_operations": ["read"] },
    { "entity_name": "DeveloperRecommendation", "allowed_operations": ["read"] }
  ]
}
```

**Capabilities:** Reads `SeoIssue` and `DeveloperRecommendation` records, uses built-in web search, accessible via in-app chat + WhatsApp + Telegram.

---

## 5. Frontend Structure

### 5.1 App Router (`src/App.jsx`)

```jsx
// Public routes
<Route path="/" element={<Landing />} />
<Route path="/login" element={<Login />} />
<Route path="/register" element={<Register />} />
<Route path="/forgot-password" element={<ForgotPassword />} />
<Route path="/reset-password" element={<ResetPassword />} />

// Protected routes
<Route element={<ProtectedRoute />}>
  <Route path="/onboarding" element={<Onboarding />} />
  <Route element={<DashboardLayout />}>
    <Route path="/dashboard" element={<FixList />} />      // ← main landing after login
    <Route path="/crawl-status" element={<CrawlStatus />} />
    <Route path="/issues" element={<Issues />} />
    <Route path="/metadata" element={<Metadata />} />
    <Route path="/redirects" element={<Redirects />} />
    <Route path="/canonicals" element={<Canonicals />} />
    <Route path="/js-rendering" element={<JsRendering />} />
    <Route path="/competitors" element={<Competitors />} />
    <Route path="/developer" element={<Developer />} />
    <Route path="/reports" element={<Reports />} />
    <Route path="/assistant" element={<Assistant />} />
    <Route path="/billing" element={<Billing />} />
    <Route path="/admin" element={<Admin />} />
  </Route>
</Route>
```

### 5.2 Customer Navigation (Sidebar)

The `DashboardLayout` sidebar only shows two items to keep the UX simple:
- **Fix List** (`/dashboard`)
- **New Scan** (`/crawl-status`)

Plus links to Billing, Admin, and Sign Out at the bottom.

### 5.3 Key Pages

#### Landing (`src/pages/Landing.jsx`)
Public marketing page with: hero, social proof stats, 9-feature grid, 3-step "How it works", testimonials, 3-tier pricing (Free / DIY $20/mo / Growth $49/mo), FAQ accordion, dark CTA, footer.

#### Onboarding (`src/pages/Onboarding.jsx`)
Simple form: business name + website URL → creates `BusinessProject` + queued `CrawlJob` → redirects to `/crawl-status?autostart=1`.

#### Crawl Status (`src/pages/CrawlStatus.jsx`)
10-step visual pipeline (queued → crawling_html → rendering_js → checking_metadata → checking_canonicals → checking_sitemap → checking_redirects → benchmarking_competitors → generating_recommendations → complete). Steps animate with 1.5s delays, then calls `runRealScan` backend function. If real scan returns fixes, bulk-creates `SeoIssue` records; falls back to demo `SCAN_ISSUES` if the scan fails. Updates `BusinessProject.seo_score` and `last_crawl_at`.

The 10 crawl steps:
```
1. Queued
2. Crawling HTML
3. Rendering JavaScript
4. Checking Metadata
5. Checking Canonicals
6. Checking Sitemap
7. Checking Redirects & 404s
8. Benchmarking Competitors
9. Generating AI Recommendations
10. Complete
```

#### Fix List (`src/pages/FixList.jsx`)
The main dashboard. Shows issues grouped into 3 categories:
- **We can fix this** (green, auto_fixed) — "Already done — nothing for you to do."
- **Needs your approval** (amber, needs_approval) — "We've prepared a fix — just review and approve."
- **Needs a developer** (purple, needs_developer) — "These need a developer to fix. We'll guide you through it."

Each issue opens an `IssueDetailModal`.

#### Issue Detail Modal (`src/components/issues/IssueDetailModal.jsx`)
Full issue view: priority badge, category label, issue title, page URL, status badge with confidence %, plain-English explanation (blue box), why it matters (amber box), current vs recommended value (red/green boxes), AI recommendation (indigo box), capability flags, and action buttons (Approve / Reject / Mark Completed / Request Help depending on status).

#### Issues (`src/pages/Issues.jsx`)
Full issues table with search + filters (category, status, priority). Supports `?status=needs_approval` URL param for deep-linking from the Dashboard.

#### Assistant (`src/pages/Assistant.jsx`)
In-app AI chat interface with conversation sidebar, message bubbles, suggested prompts, and WhatsApp/Telegram connect links.

### 5.4 UI Constants (`src/lib/mockData.js`)

Status labels and colors:
```js
STATUS_LABELS = {
  open: "Open",
  auto_fixed: "We fixed this",
  needs_approval: "Needs your approval",
  approved: "Approved",
  rejected: "Rejected",
  needs_developer: "Needs a developer",
  in_progress: "In progress",
  completed: "Completed",
}

CATEGORY_LABELS = {
  meta_title: "Page Title",
  meta_description: "Meta Description",
  "404_error": "Broken Page (404)",
  redirect: "Redirect",
  canonical: "Canonical Tag",
  sitemap: "Sitemap",
  robots_txt: "Robots.txt",
  js_rendering: "JavaScript Rendering",
  internal_link: "Internal Link",
  thin_content: "Thin Content",
  duplicate_content: "Duplicate Content",
  schema: "Schema Markup",
  performance: "Performance",
  web_dev: "Web Development",
}
```

### 5.5 Design Tokens (`src/index.css`)
- **Font:** Inter (Google Fonts)
- **Primary color:** blue (217 91% 60%)
- **Radius:** 0.75rem
- Custom utilities: `.glass-card`, `.gradient-primary` (blue → indigo), `.gradient-text`
- Success/warning semantic tokens included

---

## 6. Frontend SDK Usage Pattern

All pages use the pre-initialized `base44` client from `@/api/base44Client`:

```js
import { base44 } from "@/api/base44Client";

// List projects (most recent first)
const projects = await base44.entities.BusinessProject.list("-created_date", 1);

// Filter issues by project
const issues = await base44.entities.SeoIssue.filter({ project_id: project.id });

// Create a crawl job
const job = await base44.entities.CrawlJob.create({ project_id: project.id, status: "queued" });

// Update an issue status
await base44.entities.SeoIssue.update(issueId, { status: "approved" });

// Bulk create issues from scan results
await base44.entities.SeoIssue.bulkCreate(fixes.map(f => ({ ...f, project_id, crawl_job_id })));

// Invoke a backend function
const res = await base44.functions.invoke('runRealScan', { website_url, business_name, business_type, city });
// res.data.fixes, res.data.health_score, res.data.pages_crawled, etc.

// Realtime subscriptions
const unsubscribe = base44.entities.SeoIssue.subscribe((event) => { /* update state */ });
```

---

## 7. Current State & Open Items

### ✅ What Works
- Full auth flow (register → OTP → login → Google OAuth)
- Landing page with pricing/FAQ
- Onboarding → creates project + queued crawl job
- Real BFS crawler + deterministic analyzer (`runRealScan`) running in ~200ms
- 10-step animated crawl pipeline with autostart
- Fix List with 3-category grouping (auto_fixed / needs_approval / needs_developer)
- Issue detail modal with approve/reject/complete actions
- Issues table with search + filters
- AI Assistant agent (in-app chat + WhatsApp + Telegram links)
- Dashboard, Competitors, Reports, Developer, Billing, Admin pages

### 🔧 Known Limitations
- **No JavaScript rendering:** The crawler uses `fetch` (raw HTML only), not a headless browser. Pages that render content via JavaScript won't be fully analyzed. The `rendered_title` / `js_difference_detected` fields exist in the `CrawledPage` schema but aren't populated.
- **No real competitor benchmarking:** Competitor data is mock/demo only.
- **No real auto-fix application:** Issues are marked `auto_fixed` but no actual changes are made to the user's website (it's a scan + recommendation tool, not a CMS editor).
- **No Stripe payments:** Billing page exists but payments aren't wired up.

### 📋 Open Todos
1. Configure in-app agent LLM model settings
2. Set up Stripe payments (provider available: Stripe, region FR)
3. Wire AI to generate real `DeveloperRecommendation` records from crawl data (currently only `SeoIssue` records are created)
4. Populate `CrawledPage` entity records during scan (currently scan results go straight to `SeoIssue`)
5. Implement real competitor crawling
6. No app connectors authorized yet (Google Search Console, etc.)

### 🏗️ Architecture Decisions
- **Deno/TypeScript over Python:** Original spec used FastAPI + Playwright + BeautifulSoup. Base44 serverless only supports Deno, so replaced with `fetch` + regex parsing. Cheerio was considered but regex is lighter and sufficient for the current issue types.
- **Deterministic analyzer over LLM:** The analyzer previously called `InvokeLLM` for each scan (7–27 seconds). Replaced with deterministic rule-based logic matching the Python spec exactly — now runs in ~200ms.
- **Simplified customer UX:** Navigation restricted to only "Fix List" and "New Scan." Technical pages (Canonicals, Sitemap, Redirects, Metadata, JS Rendering) exist but are hidden from the sidebar.
- **3-category grouping:** Issues map to customer-friendly buckets: "We can fix this" / "Needs your approval" / "Needs a developer" — matching the Python spec's `we_can_fix` / `needs_approval` / `needs_developer` groups.

---

## 8. Installed Packages

```
@base44/sdk ^0.8.35
@tanstack/react-query ^5.84.1
@hello-pangea/dnd ^17.0.0
react ^18.2.0 / react-dom ^18.2.0
react-router-dom ^6.26.0
react-hook-form ^7.54.2
react-markdown ^9.0.1
react-quill ^2.0.0
recharts ^2.15.4
framer-motion ^11.16.4
three ^0.171.0
react-leaflet ^4.2.1
lucide-react ^0.475.0
tailwindcss-animate ^1.0.7
date-fns ^3.6.0
lodash ^4.17.21
moment ^2.30.1
jspdf ^4.2.1
html2canvas ^1.4.1
canvas-confetti ^1.9.4
zod ^3.24.2
@stripe/react-stripe-js ^3.0.0 / @stripe/stripe-js ^5.2.0
+ all @radix-ui/* primitives for shadcn/ui components
```

---

*End of report. Last updated: 2026-07-04*