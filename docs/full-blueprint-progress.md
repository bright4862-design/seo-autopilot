# Full blueprint progress

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`.

This is the current requirement ledger. Historical checkpoints remain in Git history and executable plans under `docs/superpowers/plans/`. The approved spec controls over older handoff paraphrases.

## Release sequencing and Stage-1 freeze

Stage 1 and the later blueprint remain distinct release states.

- Stage-1 source is merged on `main`; exact-source publication/promotion and fresh non-owner production acceptance remain a separate guarded operation.
- `main` was freshly verified at `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad`, containing the V7 runtime/public-build changes and durable ownership-before-admission fix #308.
- Later-stage integration remains on `agent/full-blueprint-stage2-coverage-b06-20260919`, PR #303.
- Do **not** merge later-stage work to `main`, publish Base44, promote worker traffic, mutate admission, run a competing production scan, rebuild the release, change schema/secrets, or otherwise move production while the Stage-1 release operator owns that cutover.
- After Stage-1 live acceptance is recorded, reconcile this integration branch onto the then-current accepted `main` without reverting V7 or #308, then require fresh exact-head integrated CI.

## Stage 1 — source complete; live release acceptance separate

Stage 1 established published-route evidence identity, authenticated authority/persistence/readers, image/template/search-evidence correctness, historical signature compatibility, preview privacy, and the named synthetic acceptance runner.

Historical detail: `docs/stage-one-evidence-acceptance.md`.

The labelled corpus is explicitly synthetic and cannot satisfy the genuine B25 30-site gate. The frozen scanner revision checked by later-stage CI remains `01ebe8e90df1e6bd`.

## Stage 2 — B06–B18 source integrated; corrected after fresh independent review; final re-review still open

Integration surface: PR #303 / `agent/full-blueprint-stage2-coverage-b06-20260919`.

The isolated Stage-2 lane PRs were CI/review inputs only and must not be merged directly to `main`.

### Requirement status

- **B06 — shared bounded coverage scheduler/internal-link verification:** integrated. One finite follow-up scheduler reuses hardened robots/DNS/SSRF/redirect/body/deadline controls. Probe-only URLs never enter the Standard-150 assessed set or denominator. Verified unsampled broken-link evidence has authenticated downstream coverage.
- **B07 — active soft-404:** integrated. Deterministic same-origin/effective-scope missing-page candidates use the shared finite scheduler. Challenge/429/robots/budget/deadline/incomplete states remain unknown. Synthetic probes stay outside assessed pages. Authenticated downstream proof exists.
- **B08 — redirect meaning:** integrated. Harmless normalization, usable destination, wrong/catch-all destination, unusable destination and unverified access are distinct. Challenged/rate-limited destinations remain unknown; a verified ordinary 404 remains unusable.
- **B09 — sitemap integrity:** source/helper/probe integration uses the same finite scheduler. If later promoted into customer findings, exact root/child provenance and failure reasons must survive the authenticated downstream chain; Stage 2 does not invent a customer finding merely to expose internal evidence.
- **B10 — near-duplicate main content:** accepted main-content seam is integrated. Common chrome is excluded; raw substantive copy is not retained; bounded deterministic SHA-256 shingle fingerprints/signature metadata support conservative internal analysis. These fingerprints are producer-only and are projected out before HTTP/authority/persistence boundaries. Any future customer-visible duplicate finding requires explicit authenticated downstream/privacy proof.
- **B11 — money-page reachability:** integrated on the final retained Standard-150 set. Only exact retained internal edges contribute. Sitemap discovery cannot become an inlink; challenged/unusable sources are re-gated out; unsampled links cannot expand the assessed set; `sitewide_orphan_claim=false`. The private `_reachability_links` cache is removed before publication and denied again at the external projection boundary.
- **B12 — raw/rendered hub links:** integrated. Up to five eligible hubs can be represented while browser execution remains inside the existing three-page follow-up ceiling. Only accepted successful render evidence completes a pair; failed/unassessed states remain explicit; rendered links cannot expand Standard 150.
- **B13 — local entity completeness/status:** integrated as evidence-only. Accepted usable HTML produces bounded JSON-LD observations. Explicit structured status or conservative accepted title/H1 language can establish open/closed/Coming Soon; arbitrary body wording cannot. Regular-hours applicability stays contextual. Raw identity/contact observations are internal; the external aggregate is a positive-allowlisted state/count proof.
- **B14 — cross-page NAP/source provenance:** integrated conservatively as evidence-only. Cross-page identity requires the same explicit absolute HTTP(S) JSON-LD `@id` on at least two distinct page URLs. Matching NAP/family never proves identity. Form/store-finder evidence counts only with the already-verified entity ID; sitemap provenance comes only from retained discovery evidence. `sitewide_consistency_claim=false`. Exact entity keys/page URLs/status-heading provenance and unknown future aggregate/debug fields are denied externally.
- **B15 — contextual freshness:** integrated as evidence-only. A fail requires current-content intent plus contradictory current-scoped temporal evidence. Old articles, old years and dated paths alone cannot fail. Historical/archive evidence remains historical. Year-only dates use 31 December conservatively. Per-page freshness producer evidence stays internal pending an explicit customer contract.
- **B16 — URL variants:** integrated. Exact path/query/case/reserved-escape/empty-query identity is retained. No implicit sibling-host expansion and no duplicate claim without independent equivalence evidence; redirect meaning delegates to B08.
- **B17 — page weight + optional CrUX:** integrated. Decoded HTML, inline script/style and transfer-body bytes remain distinct. Transfer bytes are measured from raw response chunks before decoding, never inferred from `Content-Length`, and remain unknown on access-limited pages. Ordinary scans authenticate CrUX as disconnected. Controlled connected evidence requires owner authorization, exact scan identity and valid observation time; stale, missing or future-dated observations fail closed. No live provider connection is claimed.
- **B18 — optional GSC:** integrated at source/contract level. Ordinary scans authenticate GSC as disconnected with `provider_data_admitted=false`. Controlled connected evidence requires owner authorization, exact scan identity, exact retained-URL membership, conflict rejection, Standard-150 ceiling and valid observation time. Stale, missing and future-dated evidence remains non-current. No live GSC connection or traffic/indexing claim is made.

### Whole-stage review history and corrections

Earlier combined review found a material P1 boundary leak: B10 content fingerprints and B13 raw local-entity observations could cross output/authority handling. A common post-crawl projection fixed the known shape at `e42151d4f10007f4f1660de4a2bbda927a4696eb` with four boundary regressions.

A subsequent serialized review found future B13/B14 aggregate keys were fail-open. RED commit `661b9e2121c6f49bd50dedc64bdce1c73cf54b6b` made CI `35495870104` fail as intended; correction `fda78e9aa4fe823e2067837041f3cba538712f3b` changed aggregate/completeness/NAP/inconsistency projection to positive allowlists and passed exact-head CI `35495894222`.

A **fresh independent CodeRabbit follow-up review** then found two further material P1 issues:

1. the direct authority/signing helpers (`build_authority_review_payload`, `build_completion_envelope`, `build_limited_envelope`) trusted callers to have already projected private Stage-2 producer fields; a direct/internal caller could therefore re-sign private B10/B11/B13/B15 fields;
2. optional CrUX/GSC adapters rejected stale data but did not reject an `observed_at` later than the scan's `as_of` date, allowing future provider observations to be treated as current.

RED reproduction commit: `bea5d3d8a1ec5d7f77d7f68ca4919a45226ded42`.

- Added `scanner-api/tests/test_stage2_followup_review_regressions.py` with three behavioral regressions for direct authority projection, completion/limited signed-envelope projection, and future-dated CrUX/GSC rejection.
- FixList CI `35498446283`: root **115 passed**; `scanner-api` **3 failed / 1,990 passed / 18 skipped**; the three new regressions were the intended failures. The separate lint/typecheck/contracts/frontend-build job passed.

Corrections:

- `12d6c7a24b68a681cd9a5d1a0b78a996ae23edaa`: CrUX/GSC adapters reject `observed_at > as_of` as `unavailable` with `provider_observation_time_invalid` before stale/current classification.
- `0e5a0ed176d764a9ac78bc2d96833f46a268911d`: connected provider wrappers preserve the normalized invalid-time reason through CrUX/GSC scan evidence.
- `10798d00d1c0e7cc31a6dfaca3cd4fc67abeb354`: direct authority-review, completion and limited-result helpers defensively apply `project_scan_result_for_external_boundary` before sampling, signing or persistence-envelope construction.

Intermediate exact CI `35499222707` on `10798d00...` proved the new follow-up regressions green but exposed one stale compatibility assertion: root **115 passed**; `scanner-api` **1 failed / 1,992 passed / 18 skipped**; lint/typecheck/contracts/frontend build passed. The remaining test still required a signed B13/B14 aggregate to equal the raw internal aggregate, contradicting the privacy contract.

`f8175c496728d806085056a2b79cb42e5a0fc61c` strengthens that compatibility test instead of weakening it: signed authority must retain approved version/count/state diagnostics and provable NAP conflict fields while explicitly excluding exact entity IDs, page URLs, `entity_key`, `page_url` and contextual-status provenance.

Detailed record: `docs/superpowers/plans/2026-09-20-stage2-followup-review-hardening.md`.

### Latest exact executable checkpoint

Exact executable head: `f8175c496728d806085056a2b79cb42e5a0fc61c`.

FixList CI `35499312736` — **SUCCESS** on both jobs:

- immutable checkout: passed;
- root scanner regressions: **115 passed**;
- full `scanner-api`: **1,993 passed / 18 skipped**;
- follow-up authority/privacy and future-provider regressions: passed;
- strengthened B13/B14 signed-authority privacy behavior: passed;
- labelled Stage-1 corpus: `synthetic`, **14 cases / 55 assertions**, `full_30_site_gate=not_assessed`;
- frozen scanner revision `01ebe8e90df1e6bd`: passed;
- production scanner image: passed, SHA `sha256:362269f3c43c8c60e57e32edcb8367b024d3da456d6ca1adb95410f40f9f3715`;
- lint, typecheck, generated release contracts, frontend contract tests and production frontend build: passed.

GitHub Actions requested Node 20 but resolved **Node 20.20.2**. Do not describe this checkpoint as Node 20.19.5 runtime evidence.

Documentation-only commits may sit above this executable head. A documentation head is not executable certification unless its exact SHA separately receives green CI.

### Stage 2 completion gate

Stage 2 is **not yet recorded complete**. The latest independent review's two material P1 findings now have RED reproduction, minimal fixes, behavioral regressions and exact executable green CI. One fresh independent re-review of the corrected stable PR #303 head is still mandatory. If it reports a material issue, reproduce first, make the smallest safe correction and require fresh exact-head CI.

Keep internal evidence-only B09/B10–B18 fields internal unless a deliberate producer → Review → signed authority → persisted rows → customer/card/handoff/export chain is intentionally added. Preserve Standard-150/security/privacy/historical-reader invariants.

No account-specific CrUX/GSC connection is required for an otherwise valid scan. Disconnected behavior plus controlled authorized-response behavior is the current source acceptance contract.

## Stage 3 — isolated lanes built; shared integration held behind Stage 2

Do not duplicate these implementations. Reuse only after Stage 2 closes:

- `agent/stage3-b19-b20-decisions-20260919` @ `e74d87acd0cec2955402b96f635f13bc275f3a91`, CI `35463839728`: B19 exact **impact × reach × page value × confidence** factor evidence/explanations with truthful unknown denominators; B20 explicit evidenced shared root causes across SEO/GEO. Family similarity is not root-cause proof and repair leverage is not a substitute fourth factor.
- `agent/stage3-b21-b24-delivery-20260919` @ `a998b4e38a06d6c163ac8853c3e49e9f10a58cb7`, CI `35463511347`: B21 exact unique unions/count distinctions/rank-before-truncate; B22 authenticated evidence-led private previews; B23 documented evidenced-root-cause score caps preserving incomplete/access ceilings; B24 authenticated backward-compatible handoff v2 with historical v1 compatibility and no exposure of suppressed/operator-only findings.

Python Review remains canonical ranking authority. Shared ranking/authority/persistence/customer integration remains serialized work after Stage 2 closes.

## Stage 4 — isolated compatibility/release lane built; live acceptance not run

`agent/stage4-b25-b28-compat-release-20260919` @ `d2ce905ff67410586f86e38bafd93ce4e998e4d1`, CI `35464436789`, remains isolated implementation input, not release authorization.

Spec numbering controls:

- **B25:** named synthetic corpus plus genuine provenance-labelled 30-site baseline/candidate gate;
- **B26:** reproduced own-site serving defects/fixes with source evidence;
- **B27:** GEO/historical HMAC/reader/tamper/privacy compatibility;
- **B28:** exact-source review/CI/deployment/live acceptance, including runtime identities, rollback and one bounded real customer Standard-150 submit → persistence → exact `scan_id` reload/history → linked rescan verification.

The genuine 30-site baseline/candidate gate remains **not assessed**. Historical summaries and synthetic fixtures cannot satisfy it. No Stage-4 deployment, live customer scan or production acceptance is claimed.

## Hard invariants

- Standard-150 assessed-page cap and truthful denominators remain authoritative.
- Stage-2 follow-up checks share one finite request pool; no second scheduler/budget.
- Robots ownership, DNS/SSRF, redirect, body and deadline protections remain authoritative.
- One active scan/account, cancellation/terminalization and exact scan isolation remain intact.
- Missing, blocked, stale, disconnected, future-dated or otherwise invalid evidence remains unknown/unavailable rather than an invented pass/fail/current state.
- Historical signatures/readers stay compatible; unknown evidence versions fail closed.
- Preview privacy and entitlement boundaries remain intact.
- Python Review remains canonical priority/ranking authority.
- Premium/Grok remain outside this integration.
- Synthetic/historical data never substitutes for the genuine 30-site gate or real customer live acceptance.

## Exact next engineering action

Stabilize the documentation head and require its exact-head FixList CI. Then request one fresh independent re-review of the corrected current PR #303 head. Correct any new material issue with a reproducing regression and fresh exact-head CI. Only after a clean re-review may Stage 2 be recorded complete and serialized Stage-3 B19–B24 integration begin. Do not move production.
