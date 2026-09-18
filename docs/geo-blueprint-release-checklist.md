# GEO and scanner blueprint release checklist

Status: GEO integration and blueprint P0 corrections implemented and independently task-reviewed; combined release gates in progress. No production activation is claimed. See geo-release-acceptance.md.

Source: user-uploaded **FixList Scanner Gap Analysis & Blueprint**, 18 September 2026, 18 pages. The reattached `(1)` copy is byte-identical (SHA256 `c76efed66f373e2455c326b2804a8148489509f8625f84377b9f21bef4f1f6f9`). Reported site counts are hypotheses for fixture construction, not independently reproduced live results.

## Immediate release gates

| Requirement | Evidence at start of integration | Acceptance needed |
| --- | --- | --- |
| Fetch published slash/path/host | All enqueue sources preserve published request identity; sitemap host/scheme rewriting removed (15cd1ef6) | Mock server proves published /x/ returns 200 without a synthetic /x request, while a published /x redirect is retained; provenance distinguishes identity/request/final |
| Empty vs absent image alt | extract.py counts only absent attributes; empty and whitespace attributes are not missing (15cd1ef6) | Decorative alt="" causes no missing-attribute repair or score penalty; absent attribute remains detectable; content applicability cannot be inferred solely from main/article placement |
| Challenged HTML exclusion | Existing vendor evidence gate detects SiteGround/Cloudflare | GEO receives no real-site noindex/metadata findings or numeric score from challenged, denied or incomplete HTML |
| General visible templates | Existing SEO location detector retained; GEO adapter covers bounded visible token syntax, with real-rule action matching | {{year}} and #location# in actual content are detected; script/code examples excluded; placement retained |
| Search-facing scope | Existing noindex and canonical evidence available | Explicit utility exclusions and sitemap/noindex conflicts distinguished; no blanket suppression of accessibility defects |
| Honest counts and priority | Existing repair invariants and calibration require fixture review | Unique evidence-backed affected-page counts; truncation disclosed; decorative alt cannot outrank broken critical content |
| Historical authority | Historical v1–v6 byte/HMAC fixtures pass; GEO uses an internal snapshot marker with public V6 routes | Older seals still verify; GEO covered by new internal snapshot revision; tampered score/coverage/evidence rejected |
| Customer evidence access | Sealed eight-field preview summary and verified full projection; UI/export no-leak regressions pass | No hidden findings or full evidence leaked through GEO; null never becomes zero; valid zero remains zero |
| Release identity | Production baseline source b5bce859 / fingerprint 9e4901da590017e1 | Candidate fingerprint 47793ce37ca20523; exact-SHA CI, Base44/worker source agreement, rollback and runtime acceptance remain required |

## Remaining blueprint coverage

These items stay visible as follow-on scanner work. They are not silently claimed by the GEO score and are not a reason to invent results from uncollected evidence.

| Blueprint item | Boundary for this release |
| --- | --- |
| Every same-site target / sibling host | Additional target checks need an explicit bounded budget and existing SSRF/domain rules; no unlimited crawl or automatic sibling-host expansion |
| Soft-404 probes / URL variants | Requires synthetic requests; outside the first GEO release's no-new-requests contract |
| Redirect destination sanity | Reuse actual redirect traces where present; do not infer that any redirect to home is broken |
| Sitemap integrity | Reuse existing fetched sitemap evidence; challenged sitemap means not verified, not real-site noindex |
| Near-duplicate clusters | Needs main-content extraction and labelled calibration; template similarity alone does not prove duplication harm |
| Money-page reachability | Sampled graph only; low observed inlinks do not prove sitewide orphaning |
| Raw/rendered link comparison | Requires retained paired evidence; no extra rendering budget added for GEO |
| Local completeness / cross-page consistency | Explicit entity applicability and provenance needed; optional holiday hours or sameAs not universal defects |
| Page weight / CrUX | Transfer/decoded/script bytes must stay distinct; HTML size is not a Core Web Vitals measurement |
| Freshness | An old year alone is not stale; requires current-content intent and contradictory date context |
| Impact × reach × value × confidence | Product calibration proposal, not validated ranking formula; preserve confidence and exact counts independently |
| Root-cause handoff / vendor ownership | Share one action across SEO/GEO; retain evidence, verification and owner distinctions |
| Own-site metadata/sitemap/soft 404 | Requires separate reproduced site-serving defects and hosted rendering fixes; do not assume PDF claims match current deployment |
| Pricing and market claims | Outside GEO/scanner scope; no pricing edits based on unverified comparison table |
| Chrome/Googlebot identity | Excluded by explicit user boundary; keep transparent FixList identity |
| Missing-check score cap | GEO uses a separate coverage gate and unresolved-outcome range, not an invented observed-defect penalty |

## Fixture corpus

Use deterministic local fixtures for Pretto-like visible year tokens and published slash URLs; Center Street-like template placeholders and verified dead links; Ike's-like utility noindex/sitemap conflicts and location shells; getfixlist-like duplicate raw titles and limited evidence; and Ironwood-like SiteGround challenges. Label fixtures as synthetic when they are not archived live responses. A passing synthetic fixture does not establish a live site's present condition.

## Ironwood

Reported successful diagnostic run 35397753613 attempt 2 returned HTTP 202 and `sg-captcha: challenge` for all six root/robots/sitemap requests across both transparent user agents. It did not verify production egress-IP equivalence. No IP/header/cadence/TLS trigger has been isolated. GEO cannot clear access protection. Approved site-admin/SiteGround access configuration and actual-worker verification remain the next access steps.
