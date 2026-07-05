# SEO Autopilot — Global Status Report
**Date:** July 5, 2026

## What the product is
SEO Autopilot is a guided SEO assistant for small business owners. A user signs up, enters their business name and website URL (plus optional competitors), and the app scans their site, compares it to competitors, and produces a plain-English "Fix List" — no technical jargon. It never claims to modify the customer's website; it prepares recommendations for review.

## Core user journey
1. **Register / Login** — email + password with OTP verification, Google sign-in, forgot/reset password.
2. **Onboarding** — business name + website URL, plus up to 3 optional competitor websites; a project and scan job are created and the scan starts automatically.
3. **Live scan** — a real crawler fetches up to 25 pages of the actual website (following internal links) and checks titles, meta descriptions, canonical tags, broken pages (404s), and thin content on important pages.
4. **Competitor comparison** — each competitor site is crawled (up to 10 pages) and scored on: service pages, search-title quality, search-description coverage, content depth, FAQ usage, trust signals, and broken pages. Plain-English insights are generated when competitors look stronger.
5. **Scan complete screen** — pages scanned, improvements found, three counts (Prepared for you / Needs your approval / Needs a developer), and top recommended actions.
6. **Fix List (home)** — opens with a **"What to do first" guidance card** built from real issue counts (approvals → prepared fixes → website improvements, or "No major issues found"), then issues grouped into the three buckets with detail views (what's happening, why it matters, current vs. recommended, approve/reject/complete), plus scan history.
7. **Competitors page** — comparison summary, **top competitor gaps shown first**, then the "Your Site vs. Competitor Average" table with friendly labels, and a "Create improvement plan" button that adds gaps to Website Improvements (no duplicates).
8. **Website Improvements** (formerly "Developer") — recommendations requiring developer work, categorized, with suggested packages (DIY / $500 Cleanup / Custom Quote).
9. **Scan Report** (formerly "Reports") — simple summary reports with score, counts, competitor insights, and next steps.
10. **AI Assistant** — in-app chat agent for SEO questions.

## Navigation (customer-facing)
Fix List · New Scan · Competitors · Website Improvements · Scan Report · Assistant · Billing & Plans · Admin (admins only)

## Lead capture
- "Join Waitlist", "Request Cleanup", and "Contact Us" on the pricing page open a simple prefilled modal; requests saved as lead records.
- Admins manage all leads in a "Lead Requests" tab (new / contacted / closed).

## Trust & language
- Guided, plain-English wording throughout — "prepared fixes" / "recommended improvements", never "auto-fixed" or claims of modifying the site.
- No technical jargon in the customer UI (no "canonical", "schema", "indexation") — e.g. schema is labeled "Trust signals".
- A disclosure note explains the scan checks accessible HTML.

## Security
- All 11 data types (projects, scans, pages, issues, recommendations, competitors, competitor insights, redirects, metadata, reports, lead requests) are locked to their owner.
- Public visitors cannot read private records; one user cannot see another's data; admins retain full access.

## Billing status
- Pricing page shows all tiers with a "Plans are coming soon" banner.
- No payment processing connected yet (Stripe not connected — deliberate).

## Design
- Clean SaaS look: Inter font, blue→indigo gradient accents, white rounded cards on a soft background, green/amber/purple status colors, fully responsive with a mobile drawer sidebar.

## Known limitations / not built yet
- No JavaScript rendering in the crawler (HTML-only analysis).
- No actual website editing — everything is a recommendation.
- No payments, no PDF export of reports.
- No Google Search Console integration.