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

Exact executable head: `e906ef69c7b7deab3a1014c702b4f3af1453c54c`.

FixList CI `35490908086` — **SUCCESS** on both jobs:

- immutable checkout verified the exact SHA;
- root scanner regression step passed;
- full scanner-api suite passed, including six new B13/B14 explicit-provenance regressions; relative to the prior 1,978-test checkpoint this is 1,984 passed / 18 intentional skips;
- labelled Stage-1 synthetic corpus passed and remains synthetic; `full_30_site_gate=not_assessed` remains unchanged;
- frozen scanner revision check passed;
- production scanner image build passed;
- lint, typecheck, generated release contracts, frontend contract tests and production frontend build passed.

Documentation-only commits now sit above the executable checkpoint. Keep code certification attached to `e906ef69...` unless a later exact head also receives green CI.

## Stage-2 material state

### B06–B10

- B06 shared finite coverage scheduler / unsampled internal-link verification is integrated with authenticated downstream proof.
- B07 active soft-404 orchestration is integrated through the same finite scheduler; blocked/challenged/robots/budget/deadline/incomplete evidence remains unknown.
- B08 redirect meaning distinguishes harmless normalization, usable, wrong/catch-all, unusable and unverified access. Challenge/block/rate-limit evidence remains unknown.
- B09 sitemap integrity shares the same scheduler. If promoted to customer findings, exact root/child provenance and child failure reasons must survive the downstream chain.
- B10 accepted main-content evidence is integrated. Raw substantive page copy is not retained; bounded deterministic fingerprint/signature evidence is used. If near-duplicate evidence becomes customer-visible, add authenticated downstream/privacy proof before exposure.

### B11/B12

B11 produces sample-scoped depth/inlink/navigation provenance on the real retained Standard-150 set after the final cap. Exact retained edges only; sitemap discovery cannot become an inlink; challenged/unusable sources are re-gated out; unsampled targets cannot expand the assessed set; `sitewide_orphan_claim=false`. The private retained-link cache is removed before persistence/customer projection.

B12 reuses retained-link evidence and the existing bounded browser-followup observations. Up to five hubs may be selected for disclosure while execution remains under the existing three-page followup ceiling. Rendered links count only from successful accepted 2xx `usable_html` observations without challenge/block/rate-limit/fetch-error/truncation state; other render states remain failed/unassessed.

### B13/B14 — explicit provenance slice complete at source level

B13 accepted usable HTML produces bounded JSON-LD LocalBusiness/Store-family observations. The producer now retains versioned status/source provenance without introducing a second fetch:

- explicit machine status (`businessStatus`, `openingStatus`, `status`) may establish `coming_soon`, `open` or `closed` when the value maps unambiguously;
- otherwise a conservative accepted title/H1 phrase such as Coming Soon, Opening Soon, Now Open, Temporarily Closed or Permanently Closed may establish context;
- arbitrary body text does not establish business status;
- missing regular hours are non-defective for verified Coming Soon/closed, applicable for verified open, and unknown when applicability is unknown.

B14 remains deliberately strict about identity:

- only explicit absolute HTTP(S) JSON-LD `@id` is verified for cross-page identity;
- relative/fragment IDs remain unverified without trusted document-base resolution;
- matching names/addresses/phones or page-family similarity never prove identity;
- the same verified ID must occur on at least two distinct page URLs before consistency can pass/fail;
- same-page duplicate/conflicting JSON-LD cannot become cross-page proof;
- distinct explicit IDs stay separate even with a shared phone;
- `sitewide_consistency_claim=false`.

Source provenance is now recorded conservatively:

- a form contributes `form_explicit_entity_id` only when it contains the exact already-verified entity ID in an explicit entity/location/store ID field/attribute;
- a store-finder/locator contributes `store_finder_explicit_entity_id` only when an explicit finder marker and exact already-verified entity ID occur together;
- `sitemap_reference` is added only from the retained page's real `discovered_from` evidence during scan aggregation;
- none of these sources can promote a missing/unverified identity.

The bounded scan aggregate remains attached to the shared result and authenticated `technical_audit_summary`. It is evidence-only: no new repair/card/export/score/preview surface was introduced.

Detailed checkpoint: `docs/superpowers/plans/2026-09-20-stage2-b13-b14-local-entity.md`.

### B15

Contextual freshness is produced on the retained-page evidence seam. A fail requires explicit current-content intent plus contradictory current-scoped temporal evidence. Old articles/years/dated paths alone cannot fail; archive/history wording remains historical; `apply now` is not current-content intent; year-only dates use 31 December conservatively. Evidence-only, no new fetch or customer repair.

### B16–B18

- B16 exact URL-variant identity is integrated; no sibling-host expansion or duplicate claim without independent equivalence evidence.
- B17 decoded HTML and inline script/style bytes are separate from directly measured raw transfer-body payload bytes. Transfer bytes are measured before content decoding, never inferred from `Content-Length`, cannot be spoofed by a remote internal header, and remain unknown on access-limited pages. Ordinary scans authenticate CrUX as disconnected; controlled authorized/current/stale/unavailable shapes are tested. No live provider connection is claimed.
- B18 ordinary scans authenticate GSC as disconnected with `provider_data_admitted=false`, no metrics and exact retained assessed-URL count. Controlled connected/stale/unavailable shapes require authorization, exact scan identity, exact retained URL membership, conflict rejection and the Standard-150 ceiling. No live GSC connection or traffic/indexing claim is made.

## Stage 2 remains open only at the final review/certification gate

Do not start shared Stage-3 integration yet. Source implementation for B06–B18 has reached the combined whole-stage review boundary. Remaining serialized work:

1. obtain a fresh independent review of the complete current B06–B18 source shape;
2. reproduce every material review finding with a behavioral regression, then apply the smallest safe correction;
3. require fresh exact-head FixList CI after review corrections, or certify the current source only if the fresh review finds no material issue;
4. keep evidence-only B09/B10–B18 fields internal unless an intentional authenticated customer chain is added; do not invent UI/export output to claim completeness;
5. preserve Standard-150 cap, one finite probe budget, robots/DNS/SSRF/redirect/body/deadline controls, one active scan/account, exact scan isolation, historical signatures/readers, preview privacy and Python Review authority.

The optional-provider gate is source/contract based: disconnected behavior plus controlled connected-response behavior is implemented. A live account-specific provider connection is neither claimed nor required for an otherwise valid scan.

## Stage 3 — isolated lanes built, not shared-integrated

Reuse only after Stage 2 closes:

- `agent/stage3-b19-b20-decisions-20260919` / `e74d87acd0cec2955402b96f635f13bc275f3a91`, CI `35463839728`: B19 impact × reach × page value × confidence and B20 explicit evidenced SEO/GEO root causes. Family similarity is not root-cause proof.
- `agent/stage3-b21-b24-delivery-20260919` / `a998b4e38a06d6c163ac8853c3e49e9f10a58cb7`, CI `35463511347`: B21 exact unions/rank-before-truncate, B22 authenticated private preview selection, B23 evidenced root-cause score caps preserving existing ceilings, B24 backward-compatible handoff v2.

These are integration-ready inputs, not product completion. Python Review remains canonical ranking authority. Shared ranking/authority/persistence/customer interfaces remain serialized integration work.

## Stage 4 — isolated lane built, not released

Reuse `agent/stage4-b25-b28-compat-release-20260919` / `d2ce905ff67410586f86e38bafd93ce4e998e4d1`, CI `35464436789`, only after Stage 3 shared integration.

Spec numbering controls:

- B25 named synthetic corpus + genuine provenance-labelled 30-site baseline/candidate gate;
- B26 reproduced own-site serving defects/fixes;
- B27 GEO/historical HMAC/reader/tamper/privacy compatibility;
- B28 exact-source review/CI/deployment/live customer acceptance.

The genuine 30-site gate remains **not assessed**. Historical summaries and synthetic fixtures cannot become a pass. No Stage-4 deployment, live customer scan or acceptance has been run by this integration branch.

## Exact next action

Stay on Stage 2 for the fresh independent whole-stage B06–B18 review. Fix material findings with behavioral regressions and fresh exact-head CI. Only then begin serialized Stage-3 shared integration.
