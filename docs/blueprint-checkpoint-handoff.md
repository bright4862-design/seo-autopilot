# Blueprint implementation checkpoint

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`.

This is the current serialized handoff for the FixList full-scanner blueprint. Historical checkpoints remain in Git history and the linked executable plans. The approved spec controls over older handoff paraphrases.

## Release boundary

- Stage-1 production publication/promotion/live non-owner acceptance remains owned by the existing exact-source release operator.
- Do not use this later-stage integration branch to publish, promote worker traffic, mutate admission, run a competing production scan, change schemas/secrets, or otherwise move production.
- Later-stage integration stays on `agent/full-blueprint-stage2-coverage-b06-20260919`, PR #303.
- `main` was reverified on 2026-09-20 at `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad`; the freeze remains intact.
- Once Stage-1 live acceptance is recorded, reconcile this integration branch onto the then-current accepted `main` without reverting V7 route/public-build changes or the durable ownership-before-admission fix, then run fresh exact-head combined CI.

## Current Stage-2 executable checkpoint

Exact executable head: `e286c3c4f0db6b90c60300f804232c5894936c40`.

FixList CI `35484767939` — **SUCCESS** on both jobs:

- immutable checkout verified the exact SHA;
- root scanner regressions: **115 passed**;
- `scanner-api`: **1,961 passed / 18 intentional skips**;
- B15 focused suite: **9 passed** as part of the scanner suite;
- labelled Stage-1 corpus: `synthetic`, 14 cases / 55 assertions, `full_30_site_gate=not_assessed`;
- frozen scanner revision `01ebe8e90df1e6bd`: passed;
- production scanner image: `sha256:afc21e8f12c5d00cfaa9cdbef78514576141422bc9ee08605e8f2f6affabd74d`;
- lint, typecheck, generated release contracts, frontend contract tests and production frontend build: passed.

The workflow installed Node `20.20.2`; do not describe it as Node `20.19.5` runtime evidence.

Documentation-only commits sit above this certified executable head; certification remains attached to the exact code SHA.

## Stage-2 material state

### B06–B10

- B06 shared finite coverage scheduler / unsampled internal-link verification is integrated with authenticated downstream proof.
- B07 active soft-404 orchestration is integrated through that same finite scheduler; blocked/challenged/robots/budget/deadline/incomplete evidence remains unknown.
- B08 redirect meaning distinguishes harmless normalization, usable, wrong/catch-all, unusable and unverified access. Challenge/block/rate-limit evidence remains unknown.
- B09 sitemap integrity shares the same scheduler. If promoted to customer findings, exact root/child provenance and child failure reasons must survive the downstream chain.
- B10 accepted main-content extraction/privacy seam is integrated. Raw substantive page copy is not retained; bounded fingerprint/signature evidence is used. Add authenticated downstream proof only if near-duplicate evidence becomes customer-visible.

### B11/B12

B11 reaches the real retained Standard-150 set after the final cap without expanding the assessed set or request budget. Exact retained edges create sample-scoped depth/inlink/navigation provenance only; sitemap discovery cannot become an inlink and `sitewide_orphan_claim` remains false. The temporary link cache is removed before result persistence/customer projection.

B12 reuses B11 retained-link evidence and only the existing bounded browser-followup observations. Up to five hubs may be disclosed while browser execution remains under the existing three-page policy. A prior independent-review P1 is fixed: rendered links count as completed evidence only from successful accepted 2xx `usable_html` observations with no challenge/block/rate-limit/fetch-error/truncation state. Bare link dictionaries and unusable renderer responses fail closed as unavailable/unassessed.

### B13/B14

B13 page-level structured local-entity evidence is produced from accepted usable HTML. The bounded versioned producer currently uses conservative LocalBusiness/Store-family JSON-LD and records name, address, phone, explicit regular hours when present, schema type, entity ID and optional holiday-hours/photos/sameAs/parent presence. Missing hours with unknown applicability remains `not_verified`; optional fields are not universal defects. Malformed/oversized structured data and unusable HTTP pages fail closed.

B14 is stricter than B13 completeness:

- only an explicit absolute HTTP(S) JSON-LD `@id` is currently verified for cross-page identity;
- relative/fragment IDs remain observed but unverified until trusted base resolution exists;
- shared names, addresses, phones and page-family similarity never prove identity;
- the same verified entity ID must appear on at least two distinct page URLs before NAP consistency can pass or fail;
- same-page duplicate/conflicting JSON-LD cannot become cross-page proof;
- distinct explicit IDs remain separate even with a shared phone;
- `sitewide_consistency_claim` is false.

B13/B14 hardening head `fe3d18cc63f7b0acdf0e97679db5b14e47966e10` passed CI `35484333097` with 115 root and 1,952 scanner-api tests / 18 skips. Detailed checkpoint: `docs/superpowers/plans/2026-09-20-stage2-b13-b14-local-entity.md`.

B13/B14 remain **partial** because their bounded scan-level aggregate is not yet attached to the shared top-level `run_scan`/authority result. No B13/B14 customer repair/card/export or score change is introduced. Generic visible-text/store-form identity, complete Coming Soon inference and full store-finder/form parity are not claimed.

### B15 — current slice

B15 contextual freshness is now produced on the real retained-page seam by `scanner-api/app/stage2_freshness_producer.py` and invoked from `content_evidence_findings` after the final assessed set is stable.

- accepted usable HTML is mandatory;
- old year/article/path alone cannot fail freshness;
- explicit current-content language is required;
- generic action language such as `apply now` is not current-content intent;
- current-scoped temporal evidence must occur in the same visible field as current language;
- explicit archive/history wording keeps that field's dates historical so mixed wording remains unknown instead of a false stale defect;
- path dates are historical-only;
- year-only dates use 31 December conservatively;
- no new fetch, request budget, repair/card or score adjustment is introduced.

Exact B15 code head `e286c3c4f0db6b90c60300f804232c5894936c40` passed CI `35484767939`: 115 root passed, 1,961 scanner-api passed / 18 skips, labelled synthetic corpus unchanged, frozen revision passed, production image built and frontend/contract gates passed.

Detailed checkpoint: `docs/superpowers/plans/2026-09-20-stage2-b15-contextual-freshness.md`.

### B16–B18

- B16 exact URL-variant identity is integrated; no sibling-host expansion or duplicate claim occurs without independent equivalence evidence.
- B17 decoded HTML bytes and inline script/style bytes are separated. Direct transfer bytes are still open and must not be replaced by decoded bytes or zero. Optional CrUX must expose disconnected/stale/unavailable states unless current authorized evidence exists.
- B18 optional GSC remains open with explicit disconnected/stale/unavailable behavior required unless a current owner-authorized response exists.

## Independent review status

A fresh CodeRabbit request was posted for the combined B11–B14 shape. The bot currently reports that automatic review is disabled for this repository and exposes a manual trigger; the request is therefore **not** counted as an independent-review pass. B15 also still requires fresh independent review before Stage 2 can close. Do not substitute the request itself for review evidence.

## Stage 2 remains open

Do not start shared Stage-3 integration yet. Remaining serialized work:

1. attach bounded B13/B14 scan-level evidence to the shared scanner result/authority path without changing the assessed page set or request budget;
2. add direct B17 transfer-byte evidence and conservative optional CrUX states;
3. add B18 optional GSC states;
4. preserve exact B09 sitemap provenance if/when exposed downstream;
5. add real producer → Review → signed authority → persisted rows → verified customer/card/handoff/export coverage for every newly displayed evidence/count/finding;
6. obtain fresh independent review of the combined B11–B18 shape and close concrete findings with regressions;
7. require final fresh exact-head CI after the remaining shared wiring before recording B06–B18 complete.

## Stage 3 — isolated lanes built, not shared-integrated

Reuse these existing lanes only after Stage 2 closes:

- `agent/stage3-b19-b20-decisions-20260919` / head `e74d87acd0cec2955402b96f635f13bc275f3a91`: B19 impact × reach × page value × confidence and B20 explicit evidenced SEO/GEO root causes. Lane CI passed.
- `agent/stage3-b21-b24-delivery-20260919` / head `a998b4e38a06d6c163ac8853c3e49e9f10a58cb7`: B21 exact unions/rank-before-truncate, B22 authenticated private preview selection, B23 evidenced root-cause score caps preserving existing ceilings, B24 backward-compatible handoff v2. Lane CI passed.

These are integration-ready inputs, not source-complete product behavior. Python Review remains canonical ranking authority. Shared ranking/authority/persistence/customer interfaces remain serialized integration work.

## Stage 4 — isolated lane built, not released

Reuse `agent/stage4-b25-b28-compat-release-20260919` / head `d2ce905ff67410586f86e38bafd93ce4e998e4d1` only after Stage 3 shared integration. Lane CI passed but does not constitute live acceptance.

Spec numbering controls:

- B25 named synthetic corpus + genuine provenance-labelled 30-site baseline/candidate gate;
- B26 reproduced own-site serving defects/fixes;
- B27 GEO/historical HMAC/reader/tamper/privacy compatibility;
- B28 exact-source review/CI/deployment/live customer acceptance.

The genuine 30-site gate remains **not assessed**. Historical summary counts and synthetic fixtures cannot be turned into a pass. No Stage-4 deployment, customer scan or live acceptance has been run by this integration branch.

## Invariants carried forward

- Standard-150 assessed-page cap and truthful denominators remain authoritative.
- One finite shared Stage-2 follow-up request pool only.
- Robots ownership, DNS/SSRF, redirects, body/deadline limits remain intact.
- One active scan/account, cancellation, server terminalization and exact scan isolation remain intact.
- Missing/challenged/robots/budget/deadline/stale/disconnected/invalid evidence remains unknown.
- Historical signatures/readers remain compatible; unknown evidence versions fail closed.
- Preview privacy remains intact.
- Python Review remains the sole canonical ranking/decision authority.
- Premium/Grok remain outside this integration.

## Exact next action

Remain on Stage 2. Wire the bounded B13/B14 aggregation into the shared scanner result/authority path, preserving evidence-only/no-customer-claim semantics. Then implement B17 direct transfer bytes/CrUX and B18 optional GSC states. Obtain fresh independent review and exact-head CI on the final Stage-2 shared source before beginning Stage-3 integration.
