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

Exact reviewed code/test head before the latest documentation-only commits: `f904649c9193877181471e1daa01097da0f3062b`.

Exact-head FixList CI: `35472567286` — **SUCCESS**.

Verification on that code head:

- root scanner regressions: **115 passed**;
- `scanner-api`: **1,911 passed / 18 intentional skips**;
- focused B10/B17 extraction: **5 passed**;
- focused Stage-2 review hardening: **5 passed**;
- B08 redirect meaning: **6 passed**;
- labelled Stage-1 corpus: `synthetic`, 14 cases / 55 assertions, `full_30_site_gate=not_assessed`;
- frozen scanner revision `01ebe8e90df1e6bd`: passed;
- production scanner-image build: passed, image SHA `sha256:73902d7ee4728b41d0b26bc956ff51bd388320d40c439faaacd2735ff98b9f63`;
- lint, typecheck, generated release contracts, frontend contract tests and production build: passed.

The workflow resolved Node 20.20.2. Do not describe this exact CI run as Node 20.19.5 runtime evidence.

Detailed current review checkpoint: `docs/superpowers/plans/2026-09-19-stage2-serialized-review-hardening.md`.

## Stage-2 lane integration already on PR #303

The lane PRs were CI/review inputs and were not merged directly to `main`.

- **B06** shared finite coverage scheduler / unsampled internal-link verification.
- **B07** active soft-404 producer/orchestration and provenance hardening from `agent/stage2-b07-producer-20260919`.
- **B08** redirect destination meaning from `agent/stage2-b08-redirect-meaning-20260919` / PR #309.
- **B09 + B16** sitemap integrity and exact URL variants from `agent/stage2-b09-b16-coverage-20260919` / PR #310.
- **B10–B15/B17–B18** helper/evidence contracts from `agent/stage2-b10-b18-acceptance-20260919` / PR #311.

The B07/B09/B16 producer path is serialized through the existing `SharedCoverageProbeScheduler`, not a second scheduler. Synthetic/probe-only URLs remain outside assessed `pages` and `pages_crawled` and cannot inflate the Standard-150 denominator.

## Fresh independent-review corrections landed

The current green code head incorporates the latest concrete review findings:

1. **Image evidence / DOM sanitization** — scalar image applicability is captured before destructive BeautifulSoup sanitization. Hidden/example descendants are excluded; decomposed nodes are never dereferenced later.
2. **Empty landmark correctness** — main/article/body selection uses explicit `is None` checks so an empty `<main>` cannot fall through to unrelated body/title content.
3. **B10 raw-content privacy** — raw substantive page text is no longer retained by the producer compatibility field. The field contains only irreversible SHA-256 five-token shingle digests plus aggregate signature/token/character-count metadata. The corresponding independent review thread remains intentionally open until the reviewer confirms whether the hashed compatibility field itself must be absent from the final `pages`/`crawled_pages` payload.
4. **Redirect-loop provenance** — zero-hop diagnostic loop state is `not_verified`; a loop with observed hop evidence remains `verified_unusable`.
5. **Access-block redirect truthfulness** — challenge/block/rate-limit evidence is evaluated before generic HTTP >=400 classification. Challenged 403/429/503 destinations remain unknown; a verified ordinary 404 remains unusable.

The empty-landmark and access-block review threads were replied to with exact-head CI evidence and resolved. The B10 final-publication thread remains open for independent confirmation.

## Stage 2 status

Stage 2 is **not source-complete** and Stage 3 must not be shared-integrated yet.

Source-complete/materially proven on the integration line:

- B06 shared bounded scheduler/internal-link verification;
- B07 active soft-404 orchestration + authenticated downstream proof;
- B08 redirect meaning with current fail-closed access handling;
- B09/B16 helper + shared scheduler integration, with remaining exact source-level sitemap provenance/customer promotion decisions noted below;
- B10 accepted main-content extraction/privacy seam;
- B17 decoded HTML + inline script/style byte separation.

Open serialized Stage-2 work:

- **B10:** resolve final publication-boundary handling of hashed compatibility material; if duplicate evidence becomes displayed, add producer → Review → signed authority → persisted rows → customer/card/handoff/export proof.
- **B11:** stable sample-scoped crawl depth, inlink and navigation provenance; no sitewide orphan claim from sample-only evidence.
- **B12:** paired raw/rendered hub-link evidence for up to five hubs, with explicit completed/failed/unassessed states.
- **B13/B14:** contextual local entity/status/address/phone/regular-hours producer evidence and verified entity matching/NAP consistency.
- **B15:** current-content intent + current-scoped temporal anchors; an old date alone cannot fail freshness.
- **B17:** directly measured transfer bytes; decoded bytes remain distinct. Optional CrUX must explicitly support disconnected/stale/unavailable.
- **B18:** optional GSC with explicit disconnected/stale/unavailable until a current owner-authorized response exists.
- **B09 customer/source completion:** exact sitemap root/child provenance and exact child failure reasons must be retained if promoted into displayed findings.
- Any new customer-displayed evidence/count/finding requires the real authenticated downstream chain before closure.

Combined independent review and fresh exact-head CI after the remaining shared wiring remain mandatory gates before recording B06–B18 complete.

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

Stay on Stage 2. First close the B10 final publication-boundary review question with a reproducing test if the reviewer requires the hashed compatibility field itself to be removed. Then implement B11 producer provenance truthfully from observed crawl/inlink/navigation data without inventing a complete-site denominator. Continue B12–B15/B17 transfer/B18 as serialized slices, add authenticated downstream tests for anything customer-visible, run focused tests after each slice, and require exact-head FixList CI + independent review for meaningful combined checkpoints.

Do not begin shared Stage-3 integration until B06–B18 are genuinely source-complete and green. Do not begin Stage-4 live execution until all applicable source/review/CI/30-site/release gates are actually proven.