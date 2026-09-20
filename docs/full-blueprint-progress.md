# Full blueprint progress

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`. The approved spec's exact requirement IDs and semantics control over older handoff paraphrases.

## Release sequencing / freeze

- `main` was refreshed and remains `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad`, containing V7 runtime/public-build changes and durable ownership-before-admission fix #308.
- Current-main `docs/stage-one-evidence-acceptance.md` still records exact-source production publication and fresh non-owner production acceptance as pending. No accepted Stage-1 production report is recorded.
- Stage-1 publication/promotion/non-owner acceptance remains owned by the existing single release operator.
- Later-stage integration remains on `agent/full-blueprint-stage2-coverage-b06-20260919`, PR #303.
- Do not merge later-stage work to `main`, publish Base44, promote worker traffic, mutate admission, submit a competing production scan, rebuild the release, change schema/secrets, or copy/recreate V7 persistence routes on this older-base branch.
- After Stage-1 live acceptance is recorded, reconcile this branch onto the then-current accepted `main` without reverting V7/#308 and require fresh integrated-head CI before durable customer-path integration.

The Stage-1 labelled corpus remains explicitly synthetic. Frozen scanner revision `01ebe8e90df1e6bd`. Synthetic/historical evidence cannot satisfy B25's genuine 30-site gate.

## Stage 2 — B06–B18 complete for source/review/CI

Stable corrected Stage-2 head `10f51529bf5bf64b7b24ab8424f3ae821de46b39`; exact-head FixList CI `35500580582` passed. Fresh CodeRabbit follow-up `5748778814` returned `Comments: 0` / no actionable finding. This closes Stage 2 for implementation, independent review and exact-head CI only; it is not a production-release claim.

Requirement state:

- **B06 complete:** one finite shared follow-up scheduler; probe-only URLs cannot inflate Standard-150 assessed pages/denominators.
- **B07 complete:** active soft-404 producer/orchestration reuses that scheduler; challenge/429/robots/budget/deadline/incomplete remains unknown.
- **B08 complete:** redirect meaning distinguishes normalization, usable, wrong/catch-all, unusable and unverified access destinations.
- **B09 complete:** robots-declared sitemap integrity/probes reuse the shared finite scheduler with retrieval/probe provenance.
- **B10 complete:** deterministic accepted-main-content analysis remains internal; private fingerprints/raw copy do not cross external authority/customer boundaries.
- **B11 complete:** exact retained-set depth/inlink/navigation with truthful sample scope; sitemap is not an inlink and unsampled links cannot expand Standard 150.
- **B12 complete:** paired raw/rendered hub-link evidence under the existing browser-followup ceiling with completed/failed/unassessed states.
- **B13 complete:** contextual local entity/status completeness with raw identity/contact evidence internal and positive-allowlisted external aggregates.
- **B14 complete:** cross-page identity requires the same explicit absolute HTTP(S) JSON-LD `@id` on distinct URLs; matching NAP/family is insufficient.
- **B15 complete:** contextual freshness requires current-content intent plus contradictory temporal evidence; old dates alone do not fail.
- **B16 complete:** exact bounded URL-variant identity/probes without sibling-host expansion or unverified duplicate claims.
- **B17 complete:** raw transfer bytes measured separately from decoded/inline bytes; optional CrUX disconnected by default and controlled evidence requires owner authorization, exact scan identity and valid observation time.
- **B18 complete:** GSC disconnected by default; controlled evidence requires owner authorization, exact scan identity, exact retained-URL membership, conflict rejection, Standard-150 ceiling and valid observation time.

## Stage 3 — B19–B24 in progress

Reviewed lane sources were integrated serially, not merged to `main`:

- B19/B20 lane `e74d87acd0cec2955402b96f635f13bc275f3a91` -> integration `c3f9d685e17b26c372a5a47403b478caec36ed2a`.
- B21–B24 lane `a998b4e38a06d6c163ac8853c3e49e9f10a58cb7` -> integration `3aebc7375e854ce063ac8853c3e49e9f10a58cb7`.
- Combined lane CI `35501672504` passed.

### B19 — signed authority partial complete; durable customer seam open

B19 is integrated into canonical Review before completion signing. RED `ac6ce27b3c492649537d80788f7b02b86ec39e5e` / CI `35501924104`; GREEN `7ba2df83d848fd643bb510374b7da5a18ac749f1` / CI `35501983203`.

The signed Review carries versioned exact factors `impact x reach x page value x confidence`, explanations and truthful unknowns. Repair leverage is not a substitute/fifth factor. B19 is not complete overall because durable FixItem/card/export consumption is still unproven.

### B20 — signed authority review gate closed; durable customer seam open

CodeRabbit found a P1 where repair-local identity could replace trusted producer identity. RED `6f1e2cc3ae519bbb494cab599579758f9efe427a` / CI `35503985665`; fix `56a9362ceb9ec1b06b88e26a0fd7db8fff97e92c`; strengthened stale assertion `cbfd2b1f4a696c209dfab90e3981f42b0cbaa481`; exact-head CI `35504200573` passed. Fresh follow-up on stable head `fb9a22f1284e1381db04186733ebeb32bb4a7e93` (`5749166024`) reported no unresolved material issue.

Verified multi-member grouping requires trusted non-empty enclosing `scan_id == scan_run_id`; repair-local identity can only confirm that trust. Explicit evidenced same-root-cause evidence is required; family similarity alone is insufficient. Durable customer projection remains open.

### B21 — corrected signed authority seam review/CI complete; durable customer seam open

B21 is wired through the canonical Review -> signed completion boundary with truthful unique affected-page / observation / known-population / displayed-sample counts and rank-before-truncate delivery metadata.

Initial semantic RED `513a4438d5622d393bf3031cb2db17f29caa7ee5` / CI `35506946578` proved `stage3_delivery` absent. `86cea88d8a90c62a686015fb9fc464fc0dddfd0d` attached counts/delivery; CI `35507077795` exposed legacy `priority_rank` masking B19 score order; `d74240b751d9ac1fefe070036397d016a6d074aa` removed it only from the temporary B21 view. `e9aa3789b9b143a7b3b8dbdd0e52ad2edf953a0f` corrected the fixture to a B19-known family-scoped candidate; CI `35507339178` passed.

Fresh CodeRabbit then found a material P1: explicit unknown B19 composite score could normalize to sortable zero and use impact as tie-breaker, allowing a high-impact unknown repair to displace an authenticated known score of exactly `0.0` at the 36-item cap.

- Regression `467fc4aaf184c2cf8ad99e41dc8baa8fd13ac0d2` covers unknown-vs-known-zero ordering.
- Fix `2b952e14ac72f03c42be794540574bc06a2c55b7` places every numeric B19 composite, including exact zero, in the known segment before every explicit unknown composite; impact cannot substitute across that boundary.
- Reviewer-required signed-authority regression `881430f0ccd1900535fe2d4483e7d217b382954e` uses 37 contract-valid repairs: 35 positive known scores + one authenticated known `0.0` + one high-impact unknown. It proves the known zero remains inside the 36 displayed IDs, the unknown repair is omitted and the completion HMAC authenticates that exact Review.
- Exact-code CI `35512886836` passed: root `115 passed`; scanner-api `2030 passed, 18 skipped`; B21 signed integration `2 passed`; synthetic corpus 14 cases / 55 assertions / `full_30_site_gate=not_assessed`; frozen revision `01ebe8e90df1e6bd`; scanner image `sha256:6d49c53baa876bf38bdf4229399e13ab2164ccbbc40a99e5723589b786aa5022`; lint/typecheck/contracts/frontend build passed.
- Stable checkpoint head `7236c36cd65fe441a9a90c6a52db9a6c2342125a` passed exact-head FixList CI `35513093636` on both jobs.
- Focused independent CodeRabbit follow-up `5750062094` on exact stable head `7236c36...` reported **no unresolved material issue** and explicitly verified the B19 four-factor model, unknown-denominator preservation, known-zero-before-unknown ordering, rank-before-truncate, completion-HMAC proof, B20 producer-identity trust, bounded delivery summary, external projection, no new request activity and unchanged Standard-150 boundary. CodeRabbit did not run tests; repository CI above supplies execution proof.

The **B21 independent-review gate is closed for the signed authority boundary**. B21 remains incomplete overall until authenticated B19/B21 evidence is persisted and consumed by real customer card/export surfaces with no suppressed/operator/private leakage.

### B23 — signed authority source seam implemented; review + durable score consumption open

B23 now has a real canonical Review -> completion-HMAC decision seam without rewriting the current customer-visible legacy `health_score`.

- RED `c713baca3f65da28bd52616960fdcb30e8f52d49` / FixList CI `35514082243`: the new signed B23 expectation failed in the Python scanner-api job while the separate lint/typecheck/contracts/frontend job remained green.
- `5d967faa32e6a0790cf5cae013717a35455ba9b4` binds optional score caps only to the same versioned, explicit, verified B20 root-cause evidence. Unverified/conflicted/cross-scan evidence cannot contribute a cap; conflicting explicit caps fail closed.
- `addc071e2fcc2d4f2392eb1fa5586cb73dde352e` attaches `stage3_health_score_decision` before completion signing. It uses the already-final legacy score as the base, carries an existing explicit legacy ceiling without recomputing it, deduplicates by `root_cause_id`, preserves coverage state and can only keep/lower the candidate score.
- `bdd7fc4e2794227997b181693b203b157304ba02` adds conflict and foreign-scan adversarial regressions.
- `23d28ddee804e9c20db4136f06aab879685d1942` separates root-cap lowering from preservation of a stricter pre-existing incomplete ceiling.
- Exact executable CI `35514416069` passed both jobs: root scanner regressions, full scanner-api suite, labelled synthetic corpus, frozen revision, scanner image build, lint/typecheck/generated release contracts/frontend contracts/frontend production build all passed.

Behavioral proof covers: verified cap 72 producing a signed candidate score 72 from legacy score 88 while legacy display remains 88; existing incomplete ceiling 55 remaining stricter than cap 72; cap conflicts failing closed; and foreign repair scan identity being unable to apply a cap after B20 isolation rejects the group.

Detailed checkpoint: `docs/superpowers/plans/2026-09-20-stage3-b23-signed-score-caps.md`.

B23 remains **partial**, not complete overall: focused independent review is still required, and after Stage-1 accepted-main reconciliation any actual customer-visible B23 score must be proven through the real V7 persistence/read/card/export path while preserving historical readers/signatures and all access/sample/incomplete ceilings.

CI requested Node 20 in prior runs but hosted setup has resolved newer Node 20 patch versions; none of these runs is represented as exact Node 20.19.5 evidence.

### B22/B24 current state

- **B22 partial:** strict authenticated private-preview selection/whitelist helper exists; actual entitlement/customer preview seam and no-leak proof remain unwired.
- **B24 partial:** handoff-v2 builder + historical-v1 reader exist; actual authenticated customer/operator handoff route, persisted source fields and suppressed/operator-only exclusion remain unwired.

Stage 3 is **in progress, not complete**.

## Stage 4 — B25–B28 isolated lane only

Canonical isolated source: `agent/stage4-b25-b28-compat-release-20260919` @ `d2ce905ff67410586f86e38bafd93ce4e998e4d1`, CI `35464436789`. It is implementation input, not release authorization.

- **B25 incomplete:** named synthetic corpus exists, but genuine provenance-labelled 30-site baseline/candidate gate remains `not_assessed`; synthetic mini-fixtures/historical summaries are not a substitute.
- **B26 partial:** own-site serving-defect reproduction/fix support exists in isolated lane; shared acceptance remains gated behind Stage 3.
- **B27 partial:** GEO/historical HMAC/reader/tamper/privacy compatibility work exists in isolated lane; shared acceptance remains gated behind Stage 3.
- **B28 incomplete:** exact-source deployment/live acceptance has not run. Required live identities, rollback proof and real customer submit -> persistence -> exact scan reload/history -> linked rescan remain outstanding.

## Hard invariants

Standard-150 assessed-page cap; truthful denominators; one finite Stage-2 follow-up budget; robots/DNS/SSRF/redirect/body/deadline protections; one active scan/account; cancellation/terminalization; exact scan isolation; historical signatures/readers; preview privacy; and unknown/unavailable semantics remain authoritative. New displayed counts/priorities/scores require authenticated source -> Review -> persistence -> customer proof before overall completion. Premium/Grok remain out of scope.

## Exact next engineering action

B23's signed source seam is implemented and exact-code CI green; its focused independent review is now the next gate. If review reports a material issue, reproduce it first, correct minimally and require fresh exact-head CI.

Durable B19/B21/B23 customer persistence/card/export work remains release-gated because this older-base integration branch must not recreate V7 while Stage-1 acceptance is pending. Once Stage-1 exact-source publication and fresh non-owner acceptance are recorded, reconcile onto accepted `main`, preserve V7/#308, run fresh integrated-head CI, then wire authenticated B19/B21 evidence and any B23-adjusted score through the real V7 persistence/read/card/export path with RED -> GREEN regressions and independent review.

Until that release gate closes, continue only Stage-3 source work that does not duplicate/mutate the frozen release path. B22/B24 source-only work is eligible only if it can remain off the V7 customer/persistence path. Do not move production.