# Blueprint implementation checkpoint

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`.

This is the current serialized handoff for the FixList full-scanner blueprint. Historical checkpoints remain in Git history and the linked executable plans. The approved spec controls over older handoff paraphrases.

## Release boundary

- Stage-1 publication/promotion/live non-owner acceptance remains owned by the existing exact-source release operator.
- `main` was reverified on 2026-09-20 at `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad`; the Stage-1 freeze remains intact.
- Do not use the later-stage integration branch to publish, promote worker traffic, mutate admission, run a competing production scan, rebuild the release, change schema/secrets or otherwise move production.
- Later-stage integration remains on `agent/full-blueprint-stage2-coverage-b06-20260919`, PR #303.
- After Stage-1 live acceptance, reconcile this branch onto the then-current accepted `main` without reverting V7 route/public-build changes or #308, then run fresh exact-head combined CI.

## Current Stage-2 executable checkpoint

Exact executable head: `910206d34a298ab840cf610542a55809a76b0115`.

FixList CI `35490060294` — **SUCCESS** on both jobs:

- immutable checkout verified the exact SHA;
- root scanner regressions: **115 passed**;
- `scanner-api`: **1,978 passed / 18 intentional skips**;
- new shared disconnected-provider result/authority regressions: **3 passed**;
- existing connected-provider contract regressions: **7 passed**;
- direct B17 transfer-body regressions: **4 passed**;
- labelled Stage-1 corpus: `synthetic`, 14 cases / 55 assertions, `full_30_site_gate=not_assessed`;
- frozen scanner revision `01ebe8e90df1e6bd`: passed;
- production scanner image: `sha256:afc5d05e3a0c36639b02c40de8545d87d3d897711969c17e13029f01c6ee9ba1`;
- lint, typecheck, generated release contracts, frontend contract tests and production frontend build: passed.

The workflow installed Node `20.20.2`; do not describe this checkpoint as Node `20.19.5` runtime evidence.

Direct transfer-byte checkpoint immediately below it: `b915e3846aa2a94da7acbe0b59be7e22c4b3051d`, FixList CI `35489000795` — SUCCESS.

## Stage-2 material state

### B06–B10

- B06 shared finite coverage scheduler / unsampled internal-link verification is integrated with authenticated downstream proof.
- B07 active soft-404 orchestration is integrated through the same finite scheduler; blocked/challenged/robots/budget/deadline/incomplete evidence remains unknown.
- B08 redirect meaning distinguishes harmless normalization, usable, wrong/catch-all, unusable and unverified access. Challenge/block/rate-limit evidence remains unknown.
- B09 sitemap integrity shares the same scheduler. If promoted to customer findings, exact root/child provenance and child failure reasons must survive the downstream chain.
- B10 accepted main-content evidence is integrated. Raw substantive page copy is not retained; bounded deterministic fingerprint/signature evidence is used. If near-duplicate evidence becomes customer-visible, add authenticated downstream/privacy proof before exposure.

### B11/B12

B11 produces sample-scoped depth/inlink/navigation provenance on the real retained Standard-150 set after the final cap. Exact retained edges only; sitemap discovery cannot become an inlink; challenged/unusable sources are re-gated out; unsampled targets cannot expand the assessed set; `sitewide_orphan_claim` remains false. The private retained-link cache is removed before persistence/customer projection.

B12 reuses retained-link evidence and the existing bounded browser-followup observations. Up to five hubs may be selected for disclosure while execution remains under the existing three-page followup ceiling. Rendered links count only from successful accepted 2xx `usable_html` observations without challenge/block/rate-limit/fetch-error/truncation state; other render states remain failed/unassessed.

### B13/B14

B13 accepted usable HTML produces bounded versioned JSON-LD LocalBusiness/Store-family observations for explicitly present name/address/phone/regular-hours/schema/entity-id plus optional fields. Malformed/oversized/unusable evidence fails closed and optional absence is not a universal defect.

B14 cross-page identity remains conservative:

- only explicit absolute HTTP(S) JSON-LD `@id` is currently verified for cross-page identity;
- relative/fragment IDs remain unverified without trusted document-base resolution;
- matching names/addresses/phones or page-family similarity never prove identity;
- the same verified ID must occur on at least two distinct page URLs before consistency can pass/fail;
- same-page duplicate/conflicting JSON-LD cannot become cross-page proof;
- distinct explicit IDs stay separate even with a shared phone;
- `sitewide_consistency_claim` remains false.

The bounded scan aggregate is attached to the shared result and `technical_audit_summary`, so the existing authority payload authenticates it. It remains evidence-only: no customer repair/card/export or score change was introduced.

B13/B14 still do **not** claim generic visible-text/store-form identity, complete Coming Soon/open/closed inference, or complete store-finder/form/sitemap entity parity. Those spec portions remain open until explicit provenance is implemented.

Detailed checkpoint: `docs/superpowers/plans/2026-09-20-stage2-b13-b14-local-entity.md`.

### B15

Contextual freshness is produced on the retained-page evidence seam. A fail requires explicit current-content intent plus contradictory current-scoped temporal evidence. Old articles/years/dated paths alone cannot fail; archive/history wording remains historical; `apply now` is not current-content intent; year-only dates use 31 December conservatively. This remains evidence-only with no repair/card/score change or new fetch.

Detailed checkpoint: `docs/superpowers/plans/2026-09-20-stage2-b15-contextual-freshness.md`.

### B16–B18 — current integrated state

- B16 exact URL-variant identity is integrated; no sibling-host expansion or duplicate claim occurs without independent equivalence evidence.
- B17 decoded HTML and inline script/style bytes are separated. Transfer-body payload bytes are now directly measured from `httpx` raw chunks before content decoding, never inferred from `Content-Length` or decoded HTML, and remote responses cannot spoof the internal measurement. Access-limited pages remain unknown. Ordinary scans authenticate CrUX as disconnected with no metrics/fabricated scan identity. Controlled exact-scan connected/stale/unavailable CrUX shapes are tested; no live connection is claimed.
- B18 ordinary scans now authenticate GSC as disconnected with `provider_data_admitted=false`, no metrics and only the exact retained assessed URL count. Controlled exact-scan connected/stale/unavailable GSC shapes are tested, including authorization, exact scan identity, exact retained URL membership, conflicting-duplicate rejection and the Standard-150 ceiling. No live GSC connection or traffic/indexing claim is made.

Detailed checkpoints:

- `docs/superpowers/plans/2026-09-20-stage2-connected-provider-evidence.md`
- `docs/superpowers/plans/2026-09-20-stage2-transfer-body-evidence.md`
- `docs/superpowers/plans/2026-09-20-stage2-provider-result-integration.md`

## Stage 2 remains open

Do not start shared Stage-3 integration yet. Remaining serialized work:

1. close the remaining B13/B14 explicit-provenance gap for contextual Coming Soon/open/closed and store-finder/form/sitemap entity evidence without inferring identity from matching NAP strings;
2. preserve exact B09 sitemap provenance if/when exposed downstream;
3. add real producer → Review → signed authority → persisted rows → verified customer/card/handoff/export coverage for every newly displayed B09/B10–B18 evidence/count/finding; evidence-only internal fields do not require inventing customer output;
4. obtain a fresh independent review of the combined B06–B18 source shape and close material findings with regressions;
5. require final fresh exact-head CI after review corrections before recording Stage 2 complete.

The optional-provider blueprint gate is satisfied only at the source/contract level here: disconnected behavior and controlled connected-response behavior are tested. No account-specific live connection is claimed or required for an otherwise valid scan.

## Stage 3 — isolated lanes built, not shared-integrated

Reuse these lanes only after Stage 2 closes:

- `agent/stage3-b19-b20-decisions-20260919` / head `e74d87acd0cec2955402b96f635f13bc275f3a91`: B19 impact × reach × page value × confidence and B20 explicit evidenced SEO/GEO root causes. Lane CI `35463839728` passed.
- `agent/stage3-b21-b24-delivery-20260919` / head `a998b4e38a06d6c163ac8853c3e49e9f10a58cb7`: B21 exact unions/rank-before-truncate, B22 authenticated private preview selection, B23 evidenced root-cause score caps preserving existing ceilings, B24 backward-compatible handoff v2. Lane CI `35463511347` passed.

These are integration-ready inputs, not source-complete product behavior. Python Review remains canonical ranking authority. Shared ranking/authority/persistence/customer interfaces remain serialized integration work.

## Stage 4 — isolated lane built, not released

Reuse `agent/stage4-b25-b28-compat-release-20260919` / head `d2ce905ff67410586f86e38bafd93ce4e998e4d1` only after Stage 3 shared integration. Lane CI `35464436789` passed but does not constitute live acceptance.

Spec numbering controls:

- B25 named synthetic corpus + genuine provenance-labelled 30-site baseline/candidate gate;
- B26 reproduced own-site serving defects/fixes;
- B27 GEO/historical HMAC/reader/tamper/privacy compatibility;
- B28 exact-source review/CI/deployment/live customer acceptance.

The genuine 30-site gate remains **not assessed**. Historical summaries and synthetic fixtures cannot become a pass. No Stage-4 deployment, live customer scan or acceptance has been run by this integration branch.

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

Remain on Stage 2. Implement the remaining B13/B14 explicit-provenance cases conservatively, then obtain a fresh independent whole-stage review and exact-head CI. Do not begin Stage-3 shared integration until B06–B18 are genuinely complete, independently reviewed and green.
