# SEO Autopilot — Project Status Report
**Date:** July 5, 2026

## What the product is
SEO Autopilot is a SaaS dashboard for small business owners. A user signs up, enters their business name and website URL (plus optional competitors), and the app scans their site, compares it to competitors, and produces a plain-English "Fix List" — no technical jargon. It never claims to modify the customer's website; it prepares recommendations for review.

## Core user journey
1. **Register / Login** — email + password with OTP verification, Google sign-in, forgot/reset password.
2. **Onboarding** — business name + website URL, plus up to 3 optional competitor websites; a project and scan job are created and the scan starts automatically.
3. **Live scan** — a real crawler fetches up to 25 pages of the actual website (following internal links) and checks titles, meta descriptions, canonical tags, broken pages (404s), and thin content on important pages.
4. **Competitor comparison (NEW)** — if competitor URLs were added, each competitor site is crawled (up to 10 pages) and scored on: service pages, search-title quality, search-description coverage, content depth, FAQ usage, trust signals (schema), and broken pages. Plain-English insights are generated when competitors look stronger.
5. **Scan complete screen** — pages scanned, improvements found, three counts (Prepared for you / Needs your approval / Needs a developer), and top recommended actions.
6. **Fix List** — issues grouped into the three buckets, with detail views (what's happening, why it matters, current vs. recommended, approve/reject/complete).
7. **Competitors page (NEW)** — comparison summary, "Your Site vs. Competitor Average" table with friendly labels, top competitor gaps with recommended actions, and a "Create improvement plan" button that adds the gaps to the developer recommendations (no duplicates).
8. **Developer page** — recommendations requiring developer work, categorized, with suggested packages (DIY / $500 Cleanup / Custom Quote).
9. **Reports** — client-friendly summary reports with score, counts, and next steps.
10. **Scan history** — past scans with date, pages scanned, improvements found, and health score.

## Lead capture (NEW)
- "Join Waitlist", "Request Cleanup", and "Contact Us" on the pricing page open a simple modal (name, email, website URL, message), prefilled from the logged-in user's account and project.
- Requests are saved as LeadRequest records with the success message: "Thanks — we received your request and will follow up soon."
- Admins manage all leads in a new "Lead Requests" tab (status: new / contacted / closed).

## Trust & language
- All customer-facing wording says "prepared fixes" / "recommended improvements" — never "auto-fixed."
- Competitor comparison avoids technical labels (no "canonical", "schema", "indexation") — uses "Trust signals for Google", "Helpful page content", etc.
- A disclosure note explains the scan checks accessible HTML.

## Security
- All 11 data types (projects, scans, pages, issues, recommendations, competitors, competitor insights, redirects, metadata, reports, lead requests) are locked to their owner.
- Public visitors cannot read private records; one user cannot see another's data; admins retain full access.

## Billing status
- Pricing page shows all tiers with a "Plans are coming soon" banner.
- No payment processing connected yet (Stripe not connected — deliberate).

## Known limitations / not built yet
- No JavaScript rendering in the crawler (HTML-only analysis).
- No actual website editing — everything is a recommendation.
- No payments, no PDF export of reports.
- No Google Search Console integration.
- Customer FAQ/trust-signal detection is not shown in the comparison table (only competitor usage is shown).