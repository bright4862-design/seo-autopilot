# Stage 2 B11 reachability provenance checkpoint — 2026-09-20

Branch: `agent/full-blueprint-stage2-coverage-b06-20260919`

PR: #303

Spec authority: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`, B11 — calculate observed depth/inlinks/navigation presence for classified money pages; retain sample scope and distinguish an observed weak route from proof of sitewide orphaning.

## Implemented in this serialized slice

### Producer adapter

Module: `scanner-api/app/stage2_reachability_provenance.py`.

- Version: `money_page_reachability_provenance_v1`.
- Scope: `observed_standard150_sample_only`.
- Retains internal-link source identity separately from existing mixed discovery provenance; sitemap discovery is never promoted to an inlink.
- Computes shortest **observed accepted-HTML** path from the exact submitted seed; sitemap-only pages keep depth unknown.
- Challenged/failed/incomplete source pages cannot become verified inlink/navigation evidence, including when malformed producer input tries to insert them.
- Preserves exact request URL spelling/query/case/reserved escapes in evidence identity.
- Enrichment is in-place on retained assessed pages and asserts that page count/order is unchanged.
- Every enriched page explicitly carries `sitewide_orphan_claim=false`; the adapter has no sitewide-orphan capability.

### Shared producer hook — now implemented

The previously open shared hook is now wired without changing `run_scan` request budgets or the Standard-150 assessed-page set:

- `scanner-api/app/extract.py` retains a bounded private `_reachability_links` cache only for accepted `usable_html` source pages. It stores only exact target URL identity and semantic navigation state; link text is deliberately not duplicated into the private B11 cache.
- `scanner-api/app/content_evidence_findings.py` invokes `enrich_pages_from_retained_link_evidence()` when `scanner.build_findings()` runs **after the final retained-page cap**. The same function may run again in Review, but the private cache has already been removed so enrichment is not repeated from hidden state.
- `enrich_pages_from_retained_link_evidence()` constructs the graph only across exact request URLs that remain in the retained assessed-page set. Unsampled/out-of-retained-set targets never expand `pages` and never enter B11 denominators.
- Source pages are re-gated with the final accepted-page evidence class before an edge becomes verified, so challenged/failed/incomplete sources cannot contribute even if malformed private cache input is injected.
- The exact seed is recovered only from retained page discovery carrying `seed`; sitemap discovery never creates an edge or depth.
- A `finally` cleanup removes `_reachability_links` from every page before the scan result can be returned, signed, persisted or projected to customers.
- The hook performs no network I/O and creates no scheduler or follow-up request budget.

### Consumer contract hardening

`scanner-api/app/stage2_coverage_evidence.py::money_page_reachability` accepts only the exact B11 provenance version/scope. Legacy `source_pages` is not interpreted as an internal inlink, so `/sitemap.xml` cannot become reachability evidence. A pass requires known inlink count, observed depth and navigation state. Partial evidence remains `not_verified`; verified weak signals are described only as `weak_route_in_observed_sample`.

### Semantic raw-link context

`scanner-api/app/extract.py` marks a raw link `navigation_presence=true` only when its anchor is under a semantic `<nav>` ancestor or an ancestor with `role="navigation"`. CSS class names such as `menu` and footer placement alone are not treated as navigation proof. Link URL identity still removes only fragments while retaining path case, raw query order and reserved escapes.

The existing Stage-1 link-observation regression was strengthened, not removed: it still requires exact href/text and now also asserts the new explicit `navigation_presence=false` field for a content link.

## Behavioral regressions

Existing B11 regressions:

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
- `scanner-api/tests/test_stage2_coverage_evidence.py` includes legacy-sitemap rejection and partial-evidence fail-closed cases.

New retained-set/shared-hook regression file:

- `scanner-api/tests/test_stage2_reachability_run_scan_seam.py` — 3 cases:
  - exact seed navigation edge is projected after final retained-page selection, with exact URL/query/escape identity and private cache removal;
  - an outgoing link to an unsampled target cannot expand assessed pages or invent a broader population/denominator;
  - an unusable/challenged source cannot contribute even when a malformed private cache is injected, and private cache cleanup is unconditional.

## Verification history

Exact code head `1f27022583b3777cfe886632cff3b7db19140334` passed FixList CI `35475369510` on both jobs before semantic link context was added.

Exact head `0b657afad65bf6c9aef883de11fd23093c6a1f90` then exposed one compatibility regression in FixList CI `35475547130`: the existing Stage-1 link-observation test expected only `{href,text}` while the raw-link record now intentionally also carries `navigation_presence`. All new B11 focused tests passed in that failing run; the full scanner-api result was **1 failed, 1,920 passed, 18 skipped**, and root scanner regressions were **115 passed**. The compatibility test was updated to assert the enriched shape rather than weakened or removed.

Exact executable head after that correction: `c26a0495162359a6af72de0371ea33207e6df505`.

FixList CI `35475725233` passed both jobs on that exact head with **115 root tests** and **1,921 scanner-api passed / 18 intentional skips**.

### Retained-link producer-hook checkpoint

Exact executable head: `f51869adf8eac44de4fa7c9387590ab3c330c5a9`.

FixList CI `35478073142` — **SUCCESS** on both jobs for that exact head:

- immutable checkout verified `f51869adf8eac44de4fa7c9387590ab3c330c5a9`;
- root scanner regressions: **115 passed**;
- scanner-api: **1,924 passed / 18 intentional skips**;
- new `test_stage2_reachability_run_scan_seam.py`: **3 passed**;
- existing B11 navigation/provenance suites remained green;
- labelled Stage-1 corpus remained `synthetic`, **14 cases / 55 assertions**, `full_30_site_gate=not_assessed`;
- frozen scanner revision `01ebe8e90df1e6bd`: passed;
- production scanner image: passed, image SHA `sha256:7dc32951eaf6b600424b9e1fde302a9300ae90b333f813e4ac1156fe1bb3ff72`;
- lint, typecheck, generated release contracts, frontend contract tests and production frontend build: passed.

The workflow resolved Node `20.20.2`; this run is not evidence for an exact Node `20.19.5` runtime.

## Independent review

A prior focused CodeRabbit review reported **no correctness defect** in the semantic-link checkpoint and independently confirmed semantic-only navigation evidence, exact URL identity preservation, sitemap/inlink separation, exclusion of challenged/failed/truncated sources, and `sitewide_orphan_claim=false`.

The retained-link producer hook landed after that review. A fresh incremental review is required for the new exact-head hook before B11 can be called independently reviewed. Review focus should include: final-retained-set timing, private cache cleanup/privacy, exact URL identity, accepted-source re-gating, no assessed-page expansion and no new request budget.

## Requirement status

**B11 producer/source wiring is now implemented and exact-head CI green, but B11 is not yet independently review-complete.** No customer-facing B11 repair/card is introduced by this slice. The new page-level provenance fields may be consumed by later Stage-3 decision work only after Stage 2 closes; any future persistence/preview/export of source URL samples must remain bounded, authenticated and entitlement/privacy-safe.

No production, deployment, admission, worker, schema, secret or customer-data state was changed by this slice.

## Exact next action

Request/resolve independent review of `f51869ad...`. If no material B11 defect is found, move the serialized Stage-2 implementation to **B12 paired raw/rendered hub-link evidence**, preserving explicit completed/failed/unassessed states and keeping raw and rendered evidence as separate observations rather than treating either as sole truth.