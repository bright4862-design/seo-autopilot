# SEO Autopilot — Full Project Report

> **Purpose:** This document contains everything about the SEO Autopilot app — its architecture, data models, backend logic, frontend pages, agent config, and current state. Feed this to an AI assistant (ChatGPT, etc.) to give it full context.

---

## 1. Project Overview

**SEO Autopilot** is a SaaS dashboard that guides non-technical small business owners from sign-up through an automated SEO scan to a simple, plain-English "Fix List."

### Core User Journey
1. **Landing page** → visitor signs up / registers
2. **Onboarding** → enters business name + website URL → creates a `BusinessProject` + queued `CrawlJob` → redirects to Crawl Status with `?autostart=1`
3. **Crawl Status** → animates a 10-step crawl pipeline, then calls the `runRealScan` backend function to do a **real BFS crawl** of the website using Deno `fetch` + regex-based HTML parsing (no Playwright/headless browser — serverless environment doesn't support it). The returned `crawled_pages` array is bulk-created as `CrawledPage` records on the frontend, and the returned `fixes` are bulk-created as `SeoIssue` records.
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

**Input payload:** `{ website_url, business_name, business_type, city, project_id, crawl_job_id }`

**Returns:** `{ business_name, website_url, health_score, pages_crawled, issues_found, crawled_pages[], fixes[], summary{we_can_fix,needs_approval,needs_developer} }`

The backend does **not** persist records itself — it returns the `crawled_pages` array and `fixes` array, and the frontend (`CrawlStatus.jsx`) bulk-creates `CrawledPage` and `SeoIssue` records with `project_id` + `crawl_job_id` attached.

```typescript
import { createClientFromRequest } from 'npm:@base44/sdk@0.8.31';

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();
    if (!user) return Response.json({ error: 'Unauthorized' }, { status: 401 });

    const { website_url, business_name, business_type, city, project_id, crawl_job_id } = await req.json();
    if (!website_url) return Response.json({ error: 'website_url is required' }, { status: 400 });

    let baseUrl = website_url;
    if (!/^https?:\/\//i.test(baseUrl)) baseUrl = 'https://' + baseUrl;
    const urlObj = new URL(baseUrl);
    const origin = urlObj.origin;
    const domain = urlObj.hostname.replace(/^www\./, '');

    // --- crawler: fetch homepage + internal pages (BFS) ---
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

    // --- analyzer: deterministic SEO issue detection ---
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

      // 1) Broken pages (404 or failed fetch)
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

      // 2) Missing / weak meta title (auto-fixable)
      if (!p.title) {
        const title = generateBasicTitle();
        issues.push({ /* meta_title — "needs a search title" — we_can_fix, auto_fixed */ });
      } else if (p.title.length < 15) {
        const title = generateBasicTitle();
        issues.push({ /* meta_title — "weak search title" — we_can_fix, auto_fixed */ });
      }

      // 3) Missing meta description (auto-fixable)
      if (!p.metaDesc) {
        const desc = generateBasicDescription();
        issues.push({ /* meta_description — "needs a better search description" — we_can_fix, auto_fixed */ });
      }

      // 4) Missing canonical (needs approval)
      if (!p.canonical) {
        issues.push({ /* canonical — "Google may be confused by duplicate page versions" — needs_approval */ });
      }

      // 5) Thin content — SMART filter (only important business pages, excludes utility pages)
      const utilityRe = /\/(contact|login|signin|signup|register|cart|checkout|privacy|terms|thank-you|thankyou|booking|account|search|tag|category|admin|wp-admin|dashboard|forgot|reset|cookie|legal|disclaimer)(\/|$)/i;
      const importantRe = /(^\/$)|(home|service|services|product|products|about|location|locations|contact|book|booking|appointment|pricing|packages|service-area|areas-we-serve)/i;
      if (p.status === 200 && p.wordCount < 250 && !utilityRe.test(pageUrl) && importantRe.test(pageUrl + '|' + (p.title || '') + '|' + (p.h1 || ''))) {
        issues.push({
          page_url: pageUrl, category: 'thin_content', customer_category: 'Page content',
          issue_title: 'This important page may need more helpful content',
          plain_english_explanation: 'This page looks important, but it may not give customers enough information to understand the service, location, benefits, or next step.',
          why_it_matters: 'Helpful pages usually explain the service, location, benefits, and common questions.',
          ai_recommendation: 'Add helpful details such as services offered, location served, common questions, proof or reviews, and a clear call-to-action.',
          current_value: `${p.wordCount} words`, recommended_value: '250+ words with service details & FAQ',
          priority: 'medium', difficulty: 'developer', group: 'needs_developer',
          can_auto_fix: false, requires_approval: false, requires_developer: true,
        });
      }
    }

    // --- health score + map groups to statuses ---
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
      crawled_pages: crawledPages.map(p => ({
        url: p.url,
        status_code: p.status || 0,
        title: p.title || "",
        meta_description: p.metaDesc || "",
        h1: p.h1 || "",
        canonical_url: p.canonical || "",
        word_count: p.wordCount || 0,
        indexable: true,
        in_sitemap: false,
        rendered_title: "",
        rendered_meta_description: "",
        rendered_canonical: "",
        js_difference_detected: false
      })),
      fixes: finalIssues,
      summary: {
        we_can_fix: finalIssues.filter(f => f.status === 'auto_fixed').length,
        needs_approval: finalIssues.filter(f => f.status === 'needs_approval').length,
        needs_developer: finalIssues.filter(f => f.requires_developer === true).length,
      },
    });
  } catch (error) {
    return Response.json({ error: error.message }, { status: 500 });
  }
});
```

**Issue detection rules (deterministic, no LLM):**

| # | Condition | Category | Group → Status | Priority |
|---|-----------|----------|----------------|---------|
| 1 | `status === 404` or `status === 0` (failed fetch) | `404_error` | `needs_approval` | high |
| 2 | `title` missing | `meta_title` | `we_can_fix` → `auto_fixed` | high |
| 3 | `title.length < 15` (too short/weak) | `meta_title` | `we_can_fix` → `auto_fixed` | medium |
| 4 | `metaDesc` missing | `meta_description` | `we_can_fix` → `auto_fixed` | medium |
| 5 | `canonical` missing | `canonical` | `needs_approval` | medium |
| 6 | Thin content — **only when ALL of:** status 200, NOT a utility page (contact/login/cart/checkout/privacy/terms/thank-you/booking/account/search/tag/category/admin), wordCount < 250, AND page looks important (homepage/service/product/location/about in URL, title, or h1) | `thin_content` | `needs_developer` | medium |

**Health score:** starts at 100, high = -8, medium = -5, low = -2, min 0.

**Summary counts:** `we_can_fix` and `needs_approval` count by `status`; `needs_developer` counts by `requires_developer === true` (the boolean field), so it stays accurate even if an issue's status changes later.

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
  "instructions": "You are the SEO Autopilot assistant, helping non-technical small business owners understand and act on their SEO audit results.\n\nYour two core jobs:\n1. EXPLAIN SeoIssue findings: read the SeoIssue entity, then explain in plain English what the issue is, why it matters, current vs recommended, using the plain_english_explanation / why_it_matters / current_value / recommended_value / ai_recommendation fields.\n2. PROVIDE ACTIONABLE STEPS for DeveloperRecommendations: read the entity and break it into a numbered, step-by-step plan a non-technical owner (or developer) can follow — WHAT to do, WHY it helps, WHO should do it.\n\nGuidelines: ground answers in real entity data; USE WEB SEARCH for general SEO concepts / best practices / CMS how-tos; keep language simple, friendly, encouraging; be concrete; use markdown formatting.",
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

Plus links to Billing & Plans, Admin, and Sign Out at the bottom.

### 5.3 Key Pages

#### Landing (`src/pages/Landing.jsx`)
Public marketing page with: hero, social proof stats, 9-feature grid, 3-step "How it works", testimonials, 3-tier pricing (Free / DIY $20/mo / Growth $49/mo), FAQ accordion, dark CTA, footer.

#### Onboarding (`src/pages/Onboarding.jsx`)
Simple form: business name + website URL → creates `BusinessProject` (status `active`, seo_score 0, plan `free`) + queued `CrawlJob` → redirects to `/crawl-status?autostart=1`.

#### Crawl Status (`src/pages/CrawlStatus.jsx`)
10-step visual pipeline (queued → crawling_html → rendering_js → checking_metadata → checking_canonicals → checking_sitemap → checking_redirects → benchmarking_competitors → generating_recommendations → complete). Steps animate with 1.5s delays, then calls `runRealScan` with `{ website_url, business_name, business_type, city, project_id, crawl_job_id }`.

**Data persistence after scan:**
1. Clears old `SeoIssue` records for the project (`deleteMany({ project_id })`)
2. Invokes `runRealScan` → gets `{ fixes, crawled_pages, health_score, pages_crawled, issues_found, summary }`
3. `bulkCreate` of `CrawledPage` records from `scanData.crawled_pages` (with `project_id` + `crawl_job_id`)
4. `bulkCreate` of `SeoIssue` records from `scanData.fixes` (with `project_id` + `crawl_job_id`); falls back to demo `SCAN_ISSUES` if the scan returns nothing or fails
5. Updates `CrawlJob.pages_found/pages_crawled` and `BusinessProject.last_crawl_at` + `seo_score`

When complete, shows a green summary card with the real `summary` breakdown (We fixed this / Needs approval / Needs developer), health score, and a "View Fix List" button.

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
The main dashboard (`/dashboard`). Loads project + all `SeoIssue` records, groups them by `status` into 3 categories:
- **We can fix this** (green, `auto_fixed`) — "Already done — nothing for you to do."
- **Needs your approval** (amber, `needs_approval`) — "We've prepared a fix — just review and approve."
- **Needs a developer** (purple, `needs_developer`) — "These need a developer to fix. We'll guide you through it."

Each issue opens an `IssueDetailModal`. Supports status updates (approve/reject/complete) that persist via `SeoIssue.update`.

#### Issue Detail Modal (`src/components/issues/IssueDetailModal.jsx`)
Full issue view: priority badge, category label, issue title, page URL, status badge with confidence %, plain-English explanation (blue box), why it matters (amber box), current vs recommended value (red/green boxes), AI recommendation (indigo box), capability flags, and action buttons (Approve / Reject / Mark Completed / Request Help depending on status).

#### Issues (`src/pages/Issues.jsx`)
Full issues table with search + filters (category, status, priority). Supports `?status=needs_approval` URL param for deep-linking from the Dashboard.

#### Assistant (`src/pages/Assistant.jsx`)
In-app AI chat interface with conversation sidebar, message bubbles (markdown + tool-call displays), suggested prompts, and WhatsApp/Telegram connect links. Uses `base44.agents.createConversation` / `addMessage` / `subscribeToConversation`.

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

// Bulk create crawled pages
await base44.entities.CrawledPage.bulkCreate(crawledPages.map(p => ({ ...p, project_id, crawl_job_id })));

// Invoke a backend function
const res = await base44.functions.invoke('runRealScan', { website_url, business_name, business_type, city, project_id, crawl_job_id });
// res.data.fixes, res.data.crawled_pages, res.data.health_score, res.data.pages_crawled, res.data.summary

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
- `CrawledPage` records persisted after each scan (bulk-created on the frontend from `runRealScan` output)
- `SeoIssue` records persisted after each scan (bulk-created on the frontend)
- Smart thin-content detection — only flags important business pages (homepage/service/product/location/about), excludes utility pages (contact/login/cart/checkout/privacy/terms/etc.), requires status 200 and < 250 words
- Fix List with 3-category grouping (auto_fixed / needs_approval / needs_developer)
- Issue detail modal with approve/reject/complete actions
- Issues table with search + filters
- AI Assistant agent (in-app chat + WhatsApp + Telegram links)
- Dashboard, Competitors, Reports, Developer, Billing, Admin pages

### 🔧 Known Limitations
- **No JavaScript rendering:** The crawler uses `fetch` (raw HTML only), not a headless browser. Pages that render content via JavaScript won't be fully analyzed. The `rendered_title` / `js_difference_detected` fields exist in the `CrawledPage` schema but aren't populated.
- **No real competitor benchmarking:** Competitor data is mock/demo only.
- **No real auto-fix application:** Issues are marked `auto_fixed` but no actual changes are made to the user's website (it's a scan + recommendation tool, not a CMS editor).
- **No Stripe payments:** Billing page exists but payments aren't wired up (Stripe available in region FR).
- **No app connectors authorized yet** (Google Search Console, etc.).

### 📋 Open Todos
1. Configure in-app agent LLM model settings
2. Set up Stripe payments (provider available: Stripe, region FR)
3. Wire AI to generate real `DeveloperRecommendation` records from crawl data (currently only `SeoIssue` records are created)
4. Implement real competitor crawling
5. Authorize app connectors (Google Search Console, Analytics, etc.)

### 🏗️ Architecture Decisions
- **Deno/TypeScript over Python:** Original spec used FastAPI + Playwright + BeautifulSoup. Base44 serverless only supports Deno, so replaced with `fetch` + regex parsing. Cheerio was considered but regex is lighter and sufficient for the current issue types.
- **Deterministic analyzer over LLM:** The analyzer previously called `InvokeLLM` for each scan (7–27 seconds). Replaced with deterministic rule-based logic matching the Python spec — now runs in ~200ms.
- **Backend returns data, frontend persists:** `runRealScan` returns `crawled_pages` + `fixes` arrays but does not write to the database itself. `CrawlStatus.jsx` bulk-creates `CrawledPage` and `SeoIssue` records with the project/crawl-job IDs. This keeps the function lightweight and lets the frontend control clearing + re-creating records per scan.
- **Smart thin-content filtering:** Thin content is only flagged for important business pages (homepage/service/product/location/about) under 250 words with status 200, excluding utility pages (contact/login/cart/checkout/privacy/terms/thank-you/booking/account/search/tag/category/admin). This prevents false positives on pages that are intentionally short.
- **Summary `needs_developer` counts by boolean field:** The scan summary's `needs_developer` count filters by `requires_developer === true` (not by `status`), so it stays accurate even after an issue's status changes.
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

*End of report. Last updated: 2026-07-05*