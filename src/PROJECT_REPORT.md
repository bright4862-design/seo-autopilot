# SEO Autopilot — Status Report for ChatGPT

> Copy-paste this entire document into ChatGPT to give it full context on the current state of the app.

---

## App Summary

**SEO Autopilot** is a SaaS dashboard that guides non-technical small business owners from sign-up → automated SEO scan → plain-English "Fix List." Built on Base44 (React + Vite + Tailwind + shadcn/ui frontend; Deno/TypeScript serverless backend; JSON-schema entities).

---

## Recent Changes (this session)

### 1. Customer-facing wording update for prepared fixes
The app does **not** actually modify the customer's website yet (no CMS integration exists). All wording was changed so it never implies the site was changed. The internal DB status `auto_fixed` is unchanged.

**Wording changes:**
| Old | New |
|-----|-----|
| "We can fix this" | "Fixes prepared" |
| "We fixed this" | "Fix prepared" |
| "Already done — nothing for you to do." | "We prepared these simple fixes for your review." |
| "Fixed automatically" / "Automatically fixed" | "Prepared for you" / "simple fixes were prepared for review" |

**Files changed:**
- `src/pages/FixList.jsx` — group title + subtitle
- `src/lib/mockData.js` — `STATUS_LABELS.auto_fixed` = "Fix prepared"
- `src/pages/CrawlStatus.jsx` — scan-complete summary label
- `src/pages/Issues.jsx` — summary badge label
- `src/pages/Reports.jsx` — report `summary` string + stat label
- `base44/functions/generateReport/entry.ts` — report `summary` string
- `src/pages/Dashboard.jsx` — StatCard label "Prepared for you" + subtitle "We prepared these for your review"

The three customer-facing Fix List groups are now:
1. **Fixes prepared** (status `auto_fixed`)
2. **Needs your approval** (status `needs_approval`)
3. **Needs a developer** (status `needs_developer`)

### 2. Auto-create `DeveloperRecommendation` records after each scan
After `SeoIssue` records are bulk-created in `src/pages/CrawlStatus.jsx`, the scan now also generates `DeveloperRecommendation` records automatically.

**Logic (in CrawlStatus.jsx `simulateCrawl`, after SeoIssue.bulkCreate):**
1. Clears old `DeveloperRecommendation` records for the project (`deleteMany({ project_id })`) so recommendations match the latest scan.
2. Filters the scan fixes where `requires_developer === true`.
3. For each, creates a `DeveloperRecommendation` with this field mapping:

| Field | Source / Rule |
|-------|---------------|
| `project_id` | current project id |
| `title` | `issue.issue_title` |
| `description` | `issue.plain_english_explanation` |
| `category` | `thin_content`→`content_pages`, `js_rendering`→`technical_seo`, `performance`→`speed_mobile`, `web_dev`→`website_structure`, otherwise `technical_seo` |
| `priority` | `issue.priority` |
| `business_impact` | `issue.why_it_matters` |
| `estimated_complexity` | `difficulty === "developer"` → `moderate`, otherwise `simple` |
| `recommended_package` | `moderate` → `500_cleanup`, `complex` → `custom_rebuild` |
| `status` | `"open"` |

The **Developer page** (`src/pages/Developer.jsx`) already reads live from `DeveloperRecommendation` records (filtered by project), so it reflects the new recommendations automatically. There is no separate "Request Help" page — just a button on the Developer page.

### 3. Scan note added to Crawl Status page
Added a persistent info box on the Crawl Status page (visible throughout the scan):

> "This scan checks the website HTML we can access directly. Some websites load important content after JavaScript runs, so deeper JavaScript rendering may require a developer review or upgraded scan."

Added `Info` icon import from lucide-react.

### 4. Redesigned Scan Complete summary box
The post-scan "complete" state on the Crawl Status page was redesigned:

- Heading: "Your scan is complete."
- Subtext: "We scanned N pages and found N recommended improvements."
- Three colored count cards:
  - **Prepared for you** (green) — `summary.we_can_fix`
  - **Needs your approval** (amber) — `summary.needs_approval`
  - **Needs a developer** (purple) — `summary.needs_developer`
- Removed the old SEO Score / Fixes Ready stat tiles and the green-tinted full-width card.

### 5. Dynamic "Top recommended actions" panel (replaces fixed list)
The Scan Complete box now shows a **dynamic** list of recommended next actions based on which issue types were actually found. Actions appear in priority order and only when relevant:

| Condition | Action shown |
|-----------|--------------|
| `summary.needs_approval > 0` | "Review approval items first" |
| `summary.needs_developer > 0` | "Review developer recommendations" |
| `summary.we_can_fix > 0` | "Review prepared titles and descriptions" |
| `issues_found === 0` | "No major issues found. Your site is looking good!" (label becomes "Status") |

Implementation: a `topActions` array is built by pushing each applicable action string in order; the panel header reads "Top recommended actions" (or "Status" when no issues), and when no issues were found it renders the single all-clear message instead of a numbered list.

### 6. Demo fallback no longer misleads on a clean site
Previously, if `runRealScan` succeeded but returned 0 issues, the Fix List would still be populated with the 8 hardcoded `SCAN_ISSUES` demo items — causing a mismatch (summary says "0 issues" but Fix List shows 8). Fixed by introducing a `scanSucceeded` flag: the demo fallback (`SCAN_ISSUES`) is now used **only** when `runRealScan` throws an error. When the demo fallback is used, `scanResult` is set with matching counts so the summary cards stay consistent with the Fix List.

### 7. Demo fallback wording no longer implies the site was changed
Updated the demo `SCAN_ISSUES` strings in `CrawlStatus.jsx` so they never imply the website was already modified (the app does not actually edit the user's site):

| Old | New |
|-----|-----|
| "We generated one for you." | "We prepared one for you." |
| "We auto-generated a title using your business name and services." | "We prepared a title using your business name and services." |
| "We removed the broken link." | "We flagged the broken link for removal." |
| "We removed the broken link automatically." | "We flagged this broken link for removal." |
| "We wrote a description highlighting your experience and service area — approve it to apply." | "We prepared a description highlighting your experience and service area — approve it to apply." |

---

## Current Architecture (unchanged)

### Core scan flow
1. **Onboarding** (`src/pages/Onboarding.jsx`) → creates `BusinessProject` + queued `CrawlJob` → redirects to `/crawl-status?autostart=1`
2. **CrawlStatus** (`src/pages/CrawlStatus.jsx`) → animates 10-step pipeline → calls `runRealScan` backend function → bulk-creates `CrawledPage` + `SeoIssue` + `DeveloperRecommendation` records → updates `BusinessProject.last_crawl_at` + `seo_score`
3. **FixList** (`src/pages/FixList.jsx`, route `/dashboard`) → groups `SeoIssue` records into 3 customer-friendly categories

### Backend functions (Deno/TypeScript)
- **`runRealScan`** — the real BFS crawler + deterministic SEO analyzer. Uses `fetch` + regex HTML parsing (no Playwright — unsupported in serverless). Returns `{ fixes, crawled_pages, health_score, pages_crawled, issues_found, summary }`. Does NOT persist records itself — frontend bulk-creates entities from the returned arrays.
- **`startCrawl`** — creates a queued `CrawlJob`
- **`generateReport`** — aggregates issues into a `Report` record
- **`getCrawlStatus`** — fetches a single `CrawlJob`

### Entities
`BusinessProject`, `CrawlJob`, `SeoIssue`, `CrawledPage`, `Competitor`, `RedirectRecommendation`, `MetadataRecommendation`, `DeveloperRecommendation`, `Report`, and built-in `User`.

### Issue detection rules (in `runRealScan`)
Deterministic, no LLM. Detects: broken pages (404/0), missing/weak meta title, missing meta description, missing canonical, and thin content (smart filter: only important business pages under 250 words, excludes utility pages like contact/login/cart/checkout/privacy/terms).

### AI Agent
`seo_assistant` agent reads `SeoIssue` + `DeveloperRecommendation` records, uses web search, accessible via in-app chat + WhatsApp + Telegram.

---

## Known Limitations / Open Items
- **No JavaScript rendering** in the crawler (HTML-only via `fetch`). The scan note now communicates this to users.
- **No real auto-fix application** — issues are marked `auto_fixed` but no actual changes are made to the user's website (scan + recommendation tool, not a CMS editor).
- **No Stripe payments** wired up (Stripe available in region FR).
- **No app connectors authorized** yet (Google Search Console, etc.).
- **Competitor data is mock** only.

---

*Last updated: 2026-07-05*