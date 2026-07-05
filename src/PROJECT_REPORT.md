# SEO Autopilot — Global Status Report
**Date:** July 5, 2026

## What the product is
SEO Autopilot is an AI-powered SEO assistant for small business owners. A user signs up, enters their business name and website URL (plus optional competitors), and the app scans their site, has AI review the findings, compares the site to competitors, and produces a short, plain-English action plan — no technical jargon, no overwhelm. It never claims to modify the customer's website; it prepares recommendations for review.

## The intelligence pipeline (core differentiator)
The product is built as a four-stage pipeline:

1. **Crawler — collects facts.** A real crawler fetches up to 25 pages of the actual website (following internal links) and extracts titles, descriptions, headings, canonical signals, word counts, link structure, and broken pages (404s).
2. **Rules — find obvious issues.** Fast deterministic checks flag missing/weak titles, missing descriptions, duplicate-page signals, broken pages, and thin content on important pages. Low-value utility pages (cart, checkout, login, account, search, privacy, terms, thank-you, payment, admin, legal, etc.) are automatically excluded unless broken, and identical issues are deduplicated before anything is saved.
3. **AI review — filters, groups, rewrites, prioritizes, explains.** A single AI strategist pass per scan receives the business context (name, type, city), all crawled pages, the raw rule findings, and competitor results, and returns structured JSON with:
   - **cleaned_fixes** — duplicates merged, utility-page noise removed, business-important pages first, every issue rewritten in warm plain English with business-specific recommended titles and descriptions
   - **top_recommended_actions** — 2–4 prioritized next steps, each with a title, a reason, and a priority
   - **grouped_page_recommendations** — related fixes for the same page merged into one page-level recommendation
   - **ignored_low_value_pages** — transparency about what was skipped and why
   - **plain_english_summary** — a 2–3 sentence owner-friendly summary of the scan
   The AI is instructed to never claim anything was fixed or published, never promise rankings, and to use honest language ("prepared", "recommended", "may help").
4. **UI — shows the few best next actions.** If AI review fails for any reason, the app silently falls back to the filtered, deduplicated rule-based results, so a scan always completes.

## Other AI abilities in the product
- **AI-written recommendations** — search titles and descriptions are generated specifically for the business (name, type, city), not generic templates.
- **Competitor gap analysis** — competitor sites are crawled and scored (service pages, title quality, description coverage, content depth, FAQ usage, trust signals, broken pages), and plain-English gap insights are generated where competitors look stronger.
- **In-app AI Assistant** — a chat agent that answers SEO questions about the user's own site and data.
- **AI-informed reports** — scan reports and PDF exports summarize AI findings in business-owner language.

## Core user journey
1. **Register / Login** — email + password with OTP verification, Google sign-in, forgot/reset password.
2. **Onboarding** — business name + website URL, plus up to 3 optional competitor websites; a project and scan job are created and the scan starts automatically.
3. **Live scan** — the four-stage pipeline above runs with a visible step-by-step progress screen.
4. **Scan complete screen** — pages scanned, improvements found, three counts (Prepared for you / Needs your approval / Needs a developer), and the AI's top recommended actions with reasons.
5. **Fix List (home)** — opens with a "What to do first" guidance card, then rich issue cards showing the title, page URL, short explanation, status badge, and impact badge with a "Review recommendation" CTA. Multiple prepared fixes for one page are grouped into a single "Improve your [Page] page" card with a combined review modal.
6. **Competitors page** — top competitor gaps first, then the "Your Site vs. Competitor Average" table, and a "Create improvement plan" button.
7. **Website Improvements** — recommendations requiring developer work, categorized, with suggested packages (DIY / $500 Cleanup / Custom Quote).
8. **Scan Report** — summary reports with score, counts, competitor insights, next steps, and a one-click plain-English PDF export.
9. **AI Assistant** — in-app chat for SEO questions.

## Navigation (customer-facing)
Fix List · New Scan · Competitors · Website Improvements · Scan Report · Assistant · Billing & Plans · Admin (admins only)

## Lead capture
- "Join Waitlist", "Request Cleanup", and "Contact Us" on the pricing page open a simple prefilled modal; requests saved as lead records.
- Admins manage all leads in a "Lead Requests" tab (new / contacted / closed).

## Trust & language
- Guided, plain-English wording throughout — "prepared fixes" / "recommended improvements", never "auto-fixed" or claims of modifying the site.
- No unexplained technical jargon in the customer UI.
- Clean scans say: "Your scan looks clean based on the accessible HTML we reviewed" with an invitation to add competitors or request a manual review.
- A disclosure note explains the scan checks accessible HTML.

## Security
- All 11 data types (projects, scans, pages, issues, recommendations, competitors, competitor insights, redirects, metadata, reports, lead requests) are locked to their owner.
- Public visitors cannot read private records; one user cannot see another's data; admins retain full access.

## Billing status
- Pricing page shows all tiers with a "Plans are coming soon" banner.
- No payment processing connected yet (deliberate).

## Design
- Clean SaaS look: Inter font, blue→indigo gradient accents, white rounded cards on a soft background, green/amber/purple status colors, fully responsive with a mobile drawer sidebar.

## Known limitations / not built yet
- No JavaScript rendering in the crawler (HTML-only analysis).
- No actual website editing — everything is a recommendation.
- No payments.
- No Google Search Console integration.