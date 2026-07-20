# Canonical alias and sitemap crawl-reserve candidate

## Scope

This candidate closes two evidence-integrity problems found in the 18-site Phase 1 production corpus and the PR #88 regression run:

1. A page requested on the apex host, resolved on `www`, and canonically declared on that same final `www` URL could be reported as a cross-domain canonical.
2. Sitemap discovery shared the full backend deadline with page crawling and could consume nearly all available time before workers began fetching pages.

The candidate fingerprint is `a4dfc1840ce07706`.

## Canonical identity contract

A canonical declaration is treated as `origin_alias_equivalent` only when the requested and canonical identities satisfy all of these conditions:

- the hosts differ only by a leading `www.`;
- the scheme is unchanged;
- the effective port is unchanged;
- the normalized path is identical;
- the query string is identical;
- the canonical matches the final public page identity.

The alias remains observable through canonical-target evidence but does not generate `canonical_cross_domain`, `canonical_loop`, or another customer-facing canonical finding.

The following remain reviewable findings or normal canonical-target checks:

- a genuinely different registrable domain;
- an HTTP-to-HTTPS change;
- a path-changing canonical;
- a query-changing canonical;
- a canonical target that redirects, fails, is noindexed, or is robots-blocked;
- canonical chains and loops.

## Sitemap crawl-reserve contract

Sitemap discovery now receives an internal deadline earlier than the global scan deadline. By default, it reserves 40% of the remaining backend budget for page crawling, bounded to a minimum of 8 seconds and a maximum of 30 seconds.

This does not change:

- the 150-page advanced hard cap;
- balanced sitemap sampling;
- crawl concurrency;
- Python Review scoring;
- fallback policy;
- access-limitation handling.

The existing crawl-scope evidence now records:

- `sitemap_discovery_version`;
- `sitemap_fetch_limit`;
- `sitemap_crawl_reserve_seconds`;
- `sitemap_discovery_elapsed_ms`;
- `sitemap_fetches_attempted`;
- `sitemap_root_count`;
- `sitemap_child_count`;
- `sitemap_urls_discovered`;
- `sitemap_deadline_reached`;
- `sitemap_stopped_for_crawl_reserve`.

These fields distinguish sitemap exhaustion, global deadline exhaustion, empty discovery, and page-fetch failures.

## Automated validation

Regression coverage asserts that:

- the exact Hartzler shape—requested apex URL, final `www` URL, and matching `www` canonical—creates no canonical finding;
- a genuine external canonical remains `canonical_cross_domain`;
- scheme, path, and query changes are not hidden as transport aliases;
- sitemap discovery reserves the configured portion of the global deadline;
- sitemap timing and queue diagnostics are written into crawl-scope evidence;
- the frozen revision, health endpoints, durable model, and frontend authority gate agree on the candidate fingerprint.

## Production acceptance after merge and synchronized deployment

Run only these Full Site regressions:

1. **Hartzler Dairy**
   - all retained page evidence is HTML;
   - `/chocolate-milk` does not produce `canonical_cross_domain` or `canonical_loop` solely because of apex/`www` identity;
   - persisted scan and FixList remain authoritative when otherwise complete.

2. **IKEA France**
   - crawl-scope evidence contains the sitemap-reserve diagnostics;
   - sitemap discovery cannot consume the entire backend deadline;
   - at least the seed or selected page queue begins crawling unless access itself is blocked.

3. **Nordic Nest**
   - crawl-scope evidence contains the sitemap-reserve diagnostics;
   - the result distinguishes deadline starvation from page-fetch or access failures;
   - page retention materially improves beyond the prior five-page outcome when the site permits access.

4. **Funbooker**
   - the known-good control reaches 150 pages;
   - Python scanner and Python Review are used without fallback;
   - the persisted ScanRun and FixList remain authoritative.

## Out of scope

This candidate does not address Shopify pacing, classifier calibration, weak-discovery authority, grouped recommendation presentation fields, or the browser/local debug-export merge bug.
