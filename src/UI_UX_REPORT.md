# SEO Autopilot — Current Layout, UX & UI Report
**Date:** July 5, 2026

## Design system
- **Style:** Clean, modern SaaS. Light theme, white cards on a soft blue-gray background (`#F7F9FB`-range).
- **Font:** Inter (all weights 300–900), used for headings, body, and display text.
- **Primary color:** Blue (#3B82F6-range), with a signature blue → indigo gradient used on primary buttons, logos, and hero elements.
- **Accents:** Green = done/prepared, Amber = needs approval, Purple = needs developer, Red = errors/critical.
- **Shape language:** Rounded corners everywhere (0.75rem radius, `rounded-xl`/`rounded-2xl` cards), pill-shaped badges, soft subtle shadows, 1px light-gray borders on cards.
- **Components:** shadcn/ui (buttons, inputs, labels, tabs, selects, dialogs) + lucide-react icons.

## Global layout

### Public pages (Landing, Login, Register, Forgot/Reset Password)
- Centered single-card layout on a blue→white→indigo gradient background.
- Small brand header: gradient square logo with a lightning bolt (Zap) icon + "SEO Autopilot" wordmark.
- Auth pages: email/password forms, Google sign-in button, OTP verification step on register, inline error messages, disabled buttons while submitting.

### Onboarding (post-signup)
- Full-screen gradient background, brand logo top-left.
- One centered white card (max-w-md) with:
  - Gradient icon tile (Search icon) + heading "Let's scan your website"
  - Business name input (with building icon)
  - Website URL input (with globe icon)
  - 3 optional "Competitor website" inputs
  - Full-width gradient CTA: "Scan My Website"
- Submitting creates the project and navigates straight into the live scan.

### Dashboard shell (all app pages)
- **Left sidebar** (white, collapsible on mobile with overlay):
  - Brand logo + name at top
  - Nav items with icons: Fix List, New Scan, Competitors, Developer, Reports, Assistant
  - Bottom section: Billing, Admin (admins), Logout
  - Active item highlighted with blue accent background
- **Top header** (sticky): hamburger menu on mobile, user avatar/name on the right.
- **Main content area:** max-width container, page title + subtitle at top-left, primary action button top-right, content in stacked white rounded cards.

## Key pages

### Fix List (dashboard home)
- Header: "Fix List" + "Run New Scan" button.
- 3 summary stat cards in a row: **Prepared for you** (green), **Needs your approval** (amber), **Needs a developer** (purple) — each with count and icon.
- Below: issues grouped into the 3 buckets as card sections; each issue row shows title, page URL, priority badge, and opens a **detail modal** with: plain-English explanation, "why it matters", current vs. recommended value side-by-side, AI recommendation, and Approve / Reject / Mark complete buttons.
- Scan history table at the bottom (date, pages, improvements, health score).

### New Scan / Crawl Status
- Vertical step timeline (10 steps: Queued → Crawling → … → Complete) with icons; completed = green check, current = blue spinner, pending = gray circle.
- Blue info note: scan checks accessible HTML.
- On completion: success card with green check, "We scanned X pages and found Y recommended improvements", 3 count tiles, "Top recommended actions" numbered list, and "View Fix List" CTA.

### Competitors
- "How your website compares" summary.
- Comparison table: **Your Site vs. Competitor Average** with friendly labels only (Pages scanned, Service pages, Clear search titles, Search descriptions, Helpful page content, FAQs, Trust signals, Broken pages).
- "Top competitor gaps" cards: insight title, plain-English explanation, recommended action, impact badge (high/medium/low).
- "Create improvement plan" button → adds gaps to developer recommendations.

### Developer
- 3 package summary cards: DIY (green), $500 Cleanup (blue), Custom Quote (purple) with counts.
- Recommendations grouped by category (Quick Fixes, Technical SEO, Content Pages, Speed & Mobile, …), each with priority badge, description, blue "Why this matters for your business" callout, and complexity/package chips.
- "Request Done-for-You Help" CTA.

### Reports
- List of generated report cards: executive summary, score, fixed/approval/developer counts, competitor summary, next steps. "Generate Report" button.

### Billing
- "Plans are coming soon" banner.
- Pricing grid of plan cards (Free scan, DIY, Growth, Done-for-You, Rebuild) with feature lists; actions open lead-capture modals (Join Waitlist / Request Cleanup / Contact Us) prefilled with the user's info; success state: "Thanks — we received your request."

### Admin (admins only)
- Tabs including **Lead Requests**: table of leads with status management (new / contacted / closed).

### Assistant
- Chat interface with the SEO assistant agent: message bubbles (user right, assistant left with markdown), tool activity indicators.

## UX principles applied
- Plain-English, business-owner language everywhere; no technical jargon (no "canonical", "schema", "indexation" in customer-facing UI).
- Honest language: "prepared" / "recommended" — never claims the site was modified.
- Loading spinners on all async operations; empty states with icon + guidance + CTA on every page.
- Fully responsive: sidebar collapses to overlay drawer on mobile; grids stack to single column.