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

### Current B12 checkpoint — shared caller disclosure gap closed and exact-head CI green

Exact executable head: `d612ceade6fc31ecd3e01d5b195dbd4d646524ef`.

FixList CI `35483256047` — **SUCCESS** on both jobs.

Fresh direct verification on that exact SHA:

- immutable checkout passed;
- root scanner regressions: **115 passed**;
- `scanner-api`: **1,932 passed / 18 intentional skips**;
- labelled Stage-1 corpus: `synthetic`, 14 cases / 55 assertions, `full_30_site_gate=not_assessed`;
- frozen scanner revision `01ebe8e90df1e6bd`: passed;
- production scanner image: passed, image SHA `sha256:be6a8dfc68ad87a156698402cbf4f89199a05a938225a8a4f25cae01338d2c28`;
- lint, typecheck, generated release contracts, frontend contract tests and production frontend build: passed.

The workflow resolved Node `20.20.2`; do not describe this run as Node `20.19.5` runtime evidence.

Implemented B12 behavior:

- `scanner-api/app/stage2_hub_render_evidence.py` selects at most five verified structural hubs from the retained Standard-150 set and separately records the exact eligible count plus whether selection was truncated.
- Raw link evidence is reconstructed only from B11 retained assessed-page provenance. If B11 source samples are truncated such that raw-link absence cannot be proven, the hub fails closed instead of producing a false raw/render difference.
- Rendered links are accepted only from an explicit renderer link collection, resolved against the hub, fragment-stripped, and intersected with the exact retained assessed URL set. Unsampled targets never become assessed pages.
- Exact path/query/case/reserved-escape identity is preserved. An explicit empty query delimiter is restored after URL resolution so `/page` and `/page?` are not silently collapsed.
- An absent rendered link collection is `failed`/unavailable rather than an empty success. Renderer exceptions remain visible only in the pre-existing browser-followup diagnostic field; the new B12 evidence records the normalized `renderer_failed` reason and does not duplicate raw exception text.
- `scanner-api/app/render_followup.py` now separates browser authorization from B12 disclosure. Its existing `pages` input still controls browser selection and remains limited by `DEFAULT_RENDER_FOLLOWUP_LIMIT=3`; the new keyword-only `evidence_pages` input is used only to build B12 disclosure rows.
- `scanner.run_scan` continues to pass `pages if material_render_risk else []` to the browser-policy input and enables `_render_page` only when material rendering risk is present, while always passing the exact final retained assessed set as `evidence_pages=pages`.
- Therefore, when rendering policy declines browser execution, eligible retained hubs are truthfully selected/unassessed while browser `selected_pages=0`, `attempted_pages=0`, and no renderer callback is enabled. No new browser call, HTTP request, coverage scheduler or second budget is created.
- Up to five hubs may be selected for disclosure even though only the existing three-page browser policy can execute. Selected hubs outside that existing policy are explicitly `unassessed`; paired failures and completed comparisons are counted separately. `interpretation=paired_comparison_neither_surface_is_sole_truth` remains pinned.

The final caller-shape regressions prove both the evidence-only no-render state and the real `run_scan` seam. The latter asserts the exact `result["pages"]` object is the disclosure source while browser-policy pages are empty and `render_page` is `None` when material render risk is absent.

A fresh CodeRabbit review is requested against the exact final B11/B12 shape; independent review remains open until a current response is recorded.

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
- B12 paired-hub evidence plus final shared no-render caller disclosure wiring, exact-head CI;
- B17 decoded HTML + inline script/style byte separation.

Open serialized Stage-2 work:

- **B10:** add authenticated Review → authority → persistence → customer/card/handoff/export proof if near-duplicate evidence becomes customer-visible.
- **B11:** resolve fresh independent review of the retained-link hook; add downstream authenticated/privacy proof only if the new provenance is exposed to customers.
- **B12:** source/caller integration is implemented and exact-head green; resolve fresh independent review. Add authenticated downstream proof only if B12 samples later become customer-visible.
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

Stay on Stage 2. Resolve the current independent review request for the exact B11/B12 shared shape, then implement B13/B14 local entity/NAP producer evidence conservatively from accepted evidence. Entity identity must be explicit/proven rather than inferred from shared names or phone numbers; optional holiday-hours/photos/sameAs/parent fields remain optional; unknown/Coming Soon regular-hours applicability stays unknown or not applicable rather than becoming a defect. Continue B15/B17 transfer/B18 after that. Add authenticated downstream tests for anything customer-visible and require exact-head FixList CI + independent review for meaningful combined checkpoints.

Do not begin shared Stage-3 integration until B06–B18 are genuinely source-complete and green. Do not begin Stage-4 live execution until all applicable source/review/CI/30-site/release gates are actually proven.
