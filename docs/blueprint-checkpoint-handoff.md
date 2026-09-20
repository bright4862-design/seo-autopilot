# Blueprint implementation checkpoint

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`.

This is the current serialized handoff for the FixList full-scanner blueprint. Historical checkpoints remain in Git history and the linked executable plans. Earlier approval-blocker language is resolved and must not be treated as current authority.

## Release boundary

Stage 1 and the later blueprint are deliberately separate release states.

- Stage-1 production publication/promotion/live non-owner acceptance remains owned by the existing exact-source release operator.
- Do not use this later-stage integration branch to publish, promote worker traffic, mutate admission, run a competing production scan, change schemas/secrets, or otherwise move production.
- Later-stage integration stays on `agent/full-blueprint-stage2-coverage-b06-20260919`, PR #303.
- Once Stage-1 live acceptance is recorded, reconcile the integration branch onto the then-current accepted `main` without reverting V7 route/public-build changes or the durable ownership-before-admission fix, then run fresh exact-head combined CI.

## Current integration branch

Branch: `agent/full-blueprint-stage2-coverage-b06-20260919`

PR: #303 — `Stage 2: integrate B06–B18 evidence lanes and finish shared producer wiring`

### Current B12 checkpoint — paired hub-link evidence seam is green, shared caller disclosure still open

Exact executable head: `e3155ae722631189f338f7bd76225a5e35950bf5`.

FixList CI `35480882511` — **SUCCESS** on both jobs. Immutable checkout, root scanner regressions, the full scanner-api suite, the labelled synthetic Stage-1 corpus, frozen scanner revision verification, production scanner-image build, lint, typecheck, generated release contracts, frontend contract tests and production frontend build all passed. The slice adds seven focused B12 behavioral regressions.

Implemented B12 behavior:

- `scanner-api/app/stage2_hub_render_evidence.py` selects at most five verified structural hubs from the retained Standard-150 set and separately records the exact eligible count plus whether selection was truncated.
- Raw link evidence is reconstructed only from B11 retained assessed-page provenance. If B11 source samples are truncated such that raw-link absence cannot be proven, the hub fails closed instead of producing a false raw/render difference.
- Rendered links are accepted only from an explicit renderer link collection, resolved against the hub, fragment-stripped, and intersected with the exact retained assessed URL set. Unsampled targets never become assessed pages.
- Exact path/query/case/reserved-escape identity is preserved. An explicit empty query delimiter is restored after URL resolution so `/page` and `/page?` are not silently collapsed.
- An absent rendered link collection is `failed`/unavailable rather than an empty success. Renderer exceptions remain visible only in the pre-existing browser-followup diagnostic field; the new B12 evidence records the normalized `renderer_failed` reason and does not duplicate raw exception text.
- `scanner-api/app/render_followup.py` attaches `hub_link_comparison` without increasing the existing `DEFAULT_RENDER_FOLLOWUP_LIMIT=3`. B12 adds no renderer call, HTTP request, coverage scheduler or budget.
- Up to five hubs may be selected for disclosure even though only the existing three-page browser policy can execute. Selected hubs outside that existing policy are explicitly `unassessed`; paired failures and completed comparisons are counted separately. `interpretation=paired_comparison_neither_surface_is_sole_truth` is pinned by regression.

Known B12 integration gap, deliberately **not** called complete: `scanner.run_scan` currently invokes `run_render_followup(pages if material_render_risk else [], ...)`. Therefore scans where the explicit rendering policy declines browser follow-up pass an empty page list and cannot disclose otherwise eligible retained hubs as selected/unassessed. The next serialized change must pass the final retained page set to the B12 disclosure builder while preserving the existing decision about whether any renderer calls are allowed. Do not broaden the browser budget to fix this.

A fresh CodeRabbit review was requested against the exact B11/B12 invariants; no current independent-review pass is claimed until that response is recorded.

Detailed B12 checkpoint: `docs/superpowers/plans/2026-09-20-stage2-b12-hub-render-evidence.md`.

### B11 checkpoint history

B11 now reaches the real retained Standard-150 page set without expanding the crawl or adding a second budget.

- `scanner-api/app/extract.py` retains a bounded private `_reachability_links` cache only for accepted `usable_html` source pages. The B11 cache contains exact target URL identity plus semantic navigation state, not duplicated anchor text.
- `scanner-api/app/stage2_reachability_provenance.py::enrich_pages_from_retained_link_evidence` runs only on the final retained assessed-page set, creates graph edges only when both exact request URLs are retained, revalidates every source as accepted usable HTML, and uses only the retained exact seed as depth origin.
- `scanner-api/app/content_evidence_findings.py` invokes that adapter from the real `scanner.build_findings()` path after the final Standard-150 cap. A later Review call sees no private cache, so hidden evidence cannot be silently replayed.
- Unsampled links are ignored for B11 graph construction rather than appended to `pages`; sitemap discovery never becomes an inlink/depth; the adapter cannot emit a sitewide orphan claim; no network call or new request scheduler is introduced.
- `_reachability_links` is removed in a `finally` block before scan results can be returned, signed, persisted, previewed or exported.

Exact B11 retained-hook head `f51869adf8eac44de4fa7c9387590ab3c330c5a9` passed FixList CI `35478073142` with **115 root tests**, **1,924 scanner-api tests / 18 intentional skips**, labelled synthetic Stage-1 corpus, frozen revision, production scanner image, lint, typecheck, generated contracts, frontend contracts and production build.

The prior focused CodeRabbit review found no correctness defect in the semantic-link B11 seam and independently confirmed semantic-only navigation evidence, exact URL identity, sitemap/inlink separation, challenged-source exclusion and the no-sitewide-orphan boundary. The retained-link hook landed afterward; the current B11/B12 review request is the independent-review gate for that newer shared hook.

Detailed B11 checkpoint: `docs/superpowers/plans/2026-09-20-stage2-b11-reachability-provenance.md`.

### Prior reviewed Stage-2 hardening

Before B11, exact reviewed code/test head `f904649c9193877181471e1daa01097da0f3062b` passed FixList CI `35472567286` with **115 root scanner tests**, **1,911 scanner-api passed / 18 skips**, labelled synthetic Stage-1 corpus, frozen revision, production scanner-image build, lint, typecheck, generated contracts, frontend contract tests and production build.

Previously corrected independent-review findings remain carried forward: image applicability before destructive DOM sanitization; empty-landmark selection via explicit `is None`; no raw B10 customer copy in retained duplicate evidence; diagnostic-only redirect loops remaining unverified; and challenge/block/rate-limit redirect destinations remaining unknown before generic HTTP failure classification.

## Stage-2 lane integration already on PR #303

The lane PRs were CI/review inputs and were not merged directly to `main`.

- **B06** shared finite coverage scheduler / unsampled internal-link verification.
- **B07** active soft-404 producer/orchestration and provenance hardening from `agent/stage2-b07-producer-20260919`.
- **B08** redirect destination meaning from `agent/stage2-b08-redirect-meaning-20260919` / PR #309.
- **B09 + B16** sitemap integrity and exact URL variants from `agent/stage2-b09-b16-coverage-20260919` / PR #310.
- **B10–B15/B17–B18** helper/evidence contracts from `agent/stage2-b10-b18-acceptance-20260919` / PR #311.

The B07/B09/B16 producer path is serialized through the existing `SharedCoverageProbeScheduler`, not a second scheduler. Synthetic/probe-only URLs remain outside assessed `pages` and `pages_crawled` and cannot inflate the Standard-150 denominator.

## Stage 2 status

Stage 2 is **not source-complete** and Stage 3 must not be shared-integrated yet.

Materially proven/integrated on this line:

- B06 shared bounded scheduler/internal-link verification;
- B07 active soft-404 orchestration + authenticated downstream proof;
- B08 redirect meaning with fail-closed access handling;
- B09/B16 helper + shared scheduler integration, with exact source-level sitemap provenance/customer-promotion caveats;
- B10 accepted main-content extraction/privacy seam;
- B11 real retained-set producer wiring and exact-head CI;
- B12 paired-hub evidence seam under the existing render-followup policy, exact-head CI, with the shared no-render caller-disclosure gap still open;
- B17 decoded HTML + inline script/style byte separation.

Open serialized Stage-2 work:

- **B10:** add authenticated Review → authority → persistence → customer/card/handoff/export proof if near-duplicate evidence becomes customer-visible.
- **B11:** resolve fresh independent review of the retained-link hook; add downstream authenticated/privacy proof only if the new provenance is exposed to customers.
- **B12:** fix the `run_scan` caller so final retained pages reach B12 disclosure even when browser execution is not selected; do not add renderer calls or another budget. Resolve fresh independent review.
- **B13/B14:** contextual local entity/status/address/phone/regular-hours producer evidence and verified entity matching/NAP consistency.
- **B15:** current-content intent + current-scoped temporal anchors; an old date alone cannot fail freshness.
- **B17:** directly measured transfer bytes; decoded bytes remain distinct. Optional CrUX must explicitly support disconnected/stale/unavailable.
- **B18:** optional GSC with explicit disconnected/stale/unavailable until a current owner-authorized response exists.
- **B09 customer/source completion:** exact sitemap root/child provenance and exact child failure reasons must be retained if promoted into displayed findings.
- Any new customer-displayed evidence/count/finding requires the real authenticated downstream chain before closure.

Combined independent review and fresh exact-head CI after the remaining shared wiring remain mandatory before recording B06–B18 complete.

## Stage 3 lanes — built in isolation, not integrated

Do not duplicate this work. Reuse these branches after Stage 2 closes:

- `agent/stage3-b19-b20-decisions-20260919`: B19 **impact × reach × page value × confidence** evidence/explanations and B20 explicit evidenced root causes across SEO/GEO. Page-family similarity is never proof of a shared root cause. Python Review remains canonical ranking authority.
- `agent/stage3-b21-b24-delivery-20260919`: B21 exact affected-page unions and rank-before-truncate, B22 authenticated private preview selection, B23 explicit verified-root-cause score caps preserving existing incomplete/access ceilings, B24 backward-compatible handoff v2.

These lanes are integration-ready inputs, not source-complete product behavior. Shared ranking/authority/persistence/customer interfaces remain serialized integration work.

## Stage 4 lane — built in isolation, not released

Reuse `agent/stage4-b25-b28-compat-release-20260919` after Stage 3 shared integration.

Spec numbering controls:

- **B25** named synthetic corpus + genuine provenance-labelled 30-site baseline/candidate gate;
- **B26** reproduced own-site serving defects/fixes;
- **B27** GEO/historical HMAC/reader/tamper/privacy compatibility;
- **B28** exact-source review/CI/deployment/live customer acceptance.

The genuine 30-site gate is still **not assessed**. Historical summary counts and synthetic mini-fixtures cannot be turned into a pass. No Stage-4 deployment, customer scan or live acceptance has been run by this integration branch.

## Invariants carried forward

- Standard 150 assessed-page cap and truthful denominators remain authoritative.
- One finite shared Stage-2 follow-up request pool only.
- Robots ownership, DNS/SSRF, redirect, decoded-body and deadline boundaries remain intact.
- One active scan/account, cancellation, server terminalization and exact scan isolation remain intact.
- Missing/challenged/robots/budget/deadline/stale/disconnected evidence remains unknown.
- Historical signatures/readers remain compatible and unknown new evidence versions fail closed.
- Preview privacy remains intact.
- Python Review remains the sole canonical ranking/decision authority.
- Premium/Grok remain outside this integration.

## Exact next action

Stay on Stage 2. Fix the narrow B12 shared-caller disclosure gap while retaining the existing browser-execution limit and no-second-budget invariant, then resolve current independent review. Continue B13–B15/B17 transfer/B18 after B12 closes. Add authenticated downstream tests for anything customer-visible and require exact-head FixList CI + independent review for meaningful combined checkpoints.

Do not begin shared Stage-3 integration until B06–B18 are genuinely source-complete and green. Do not begin Stage-4 live execution until all applicable source/review/CI/30-site/release gates are actually proven.