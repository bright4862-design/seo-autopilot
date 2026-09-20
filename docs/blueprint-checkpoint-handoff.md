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

### B11 checkpoint — shared retained-link producer hook implemented and CI green

B11 now reaches the real retained Standard-150 page set without expanding the crawl or adding a second budget.

- `scanner-api/app/extract.py` retains a bounded private `_reachability_links` cache only for accepted `usable_html` source pages. The B11 cache contains exact target URL identity plus semantic navigation state, not duplicated anchor text.
- `scanner-api/app/stage2_reachability_provenance.py::enrich_pages_from_retained_link_evidence` runs only on the final retained assessed-page set, creates graph edges only when both exact request URLs are retained, revalidates every source as accepted usable HTML, and uses only the retained exact seed as depth origin.
- `scanner-api/app/content_evidence_findings.py` invokes that adapter from the real `scanner.build_findings()` path after the final Standard-150 cap. A later Review call sees no private cache, so hidden evidence cannot be silently replayed.
- Unsampled links are ignored for B11 graph construction rather than appended to `pages`; sitemap discovery never becomes an inlink/depth; the adapter cannot emit a sitewide orphan claim; no network call or new request scheduler is introduced.
- `_reachability_links` is removed in a `finally` block before scan results can be returned, signed, persisted, previewed or exported.

Behavioral coverage now includes the existing six provenance tests, two semantic-navigation identity tests, coverage-evidence fail-closed cases, plus three new real retained-set hook cases: semantic seed navigation → exact depth/inlink; unsampled outgoing target cannot expand assessed pages; and challenged/unusable source cannot contribute even with malformed private cache input.

Exact executable head: `f51869adf8eac44de4fa7c9387590ab3c330c5a9`.

FixList CI `35478073142` — **SUCCESS** on both jobs:

- immutable checkout verified `f51869adf8eac44de4fa7c9387590ab3c330c5a9`;
- root scanner regressions: **115 passed**;
- scanner-api: **1,924 passed / 18 intentional skips**;
- new `test_stage2_reachability_run_scan_seam.py`: **3 passed**;
- labelled Stage-1 corpus remained explicitly `synthetic`, **14 cases / 55 assertions**, `full_30_site_gate=not_assessed`;
- frozen scanner revision `01ebe8e90df1e6bd`: passed;
- production scanner image passed, image SHA `sha256:7dc32951eaf6b600424b9e1fde302a9300ae90b333f813e4ac1156fe1bb3ff72`;
- lint, typecheck, generated release contracts, frontend contract tests and production build: passed.

The workflow resolved Node `20.20.2`; do not describe this run as Node `20.19.5` runtime evidence.

The prior focused CodeRabbit review found no correctness defect in the semantic-link B11 seam and independently confirmed semantic-only navigation evidence, exact URL identity, sitemap/inlink separation, challenged-source exclusion and the no-sitewide-orphan boundary. The retained-link hook above landed afterward, so **fresh incremental review of `f51869ad...` remains a gate** before B11 is independently review-complete.

Detailed checkpoint: `docs/superpowers/plans/2026-09-20-stage2-b11-reachability-provenance.md`.

B11 introduces no customer-facing repair/card in this slice. If B11 source URL samples later become persisted/previewed/exported as customer-visible evidence, that display path still requires bounded authenticated authority/persistence/entitlement/privacy coverage.

### Prior B11 checkpoint history

- `1f27022583b3777cfe886632cff3b7db19140334` passed CI `35475369510` before semantic link context.
- `0b657afad65bf6c9aef883de11fd23093c6a1f90` correctly exposed one old assertion that did not yet include `navigation_presence`; its B11 tests passed while scanner-api ended **1 failed, 1,920 passed, 18 skipped** and root tests were **115 passed**.
- The old assertion was strengthened at `c26a0495162359a6af72de0371ea33207e6df505`; CI `35475725233` passed both jobs with **115 root passed** and **1,921 scanner-api passed / 18 skipped**.

### Prior exact reviewed Stage-2 checkpoint

Before B11, exact reviewed code/test head `f904649c9193877181471e1daa01097da0f3062b` passed FixList CI `35472567286` with **115 root scanner tests**, **1,911 scanner-api passed / 18 skips**, labelled synthetic Stage-1 corpus, frozen revision, production scanner-image build, lint, typecheck, generated contracts, frontend contract tests and production build.

## Stage-2 lane integration already on PR #303

The lane PRs were CI/review inputs and were not merged directly to `main`.

- **B06** shared finite coverage scheduler / unsampled internal-link verification.
- **B07** active soft-404 producer/orchestration and provenance hardening from `agent/stage2-b07-producer-20260919`.
- **B08** redirect destination meaning from `agent/stage2-b08-redirect-meaning-20260919` / PR #309.
- **B09 + B16** sitemap integrity and exact URL variants from `agent/stage2-b09-b16-coverage-20260919` / PR #310.
- **B10–B15/B17–B18** helper/evidence contracts from `agent/stage2-b10-b18-acceptance-20260919` / PR #311.

The B07/B09/B16 producer path is serialized through the existing `SharedCoverageProbeScheduler`, not a second scheduler. Synthetic/probe-only URLs remain outside assessed `pages` and `pages_crawled` and cannot inflate the Standard-150 denominator.

## Independent-review corrections already landed

The previously green reviewed code incorporated and regressed these concrete findings:

1. **Image evidence / DOM sanitization** — scalar image applicability is captured before destructive BeautifulSoup sanitization. Hidden/example descendants are excluded; decomposed nodes are never dereferenced later.
2. **Empty landmark correctness** — main/article/body selection uses explicit `is None` checks so an empty `<main>` cannot fall through to unrelated body/title content.
3. **B10 raw-content privacy** — raw substantive page text is no longer retained by the producer compatibility field. It uses bounded deterministic SHA-256 five-token shingle fingerprints plus aggregate signature/token/character-count metadata. These fingerprints are not treated as secret against candidate-text dictionary matching.
4. **Redirect-loop provenance** — zero-hop diagnostic loop state is `not_verified`; a loop with observed hop evidence remains `verified_unusable`.
5. **Access-block redirect truthfulness** — challenge/block/rate-limit evidence is evaluated before generic HTTP >=400 classification. Challenged 403/429/503 destinations remain unknown; a verified ordinary 404 remains unusable.

## Stage 2 status

Stage 2 is **not source-complete** and Stage 3 must not be shared-integrated yet.

Materially proven/integrated on this line:

- B06 shared bounded scheduler/internal-link verification;
- B07 active soft-404 orchestration + authenticated downstream proof;
- B08 redirect meaning with fail-closed access handling;
- B09/B16 helper + shared scheduler integration, with exact source-level sitemap provenance/customer-promotion caveats;
- B10 accepted main-content extraction/privacy seam;
- B11 real retained-set producer wiring, exact-head CI green; fresh review still open;
- B17 decoded HTML + inline script/style byte separation.

Open serialized Stage-2 work:

- **B10:** add authenticated Review → authority → persistence → customer/card/handoff/export proof if near-duplicate evidence becomes customer-visible.
- **B11:** resolve fresh independent review of `f51869ad...`; add downstream authenticated/privacy proof only if the new provenance is exposed to customers.
- **B12:** paired raw/rendered hub-link evidence for up to five representative hubs, with explicit completed/failed/unassessed states and neither evidence source treated as sole truth.
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

Stay on Stage 2. Request/resolve focused independent review of the B11 retained-link hook at executable head `f51869ad...`. Then implement B12 paired raw/rendered hub-link production as the next serialized slice, followed by B13–B15/B17 transfer/B18. Add authenticated downstream tests for anything customer-visible and require exact-head FixList CI + independent review for meaningful combined checkpoints.

Do not begin shared Stage-3 integration until B06–B18 are genuinely source-complete and green. Do not begin Stage-4 live execution until all applicable source/review/CI/30-site/release gates are actually proven.