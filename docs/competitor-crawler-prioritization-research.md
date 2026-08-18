# Competitor Crawler Prioritization Research

Purpose: inform FixList repair prioritization without changing the Standard 150 crawler architecture.

Research date: 2026-08-18
Primary-source bias: vendor documentation/product documentation where available.

## Core comparison

### Sitebulb

Observed model:

- inherent Hint priority/importance
- affected URL count
- Coverage relative to URLs eligible for the Hint
- indexable vs non-indexable affected URLs
- template/page-pattern reporting

FixList implication:

- do not use all crawled pages as the denominator for every issue
- separate technical severity from site-specific action priority
- indexability must modify search-facing repair urgency
- use page-family evidence for pattern grouping, but do not infer common implementation cause from family alone

Official references:

- https://support.sitebulb.com/en/articles/9854034-about-sitebulb-hints
- https://sitebulb.com/hints/

### Semrush Site Audit

Observed model:

- Error / Warning / Notice severity
- Top Issues consider priority and number of affected pages
- analytics/pageview context can help choose which affected pages to address first
- issue-level drill-down to affected pages

FixList implication:

- breadth matters but cannot be the only ordering dimension
- page importance can be a contextual modifier
- keep issue severity separate from final work-queue ordering

Official reference:

- https://www.semrush.com/kb/1184-audit-your-website

### Ahrefs Site Audit

Observed model:

- Error / Warning / Notice issue importance
- Top Issues and affected URL counts support prioritization
- issue importance can be customized/disabled because the same generic severity does not fit every project
- crawl comparisons expose new/lost/fixed issue behavior

FixList implication:

- base severity should remain a technical taxonomy, not the complete customer priority decision
- rescan state must be explicit and evidence-backed

Official references:

- https://ahrefs.com/academy/how-to-use-ahrefs/site-audit/introduction
- https://help.ahrefs.com/en/articles/1424673-what-is-health-score-and-how-is-it-calculated-in-ahrefs-site-audit

### Screaming Frog SEO Spider

Observed model:

- High / Medium / Low priorities represent estimated potential impact
- counts and percentages help scope issues
- the tool explicitly avoids pretending generic priority is a complete strategy

FixList implication:

- customer action priority should be contextual and explainable
- retain confidence/evidence language for inferred improvements

Official references:

- https://www.screamingfrog.co.uk/seo-spider/issues/
- https://www.screamingfrog.co.uk/seo-spider/user-guide/tabs/

### Conductor Monitoring (formerly ContentKing)

Observed model:

- Website Health is affected by Issues
- issue impact is based on both the number of affected pages and the Importance of those pages
- issues are ordered by their impact on Website Health
- issue configuration can define whether certain checks apply to indexable pages or all pages
- continuous monitoring supports rapid regression detection

FixList implication:

- affected-page importance distribution is a first-class ranking signal
- issue eligibility must be rule-specific
- page importance should be evaluated across the group, not from a single representative page

Official references:

- https://support.conductor.com/health-score
- https://support.conductor.com/en_US/monitoring-setup/issue-configuration

### Lumar

Observed model:

- traffic-funnel categories: Availability, Indexability, Discoverability, Rankability, Experience
- Health Scores start at 100 and deduct weighted error reports
- each report has a weight; category weight is derived from issue report weights
- users can adjust report weighting
- the most impactful Health Score Errors are shown first
- some dimensions can incorporate Search Console/Analytics/log/sitemap context

FixList implication:

- use technical severity floors plus contextual modifiers rather than one raw occurrence count
- category/family organization is useful for orientation, but the customer queue should still be task-first
- future external performance signals can be optional enrichments; they are not required for the current architecture

Official reference:

- https://help.lumar.io/hc/en-us/articles/23471295820433-Health-Scores-for-SEO

### Botify

Observed model:

- ActionBoard is a prioritization/scoring layer above crawl evidence
- URL-level SEO score reflects detected issues and estimated traffic impact
- category scores include crawlability, content and linking
- SiteCrawler combines crawl analysis with server logs, Search Console and analytics where configured
- strategic/indexable pages can be evaluated against actual search-engine crawling and organic traffic

FixList implication:

- confirms the architectural direction: keep crawling deterministic, put business-impact prioritization in a synthesis layer above it
- external traffic/search/log context is valuable but optional future enrichment, not a reason to rebuild Standard 150

Official references:

- https://support.botify.com/en/articles/15656352-actionboard-fields
- https://support.botify.com/en/articles/9108646-sitecrawler-overview
- https://support.botify.com/en/articles/9108648-understanding-sitecrawler-reports

### JetOctopus

Observed 2026 model:

- AI SEO Recommender reads crawl, Search Console and server-log evidence
- produces a short ranked list in plain language
- every recommendation includes what is wrong, what to do, scale and direct drill-down to evidence
- can sort by number of pages (breadth) or Search Console impressions (visibility impact)
- explicitly demonstrates that a 40,000-page low-impression problem and a 200-page high-impression problem can deserve different rankings
- treats AI recommendations as leads to verify, not unquestionable truth

FixList implication:

- breadth and impact should remain separate dimensions
- customer-facing recommendation must remain inspectable down to underlying evidence
- FixList can implement a crawl-only version now using page importance/indexability/coverage, with optional performance enrichment later

Official reference:

- https://jetoctopus.com/meet-the-ai-seo-recommender/

### Oncrawl

Observed 2026 model:

- Lenses organize analysis around user goals rather than one giant universal report
- Content Lens provides multiple quality dimensions and recommended actions
- Sanity Check emphasizes business-critical pages
- Crawl-over-crawl analysis compares technical states
- alerts support thresholds and ratio-based conditions to reduce noise

FixList implication:

- keep one simple customer queue while allowing secondary work-area/page views
- regression/verification should compare state across crawls
- threshold/ratio concepts support relevant-coverage reasoning better than raw issue counts alone

Official references:

- https://help.oncrawl.com/en/articles/12495943-oncrawl-lenses
- https://help.oncrawl.com/en/articles/6984784-how-to-use-alerts-for-seo-monitoring-in-oncrawl

### Ryte

Observed model:

- issue reports are listed by priority
- issues are separated into critical/warning/informational-style levels and topic areas
- integrations can combine technical issue context with ranking/search-performance data
- GSC metrics such as clicks, impressions, CTR and position can be shown with crawl data to prioritize optimization

FixList implication:

- optional search-performance context can eventually improve page importance
- current crawl-only prioritization should be designed so future evidence enriches the contract rather than replacing it

Official references:

- https://en.ryte.com/product-insights/issue-reports/
- https://en.ryte.com/product-insights/ses-wes-integration/
- https://en.ryte.com/product-insights/gsc-data-in-reports/

## Cross-tool conclusions

### High-confidence

1. Severity alone is not enough.
2. Raw affected-page count alone is not enough.
3. Page importance matters.
4. Indexability/eligibility matters for many search-facing checks.
5. Crawl-over-crawl verification is a distinct product capability from initial diagnosis.
6. The strongest products preserve drill-down from summary/recommendation to underlying URL evidence.
7. Enterprise tools increasingly enrich crawl evidence with search traffic, log or analytics data, but that enrichment sits above the crawl itself.

### FixList-specific opportunity

Standard 150 already has enough evidence to build a better crawl-only priority layer without architecture changes:

- deterministic technical rule
- page family/type
- indexability
- affected URLs
- important/business-page heuristics
- evidence confidence
- scope
- representative pages
- crawl/sample coverage metadata

Use those signals to produce a canonical customer action queue now. Treat GSC/analytics/log/keyword performance as a later optional enrichment, never a prerequisite for a valid scan.

## Recommended canonical mental model

`Base technical severity`
+
`Evidence class`
+
`Relevant sample-qualified coverage`
+
`Affected-page importance distribution`
+
`Indexability where relevant`
+
`Confirmed repair leverage`
+
`Dependencies`
=
`Customer action priority + one plain-language reason`

Do not expose the formula. Expose the reason.
