# Full blueprint progress

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`.

This is the current requirement ledger. Historical checkpoints remain in Git history and executable plans under `docs/superpowers/plans/`. The approved spec controls over older handoff paraphrases.

## Release sequencing and Stage-1 freeze

Stage 1 and the later blueprint remain distinct release states.

- `main` was refreshed and remains `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad`, containing the V7 runtime/public-build changes and durable ownership-before-admission fix #308.
- `docs/stage-one-evidence-acceptance.md` on current `main` still records the Stage-1 source as an implementation candidate with exact-source production publication and fresh non-owner production acceptance pending. No accepted production report is recorded there.
- Stage-1 exact-source publication/promotion and fresh non-owner production acceptance remain owned by the existing single release operator.
- Later-stage integration remains on `agent/full-blueprint-stage2-coverage-b06-20260919`, PR #303.
- Do **not** merge later-stage work to `main`, publish Base44, promote worker traffic, mutate admission, run a competing production scan, rebuild the release, change schema/secrets, or otherwise move production while the Stage-1 release operator owns that cutover.
- After Stage-1 live acceptance is recorded, reconcile this integration branch onto the then-current accepted `main` without reverting V7 or #308, then require fresh exact-head integrated CI.

The labelled Stage-1 corpus remains explicitly synthetic and cannot satisfy the genuine B25 30-site gate. Frozen scanner revision: `01ebe8e90df1e6bd`.

## Stage 2 — B06–B18 source/review/CI complete on PR #303

Stable corrected Stage-2 head: `10f51529bf5bf64b7b24ab8424f3ae821de46b39`.

Exact-head FixList CI `35500580582` passed. The fresh CodeRabbit follow-up on the corrected fail-closed page-output boundary (PR #303 issue comment `5748778814`, 2026-09-20T08:48:38Z) reviewed the corrected surface and returned `Comments: 0` with no actionable finding. That satisfies the final Stage-2 independent-review gate. Stage 2 is therefore recorded **complete for source integration, independent review and exact-head CI**; this is not a production release claim and does not alter the Stage-1 freeze.

Requirement state:

- **B06:** one finite shared follow-up scheduler / unsampled internal-link verification; probe-only URLs cannot inflate Standard-150 assessed pages or denominators.
- **B07:** active soft-404 orchestration through that same scheduler; challenge/429/robots/budget/deadline/incomplete remains unknown.
- **B08:** redirect meaning distinguishes normalization, usable destination, wrong/catch-all destination, unusable destination and unverified access.
- **B09:** robots-declared sitemap integrity/probes reuse the same finite scheduler with explicit retrieval/probe provenance.
- **B10:** accepted main-content evidence is internal deterministic analysis; raw copy is not retained and private fingerprints are denied at external boundaries.
- **B11:** exact retained-set sample-scoped depth/inlink/navigation; sitemap is not an inlink, challenged sources cannot contribute, unsampled links cannot expand Standard 150, no sitewide-orphan overclaim.
- **B12:** paired raw/rendered hub-link evidence under the existing browser-followup ceiling with completed/failed/unassessed states.
- **B13:** contextual local entity/status completeness; raw identity/contact observations stay internal and external aggregate fields are positive-allowlisted.
- **B14:** cross-page identity requires the same explicit absolute HTTP(S) JSON-LD `@id` on distinct URLs; matching NAP/family never proves identity.
- **B15:** contextual freshness requires current-content intent plus contradictory temporal evidence; old dates alone cannot fail.
- **B16:** exact bounded URL-variant identity/probes; no sibling-host expansion or duplicate claim without verified equivalence.
- **B17:** measured transfer bytes remain distinct from decoded/inline bytes; optional CrUX defaults disconnected and controlled evidence requires owner authorization, exact scan identity and valid observation time.
- **B18:** GSC defaults disconnected; controlled evidence requires owner authorization, exact scan identity, exact retained-URL membership, conflict rejection, Standard-150 ceiling and valid observation time.

The latest Stage-2 privacy hardening remains positive-allowlist/fail-closed for both per-page output and local/NAP aggregates. Unknown future producer/debug fields do not become signed/persisted/customer fields automatically.

## Stage 3 — reviewed lanes integrated serially; B19/B20 reviewed authority seam and corrected B21 signed delivery seam active

The existing isolated lanes were refreshed and copied as exact reviewed deltas; no duplicate worker was launched and no lane PR was merged to `main`.

- B19/B20 source lane `e74d87acd0cec2955402b96f635f13bc275f3a91` was integrated at `c3f9d685e17b26c372a5a47403b478caec36ed2a`.
- B21–B24 source lane `a998b4e38a06d6c163ac8853c3e49e9f10a58cb7` was integrated at `3aebc7375e854ce063c0bcec0a46210473e061c7`.
- Combined exact-head FixList CI `35501672504` passed both jobs.

### B19/B20 shared authority integration

RED commit `ac6ce27b3c492649537d80788f7b02b86ec39e5e` added behavioral regressions for the canonical Review → signed completion seam. FixList CI `35501924104` failed as intended in the scanner regression job while the lint/typecheck/contracts/frontend job stayed green.

GREEN commit `7ba2df83d848fd643bb510374b7da5a18ac749f1` wires B19/B20 into `repair_contract_v2.py` after the existing canonical persistence candidate validator and before Review is signed by the durable completion envelope. Exact-head FixList CI `35501983203` passed both jobs.

The implementation proves:

- **B19 partial shared integration:** final canonical repairs carry versioned exact factors `impact × reach × page value × confidence`, explanations, truthful unknown reach, and the same authenticated envelope as `priority_factors`; repair leverage is not read as a substitute factor.
- **B20 partial shared integration:** explicit root-cause grouping consumes pre-fingerprint rows, can span SEO/GEO and families only with explicit verified evidence, unions affected URLs, and requires an enclosing producer identity with non-empty exact `scan_id == scan_run_id`.
- B19/B20 derived fields are inside the signed Review object. They are **not yet claimed as durable customer FixItem/card/export fields**; persistence/customer projections still require explicit reviewed wiring.

### B20 independent-review P1 correction — closed at the signed-review boundary

Fresh CodeRabbit review identified a material scan-isolation gap after the first shared integration: the root-cause helper could let repair-local `scan_id` / `scan_run_id` replace the trusted producer identity. Two foreign repairs sharing the same local identity could therefore group even when the enclosing producer belonged to another scan.

- RED commit `6f1e2cc3ae519bbb494cab599579758f9efe427a` added foreign-local-identity and matching-local-identity regressions. FixList CI `35503985665` failed in the scanner regression job as intended; the separate build/contracts job passed.
- Fix commit `56a9362ceb9ec1b06b88e26a0fd7db8fff97e92c` made the caller-provided producer identity authoritative. Repair-local IDs are only consistency assertions; a present mismatch forces that member to singleton `not_verified`, and absent trusted producer identity cannot be resurrected locally.
- CI `35504067902` then exposed one stale lane assertion that expected local identity to establish trust without a producer identity. The assertion was strengthened, not weakened.
- Test-semantics commit `cbfd2b1f4a696c209dfab90e3981f42b0cbaa481` now requires missing producer identity to yield untrusted singleton groups even if repairs carry local IDs. Exact-head FixList CI `35504200573` passed both jobs.
- Fresh CodeRabbit follow-up on exact stable head `fb9a22f1284e1381db04186733ebeb32bb4a7e93` (PR #303 issue comment `5749166024`, 2026-09-20T10:14:11Z) reported no unresolved material issue and explicitly rechecked trusted producer identity, repair-local consistency/fail-closed behavior, explicit verified same-root-cause evidence, B19 four-factor semantics, truthful unknown reach and signed-Review preservation.

B20 verified grouping now requires the trusted producer identity plus exact consistency of any repair-local identity on every member. Same family, similarity or repair-local scan IDs alone cannot create trust. The B20 independent-review gate is therefore closed **for the signed Review boundary**; durable FixItem/customer projection remains open, so B20 overall is not yet complete.

Detailed checkpoint: `docs/superpowers/plans/2026-09-20-stage3-signed-b19-b20-integration.md`.

### B21 signed delivery integration and independent-review correction

B21 is wired through the real canonical Review → signed completion boundary rather than remaining an isolated helper.

- Initial fixture `bd8ac740320a3d239f053ba690dfb5e6b67cb41f` was rejected by the pre-existing canonical persistence validator and is not semantic RED evidence.
- Valid RED `513a4438d5622d393bf3031cb2db17f29caa7ee5` / FixList CI `35506946578` failed exactly because `stage3_delivery` was absent at the integrated Review boundary; build/contracts remained green.
- `86cea88d8a90c62a686015fb9fc464fc0dddfd0d` attached per-repair truthful B21 counts and a bounded signed delivery summary.
- CI `35507077795` exposed that legacy `priority_rank` could mask authenticated B19 factor order in the temporary B21 view.
- `d74240b751d9ac1fefe070036397d016a6d074aa` removed `priority_rank` only from that temporary ranking view, preserving canonical historical metadata.
- `e9aa3789b9b143a7b3b8dbdd0e52ad2edf953a0f` corrected the ordering fixture to a family-scoped B19-known candidate rather than fabricating a score for cross-cutting `broken_page`. CI `35507339178` was green.

Fresh CodeRabbit review then identified a material **P1 B19/B21 truncation defect**: the helper could normalize explicit unknown B19 composite score to sortable zero and use impact as the next key, allowing a high-impact unknown repair to displace a repair whose authenticated B19 score was genuinely known as `0.0` at the 36-item cap.

- Regression commit `467fc4aaf184c2cf8ad99e41dc8baa8fd13ac0d2` covered unknown-vs-known-zero ordering.
- Correction `2b952e14ac72f03c42be794540574bc06a2c55b7` changes `stage3_delivery._candidate_priority()` so every numeric B19 score, including exact zero, is in the known sortable segment and every explicit unknown score is deferred after all known scores. Impact never substitutes for an unknown composite when comparing it with a known composite.
- The reviewer specifically required an integrated signed-Review regression with more than 36 candidates. Commit `881430f0ccd1900535fe2d4483e7d217b382954e` strengthens the real B21 integration test with 37 contract-valid repairs: 35 positive known scores, one authenticated known score exactly `0.0`, and one high-impact cross-cutting unknown score. It proves the known zero is retained, the unknown repair is omitted, the same `stage3_delivery` decision appears in the completion Review, and the existing HMAC authenticates that Review.
- Exact executable FixList CI `35512886836` passed both jobs on `881430f0ccd1900535fe2d4483e7d217b382954e`: 115 root tests; scanner-api `2030 passed, 18 skipped`; two integrated signed B21 tests; labelled synthetic corpus 14 cases / 55 assertions with `full_30_site_gate=not_assessed`; frozen revision `01ebe8e90df1e6bd`; scanner image `sha256:6d49c53baa876bf38bdf4229399e13ab2164ccbbc40a99e5723589b786aa5022`; lint, typecheck, generated contracts, frontend contracts and production frontend build all passed.
- CI requested Node 20 but `setup-node` resolved Node `20.20.2`; hosted JavaScript actions separately warned that their own runtime is forced to Node 24. This is not exact Node 20.19.5 evidence.

B21 signed behavior now proves:

- every eligible canonical repair receives truthful unique affected URL / observation / known-population / displayed-sample counts before authority signing;
- all eligible candidates are considered before the 36-item presentation limit;
- known B19 scores are ranked ahead of explicit unknown composite scores, including the exact-known-zero edge case;
- legacy calibration rank does not mask authenticated B19 factor order in the temporary B21 ranking view;
- the bounded delivery summary carries counts and `displayed_fix_ids`, not duplicate raw candidate evidence;
- the completion proof authenticates the same Review carrying B19/B20/B21.

A focused independent follow-up review of the corrected exact signed boundary is still required before closing the B21 review gate. Durable FixItem/card/export consumption also remains open.

Detailed checkpoint: `docs/superpowers/plans/2026-09-20-stage3-b21-signed-delivery.md`.

### Current B19–B24 requirement state

- **B19:** signed Review integration green; exact factors/explanations and truthful unknowns are authenticated, including unknown-vs-known-zero ordering at the B21 cap. Durable FixItem/card/export consumption is still open.
- **B20:** signed Review integration corrected, exact-head CI green, and fresh independent follow-up review clean. Durable persistence/customer projection is still open.
- **B21:** corrected signed Review integration is green at executable `881430f0...` / CI `35512886836`, including the >36 known-zero-vs-unknown signed-authority regression. Focused independent follow-up plus durable persisted customer/card/export consumption remain open.
- **B22:** strict authenticated private-preview selection/whitelist helper exists; actual entitlement/customer preview seam still needs wiring and no-leak proof.
- **B23:** explicit verified root-cause score-cap helper exists and preserves an existing ceiling independently; actual health-score integration must preserve current access/sample/incomplete ceilings.
- **B24:** handoff v2 builder + historical v1 reader exist; actual authenticated customer/operator handoff route and persisted source fields still need wiring/proof.

Stage 3 is therefore **in progress, not complete**.

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
- New displayed counts/priorities/scores require authenticated source → Review → persistence → customer proof before completion claims.
- Premium/Grok remain outside this integration.
- Synthetic/historical data never substitutes for the genuine 30-site gate or real customer live acceptance.

## Exact next engineering action

Request and inspect a focused independent follow-up review of executable `881430f0ccd1900535fe2d4483e7d217b382954e` and its persisted documentation head. Correct any material B19/B21 signed-boundary finding with a reproducing regression and fresh exact-head CI.

The next customer-visible B19/B21 persistence/card/export slice must **not** recreate or copy the missing V7 Base44 route files into this later-stage branch. Current `main` contains V7/#308, but current Stage-1 acceptance documentation still records exact-source production publication/non-owner acceptance as pending. Once that serialized release gate is actually recorded complete, reconcile this branch onto the then-current accepted `main`, preserve V7/#308, run fresh integrated-head CI, then wire authenticated B19/B21 evidence into the real durable V7 persistence/read/customer/export path without schema/RLS broadening. Until then, continue only later-stage source work that does not duplicate or mutate the release path. Do not move production.