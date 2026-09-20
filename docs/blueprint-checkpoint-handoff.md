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

Exact executable head: `fe3d18cc63f7b0acdf0e97679db5b14e47966e10`.

FixList CI `35484333097` — **SUCCESS** on both jobs:

- immutable checkout verified `fe3d18cc63f7b0acdf0e97679db5b14e47966e10`;
- root scanner regressions: **115 passed**;
- `scanner-api`: **1,952 passed / 18 intentional skips**;
- labelled Stage-1 corpus: `synthetic`, 14 cases / 55 assertions, `full_30_site_gate=not_assessed`;
- frozen scanner revision `01ebe8e90df1e6bd`: passed;
- production scanner image: `sha256:e776770dc976cf7c4b434e134db31323f61278c0f8c460c53ca890cc50d11bb9`;
- lint, typecheck, generated release contracts, frontend contract tests and production frontend build: passed.

The workflow resolved Node `20.20.2`; do not describe it as Node `20.19.5` runtime evidence.

Current documentation-only branch commits sit above that certified executable head. Certification remains attached to the exact executable SHA until a later code checkpoint receives its own CI.

## Stage-2 material state

### B06–B10

- B06 shared finite coverage scheduler / unsampled internal-link verification is integrated with authenticated downstream proof.
- B07 active soft-404 orchestration is integrated through the same finite scheduler; blocked/challenged/robots/budget/deadline/incomplete evidence remains unknown.
- B08 redirect meaning distinguishes harmless normalization, usable, wrong/catch-all, unusable and unverified access. Challenge/block/rate-limit evidence remains unknown.
- B09 sitemap integrity shares the same scheduler. If promoted to customer findings, exact root/child provenance and child failure reasons must survive the downstream chain.
- B10 accepted main-content extraction/privacy seam is integrated. Raw substantive page copy is not retained; bounded fingerprint/signature evidence is used. Add authenticated downstream proof only if near-duplicate evidence becomes customer-visible.

### B11

B11 reaches the real retained Standard-150 set after the final cap. Accepted raw HTML temporarily retains exact target URL plus semantic navigation state; graph edges exist only where both exact URLs remain assessed. Sitemap discovery cannot create an inlink/depth observation, unsampled targets cannot expand `pages`, challenged/unusable sources are re-gated out, and `sitewide_orphan_claim` remains false. The private cache is removed before result persistence/customer projection. No new network request or budget exists.

Exact retained-hook checkpoint `f51869adf8eac44de4fa7c9387590ab3c330c5a9` passed CI `35478073142` with 115 root tests and 1,924 scanner-api tests / 18 skips.

### B12

B12 uses B11 retained-link provenance plus only the existing bounded browser-followup observations. Up to five structural hubs can be selected for evidence disclosure; browser execution remains capped by the existing three-page policy. The evidence-only retained-set channel does not authorize rendering when policy declines it.

A valid independent-review P1 found that renderer dictionaries containing links could previously be accepted without proving complete usable HTML. The current branch fixes that: rendered links can contribute a completed comparison only when the observation is an explicit successful 2xx `usable_html` page with no challenge/block/rate-limit marker, fetch error, truncation or incomplete evidence. Rejected evidence remains failed/unassessed.

Prior B12 shared-caller checkpoint `d612ceade6fc31ecd3e01d5b195dbd4d646524ef` passed CI `35483256047` with 115 root tests and 1,932 scanner-api tests / 18 skips. The current `fe3d18c...` exact-head CI includes the renderer-acceptance fix plus the later B13/B14 work.

Detailed B12 plan: `docs/superpowers/plans/2026-09-20-stage2-b12-hub-render-evidence.md`.

### B13/B14 — current slice

B13 page-level structured local-entity evidence is now produced from accepted usable HTML. The producer is bounded and versioned, currently using conservative LocalBusiness/Store-family JSON-LD. It records name, address, phone, explicit regular hours when present, schema type, entity ID and optional holiday-hours/photos/sameAs/parent presence. Missing regular hours with unknown applicability remains `not_verified`; optional fields are not universal defects. Malformed/oversized structured data and unusable HTTP pages fail closed.

B14 is intentionally stricter than B13 completeness:

- only an explicit absolute HTTP(S) JSON-LD `@id` is currently verified for cross-page identity;
- relative/fragment IDs such as `#store` are retained but unverified until trusted base resolution exists;
- shared names, addresses, phones and page-family similarity never prove identity;
- the same verified entity ID must appear on at least two distinct page URLs before NAP consistency can pass or fail;
- a single observation cannot be a cross-page pass;
- duplicate/conflicting JSON-LD on one page cannot become a false cross-page inconsistency;
- distinct explicit IDs remain separate even with a shared phone;
- `sitewide_consistency_claim` is false.

Focused regressions are in `scanner-api/tests/test_stage2_local_entity_producer.py` and `scanner-api/tests/test_stage2_local_entity_identity.py`.

Intermediate B14 cross-page head `b513c6c7a47e39d792b342f15d6ff31025f5d099` passed CI `35484212032` with 115 root tests and 1,950 scanner-api tests / 18 skips. Final exact executable head `fe3d18c...` adds the relative-ID fail-closed hardening and passed 115 root + 1,952 scanner-api / 18 skips.

Detailed checkpoint: `docs/superpowers/plans/2026-09-20-stage2-b13-b14-local-entity.md`.

B13/B14 are **not source-complete**: page-level observations and the bounded scan aggregation helper exist, but the scan-level summary is not yet attached to the shared `run_scan`/authority result. No new B13/B14 repair/card/export or score change is introduced by this slice. Generic visible-text/store-form identity, complete Coming Soon inference and complete store-finder/form parity are not claimed.

### B16–B18

- B16 exact URL-variant identity is integrated; no sibling-host expansion or duplicate claim occurs without independent equivalence evidence.
- B17 decoded HTML bytes and inline script/style bytes are separated. Direct transfer bytes are still open and must not be replaced by decoded bytes or zero. Optional CrUX must expose disconnected/stale/unavailable states unless current authorized evidence exists.
- B18 optional GSC remains open with explicit disconnected/stale/unavailable behavior required unless a current owner-authorized response exists.

## Stage 2 remains open

Do not start shared Stage-3 integration yet. Remaining serialized work:

1. attach bounded B13/B14 scan-level evidence to the shared scanner result/authority path without changing the assessed page set or request budget;
2. obtain current independent review of the combined B11–B14 shape and close any concrete findings with regressions;
3. implement B15 current-content intent + current-scoped temporal evidence; an old date alone cannot fail freshness;
4. add direct B17 transfer-byte evidence and conservative optional CrUX states;
5. add B18 optional GSC states;
6. preserve exact B09 sitemap provenance if/when exposed downstream;
7. add real producer → Review → signed authority → persisted rows → verified customer/card/handoff/export coverage for every newly displayed evidence/count/finding;
8. require final combined independent review and exact-head CI before recording B06–B18 complete.

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

Remain on Stage 2. Wire the bounded B13/B14 aggregation into the shared scanner result/authority path, preserving the current evidence-only semantics and no-customer-claim boundary. Request focused independent review of the current B11–B14 combined shape. Then continue B15/B17 transfer/B18 in serialized slices with exact-head CI and authenticated downstream coverage for anything customer-visible.
