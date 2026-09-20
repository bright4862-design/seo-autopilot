# Blueprint implementation checkpoint

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`.

This is the current serialized handoff for the FixList full-scanner blueprint. Historical checkpoints remain in Git history and linked executable plans. The approved spec controls over older paraphrases.

## Release boundary

- Stage-1 publication/promotion/live non-owner acceptance remains owned by the existing exact-source release operator.
- `main` was freshly verified at `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad`; later-stage work has no authority to move production.
- Do not publish, promote worker traffic, mutate admission, run a competing production scan, rebuild the release, change schema/secrets, or merge the later-stage branch to `main`.
- Later-stage integration remains on `agent/full-blueprint-stage2-coverage-b06-20260919`, PR #303.
- After Stage-1 live acceptance, reconcile onto the then-current accepted `main` without reverting V7 route/public-build changes or #308, then require fresh exact-head integrated CI.

## Current Stage-2 executable checkpoint

Exact executable head: `f8175c496728d806085056a2b79cb42e5a0fc61c`.

FixList CI `35499312736` — **SUCCESS** on both jobs:

- immutable checkout: passed;
- root scanner regressions: **115 passed**;
- full `scanner-api`: **1,993 passed / 18 skipped**;
- Stage-2 follow-up review regressions: passed;
- strengthened B13/B14 signed-authority privacy behavior: passed;
- labelled Stage-1 corpus: `synthetic`, **14 cases / 55 assertions**, `full_30_site_gate=not_assessed`;
- frozen scanner revision `01ebe8e90df1e6bd`: passed;
- production scanner image: passed, SHA `sha256:362269f3c43c8c60e57e32edcb8367b024d3da456d6ca1adb95410f40f9f3715`;
- lint, typecheck, generated release contracts, frontend contract tests and production frontend build: passed.

GitHub Actions requested Node 20 but resolved **Node 20.20.2**. Do not represent this run as Node 20.19.5 evidence.

## Fresh independent-review findings and repair chain

A fresh CodeRabbit follow-up review of the combined Stage-2 surface found two material P1 defects:

1. `build_authority_review_payload`, `build_completion_envelope`, and `build_limited_envelope` did not independently project private Stage-2 producer fields. The normal post-crawl path projected them, but a direct/internal caller could re-sign B10 fingerprints, private B11 link cache, B13 raw entity/contact observations or B15 per-page freshness evidence.
2. CrUX/GSC adapters checked maximum age but did not reject `observed_at > as_of`, so future provider observations could be treated as current.

### RED

`bea5d3d8a1ec5d7f77d7f68ca4919a45226ded42` added three behavioral regressions for those exact findings.

FixList CI `35498446283` failed as intended:

- root: **115 passed**;
- `scanner-api`: **3 failed / 1,990 passed / 18 skipped**;
- the three new regressions were the failures;
- lint/typecheck/contracts/frontend-build job passed.

### Corrections

- `12d6c7a24b68a681cd9a5d1a0b78a996ae23edaa`: CrUX/GSC adapters fail closed on future observation time with `provider_observation_time_invalid`.
- `0e5a0ed176d764a9ac78bc2d96833f46a268911d`: connected provider envelopes preserve the normalized invalid-time reason through scan evidence.
- `10798d00d1c0e7cc31a6dfaca3cd4fc67abeb354`: all direct authority/signing helpers defensively call the external-boundary projection before sampling/signing/persistence-envelope construction.

Intermediate CI `35499222707` on `10798d00...` proved the new review regressions green but exposed one stale compatibility expectation: root **115 passed**, `scanner-api` **1 failed / 1,992 passed / 18 skipped**, build-side job green. The stale test required signed B13/B14 evidence to equal raw internal evidence, contradicting the approved privacy projection.

`f8175c496728d806085056a2b79cb42e5a0fc61c` strengthens that test instead of weakening it: approved version/count/state diagnostics and NAP conflict evidence must survive, while exact entity IDs, page URLs, `entity_key`, `page_url` and contextual-status provenance must not cross the signed authority boundary. Exact-head CI is fully green as recorded above.

Detailed record: `docs/superpowers/plans/2026-09-20-stage2-followup-review-hardening.md`.

## Stage-2 material state

- **B06:** shared finite coverage scheduler / unsampled internal-link verification integrated with authenticated downstream proof.
- **B07:** active soft-404 integrated through that same scheduler; blocked/challenged/robots/budget/deadline/incomplete remains unknown.
- **B08:** redirect meaning distinguishes normalization, usable, wrong/catch-all, unusable and unverified access.
- **B09:** sitemap integrity uses the same finite scheduler; customer promotion still requires exact root/child provenance and authenticated downstream proof.
- **B10:** accepted main-content fingerprints are internal-only and now denied both at common output projection and direct authority/signing helpers.
- **B11:** sample-scoped retained-set depth/inlink/navigation integrated; sitemap cannot masquerade as inlink; no sitewide orphan claim; private link cache denied externally.
- **B12:** paired raw/rendered hub evidence integrated under existing browser-followup ceiling with explicit completed/failed/unassessed states.
- **B13:** contextual local entity/status completeness integrated as evidence-only; raw identity/contact observations remain internal; external aggregate is positive-allowlisted.
- **B14:** explicit absolute HTTP(S) entity identity required across distinct URLs; matching NAP/family never proves identity; external NAP proof is reduced and fail-closed.
- **B15:** contextual freshness integrated as evidence-only; old date alone cannot fail; raw per-page freshness evidence stays internal.
- **B16:** exact URL variant identity integrated; no sibling-host expansion or duplicate claim without verified equivalence.
- **B17:** direct transfer bytes remain distinct from decoded/inline bytes; CrUX defaults disconnected; controlled provider data now rejects stale/missing/future timing.
- **B18:** GSC defaults disconnected; controlled data requires owner authorization, exact scan identity, exact retained URL membership, conflict rejection, Standard-150 ceiling and valid observation time.

## Stage 2 remains open only at corrected-head independent re-review

Do not start shared Stage-3 integration yet. The two latest material review findings have RED reproduction, minimal source fixes, strengthened behavioral coverage and exact executable CI. Remaining gate:

1. stabilize the documentation head and require its exact-head FixList CI;
2. request one fresh independent re-review of the corrected stable PR #303 head;
3. if a material issue appears, reproduce it before correction and require new exact-head CI;
4. if the re-review is clean, record B06–B18 complete and then begin serialized Stage-3 integration.

Keep B09/B10–B18 evidence internal unless a deliberate producer → Review → signed authority → persisted rows → customer/card/handoff/export chain is added. Preserve Standard 150, one finite request budget, robots/DNS/SSRF/redirect/body/deadline protections, one active scan/account, cancellation/terminalization, exact scan isolation, historical signatures/readers, preview privacy and Python Review authority.

## Stage 3 — isolated lanes built, not shared-integrated

Reuse only after Stage 2 closes:

- `agent/stage3-b19-b20-decisions-20260919` / `e74d87acd0cec2955402b96f635f13bc275f3a91`, CI `35463839728`: B19 exact **impact × reach × page value × confidence** with truthful unknown denominators; B20 explicit evidenced SEO/GEO root causes. Family similarity is not root-cause proof; repair leverage is not the fourth factor.
- `agent/stage3-b21-b24-delivery-20260919` / `a998b4e38a06d6c163ac8853c3e49e9f10a58cb7`, CI `35463511347`: B21 exact unique unions/counts/rank-before-truncate; B22 authenticated private previews; B23 evidenced root-cause score caps preserving incomplete/access ceilings; B24 authenticated handoff v2 with v1 compatibility and no suppressed/operator-only exposure.

Python Review remains canonical ranking authority. Shared ranking/authority/persistence/customer interfaces remain serialized integration work.

## Stage 4 — isolated lane built, not released

Reuse `agent/stage4-b25-b28-compat-release-20260919` / `d2ce905ff67410586f86e38bafd93ce4e998e4d1`, CI `35464436789`, only after Stage 3 shared integration.

Spec numbering controls:

- **B25:** named synthetic corpus + genuine provenance-labelled 30-site baseline/candidate gate;
- **B26:** reproduced own-site serving defects/fixes;
- **B27:** GEO/historical HMAC/reader/tamper/privacy compatibility;
- **B28:** exact-source review/CI/deployment/live customer acceptance.

The genuine 30-site gate remains **not assessed**. Historical summaries and synthetic fixtures cannot become a pass. No Stage-4 deployment, live customer scan or acceptance has been run by this integration branch.

## Exact next action

Wait for exact-head CI on the final persisted documentation head, then request one fresh independent re-review of that stable PR #303 head. If clean, record Stage 2 complete and begin serialized integration of the existing B19/B20 and B21–B24 deltas. Do not move production.
