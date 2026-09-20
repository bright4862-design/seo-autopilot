# Blueprint implementation checkpoint

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`.

This is the current serialized handoff for the FixList full-scanner blueprint. Historical checkpoints remain in Git history and the linked executable plans. The approved spec controls over older handoff paraphrases.

## Release boundary

- Stage-1 publication/promotion/live non-owner acceptance remains owned by the existing exact-source release operator.
- `main` was last accepted for this later-stage work at `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad`; newer repository metadata is not authorization to move the Stage-1 cutover.
- Do not use the later-stage integration branch to publish, promote worker traffic, mutate admission, run a competing production scan, rebuild the release, change schema/secrets or otherwise move production.
- Later-stage integration remains on `agent/full-blueprint-stage2-coverage-b06-20260919`, PR #303.
- After Stage-1 live acceptance, reconcile this branch onto the then-current accepted `main` without reverting V7 route/public-build changes or #308, then run fresh exact-head combined CI.

## Current Stage-2 executable checkpoint

Exact executable head: `e42151d4f10007f4f1660de4a2bbda927a4696eb`.

FixList CI `35493637000` — **SUCCESS** on both jobs:

- immutable checkout verified the exact SHA;
- CI runner: Ubuntu 24.04.5 / Python 3.12.14;
- Node 20 setup resolved **20.20.2**; do not cite this run as Node 20.19.5 runtime evidence;
- root scanner regressions: **115 passed**;
- full scanner-api: **1,988 passed / 18 intentional skips** (2,006 collected), including **4 new output-privacy regressions**;
- labelled Stage-1 corpus: synthetic, **14 cases / 55 assertions**, `full_30_site_gate=not_assessed`;
- frozen scanner revision `01ebe8e90df1e6bd` passed;
- production scanner image built as `sha256:ace9b08b88ea3c29faecc00cc0c9567deb9687cc90f1c503723bcd73f80a86dc`;
- lint, typecheck, generated release contracts, frontend contract tests and production frontend build passed.

Documentation-only commits now sit above the executable checkpoint. Keep executable certification attached to `e42151d...` unless a later exact head separately receives green CI.

## Fresh independent whole-stage review correction

The fresh combined B06–B18 CodeRabbit review identified one material P1 privacy/authority-boundary defect in prior executable checkpoint `e906ef69c7b7deab3a1014c702b4f3af1453c54c`: B10 deterministic main-content fingerprint intermediates and B13 normalized local-entity observations were still present on page dictionaries forwarded into synchronous output and durable authority handling.

The issue is now reproduced and corrected:

- `scanner-api/app/page_output_privacy.py` defines a fail-closed external projection for B10 producer fingerprints/signatures/count/source fields, B13/B14 raw observations/location context, B15 per-page contextual-freshness evidence and the defensive B11 `_reachability_links` cache.
- `scanner-api/app/render_evidence_quality.py` applies the projection at the final common post-crawl seam after B13/B14 scan aggregation has consumed retained-page evidence but before synchronous output and durable authority handling.
- The B13/B14 scan aggregate is itself reduced to non-content states/counts. Exact page URLs, entity IDs and accepted-heading status provenance are removed; NAP inconsistencies retain only field names, source count and provenance rather than the entity key.
- The projection does not mutate the producer input and preserves ordinary page evidence needed by current customer/Review contracts, including exact page URL/title/status and directly measured transfer-byte evidence.

`scanner-api/tests/test_stage2_output_privacy.py` uses distinctive B10 shingle/signature/source-text, entity ID/name/address/phone/hours, B15 intent and private-link sentinels. Four regressions prove those values cannot escape through the common post-crawl result, response-budget projection, authority review payload, or signed completion/limited-result envelopes.

Detailed checkpoint: `docs/superpowers/plans/2026-09-20-stage2-output-privacy-hardening.md`.

## Stage-2 material state

### B06–B10

- B06 shared finite coverage scheduler / unsampled internal-link verification is integrated with authenticated downstream proof.
- B07 active soft-404 orchestration is integrated through the same finite scheduler; blocked/challenged/robots/budget/deadline/incomplete evidence remains unknown.
- B08 redirect meaning distinguishes harmless normalization, usable, wrong/catch-all, unusable and unverified access. Challenge/block/rate-limit evidence remains unknown.
- B09 sitemap integrity shares the same scheduler. If promoted to customer findings, exact root/child provenance and child failure reasons must survive the downstream chain.
- B10 accepted main-content evidence is integrated. Raw substantive page copy is not retained; bounded deterministic fingerprint/signature evidence is internal-only and is now stripped before HTTP/authority/persistence boundaries. If near-duplicate evidence becomes customer-visible later, add authenticated downstream/privacy proof before exposure.

### B11/B12

B11 produces sample-scoped depth/inlink/navigation provenance on the real retained Standard-150 set after the final cap. Exact retained edges only; sitemap discovery cannot become an inlink; challenged/unusable sources are re-gated out; unsampled targets cannot expand the assessed set; `sitewide_orphan_claim=false`. The private retained-link cache is removed before persistence/customer projection and denied at the common boundary as defense in depth.

B12 reuses retained-link evidence and the existing bounded browser-followup observations. Up to five hubs may be selected for disclosure while execution remains under the existing three-page followup ceiling. Rendered links count only from successful accepted 2xx `usable_html` observations without challenge/block/rate-limit/fetch-error/truncation state; other render states remain failed/unassessed.

### B13/B14

B13 accepted usable HTML produces bounded JSON-LD LocalBusiness/Store-family observations with versioned explicit status/source provenance. Machine status or conservative accepted title/H1 can establish open/closed/Coming Soon; arbitrary body wording cannot. Missing regular hours are non-defective for verified Coming Soon/closed, applicable for verified open, and unknown when applicability is unknown.

B14 stays deliberately strict: only explicit absolute HTTP(S) JSON-LD `@id` on at least two distinct page URLs proves cross-page comparison identity. Relative/fragment IDs remain unverified without trusted base resolution; matching names/addresses/phones or family never prove identity; distinct explicit IDs stay separate; `sitewide_consistency_claim=false`. Form/store-finder/sitemap references remain provenance only and cannot promote identity.

Raw local observations/contact identity no longer cross the output/authority boundary. The scan aggregate survives only as a reduced non-content state/count summary.

### B15

Contextual freshness is produced on the retained-page evidence seam. A fail requires explicit current-content intent plus contradictory current-scoped temporal evidence. Old articles/years/dated paths alone cannot fail; archive/history wording remains historical; `apply now` is not current-content intent; year-only dates use 31 December conservatively. Per-page producer evidence is now stripped before external boundaries until an authenticated downstream contract exists.

### B16–B18

- B16 exact URL-variant identity is integrated; no sibling-host expansion or duplicate claim without independent equivalence evidence.
- B17 decoded HTML and inline script/style bytes are separate from directly measured raw transfer-body payload bytes. Transfer bytes are measured before content decoding, never inferred from `Content-Length`, cannot be spoofed by a remote internal header, and remain unknown on access-limited pages. Ordinary scans authenticate CrUX as disconnected; controlled authorized/current/stale/unavailable shapes are tested. No live provider connection is claimed.
- B18 ordinary scans authenticate GSC as disconnected with `provider_data_admitted=false`, no metrics and exact retained assessed-URL count. Controlled connected/stale/unavailable shapes require authorization, exact scan identity, exact retained URL membership, conflict rejection and the Standard-150 ceiling. No live GSC connection or traffic/indexing claim is made.

## Stage 2 remains open at follow-up independent review

Do not start shared Stage-3 integration yet. The material fresh review P1 has been reproduced, fixed and exact-head CI green. Remaining serialized gate:

1. obtain a fresh independent follow-up review of the corrected current B06–B18 source shape;
2. if any new material issue is reported, reproduce it with a behavioral regression and apply the smallest safe correction;
3. require fresh exact-head FixList CI after any further executable correction;
4. keep evidence-only B09/B10–B18 fields internal unless an intentional producer → Review → signed authority → persisted rows → customer/card/handoff/export chain is added;
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

Stay on Stage 2 for fresh independent follow-up review of executable head `e42151d4f10007f4f1660de4a2bbda927a4696eb` and the privacy correction. Fix any new material finding with behavioral regressions and fresh exact-head CI. Only then begin serialized Stage-3 shared integration.
