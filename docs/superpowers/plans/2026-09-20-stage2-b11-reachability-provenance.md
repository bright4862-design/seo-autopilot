# Stage 2 B11 reachability provenance checkpoint — 2026-09-20

Branch: `agent/full-blueprint-stage2-coverage-b06-20260919`

PR: #303

Spec authority: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`, B11 — calculate observed depth/inlinks/navigation presence for classified money pages; retain sample scope and distinguish an observed weak route from proof of sitewide orphaning.

## Implemented in this serialized slice

### Producer adapter

New module: `scanner-api/app/stage2_reachability_provenance.py`.

- Version: `money_page_reachability_provenance_v1`.
- Scope: `observed_standard150_sample_only`.
- Retains internal-link source identity separately from existing mixed discovery provenance; sitemap discovery is never promoted to an inlink.
- Computes shortest **observed accepted-HTML** path from the exact submitted seed; sitemap-only pages keep depth unknown.
- Challenged/failed/incomplete source pages cannot become verified inlink/navigation evidence, including when malformed producer input tries to insert them.
- Preserves exact request URL spelling/query/case/reserved escapes in evidence identity.
- Enrichment is in-place on retained assessed pages and asserts that page count/order is unchanged.
- Every enriched page explicitly carries `sitewide_orphan_claim=false`; the adapter has no sitewide-orphan capability.

### Consumer contract hardening

`scanner-api/app/stage2_coverage_evidence.py::money_page_reachability` now accepts only the exact B11 provenance version/scope. Legacy `source_pages` is not interpreted as an internal inlink, so `/sitemap.xml` cannot become reachability evidence. A pass requires known inlink count, observed depth and navigation state. Partial evidence remains `not_verified`; verified weak signals are described only as `weak_route_in_observed_sample`.

### Semantic raw-link context

`scanner-api/app/extract.py` now marks a raw link `navigation_presence=true` only when its anchor is under a semantic `<nav>` ancestor or an ancestor with `role="navigation"`. CSS class names such as `menu` and footer placement alone are not treated as navigation proof. Link URL identity still removes only fragments while retaining path case, raw query order and reserved escapes.

The existing Stage-1 link-observation regression was strengthened, not removed: it still requires exact href/text and now also asserts the new explicit `navigation_presence=false` field for a content link.

## Behavioral regressions added

- `scanner-api/tests/test_stage2_reachability_provenance.py` — 6 cases:
  - semantic navigation link → observed inlink/depth/navigation evidence;
  - sitemap-only page → zero observed inlinks but unknown depth/navigation, never sitewide orphan;
  - content-only internal link → navigation false, sample scope retained;
  - challenged/unusable source cannot become verified evidence;
  - shortest observed depth is independent of discovery/fetch order;
  - unaccepted target receives no invented zero/depth/navigation claim.
- `scanner-api/tests/test_stage2_navigation_link_context.py` — 2 cases:
  - semantic `<nav>` / `role=navigation` only;
  - exact path/query/case/reserved-escape request identity.
- `scanner-api/tests/test_stage2_coverage_evidence.py` adds legacy-sitemap rejection and partial-evidence fail-closed cases.

## Verification history

Exact code head `1f27022583b3777cfe886632cff3b7db19140334` passed FixList CI `35475369510` on both jobs before semantic link context was added. It included the producer adapter, hardened B11 consumer and the first B11 regressions.

Exact head `0b657afad65bf6c9aef883de11fd23093c6a1f90` then exposed one compatibility regression in FixList CI `35475547130`: the existing Stage-1 link-observation test expected only `{href,text}` while the raw-link record now intentionally also carries `navigation_presence`. All new B11 focused tests passed in that failing run; the full scanner-api result was **1 failed, 1,920 passed, 18 skipped**, and root scanner regressions were **115 passed**. The compatibility test was updated to assert the enriched shape rather than weakened or removed.

Current executable head after that correction: `c26a0495162359a6af72de0371ea33207e6df505`.

FixList CI for this current head: `35475725233` — in progress at the time this checkpoint was written. Do not call the head CI-certified until that run completes successfully.

## Independent review

A focused CodeRabbit review was requested on PR #303 for the B11 seam, specifically sample-scoped truthfulness, sitemap/inlink separation, exact identity, challenged/unusable fail-closed handling, semantic navigation evidence, privacy and compatibility. Review completion remains a gate; a request alone is not a review pass.

## Still required before B11 is source-complete

The current branch has the producer adapter, consumer contract and semantic link evidence, but shared `run_scan` has not yet connected the observed internal-link graph into `enrich_pages_with_reachability_provenance` after the final Standard-150 page cap. The serialized integrator must perform that shared hook without changing scheduler/request budgets or assessed-page counts, then expose only authenticated B11 evidence through any downstream Review/authority/customer path that actually uses it.

Required shared-hook invariants:

1. exact source request URL, not only a relative path, identifies an observed internal edge;
2. semantic `navigation_presence` comes from the accepted source page's raw-link evidence;
3. `page_has_usable_html(source)` gates verified source edges; challenged/failed/incomplete sources may be crawl-discovery inputs but not B11 evidence;
4. sitemap discovery never creates an inlink or depth;
5. enrichment occurs only after the final retained assessed-page cap and never adds probe URLs;
6. weak observed routing must remain sample-scoped and must never become a sitewide orphan claim;
7. if B11 evidence/counts become customer-visible, add the real producer → Review → signed authority → persisted rows → verified card/handoff/export chain before closing B11.

No production, deployment, admission, worker, schema, secret or customer-data state was changed by this slice.
