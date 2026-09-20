# Full blueprint progress

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`. The approved spec's exact requirement IDs and semantics control over older handoff paraphrases.

## Release sequencing / freeze

- `main` was refreshed during the B22 completion-Review privacy slice and remains `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad`, containing V7 runtime/public-build changes and durable ownership-before-admission fix #308.
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

Reviewed lane sources were integrated serially, never merged directly to `main`:

- B19/B20 lane `e74d87acd0cec2955402b96f635f13bc275f3a91` -> integration `c3f9d685e17b26c372a5a47403b478caec36ed2a`.
- B21–B24 lane `a998b4e38a06d6c163ac8853c3e49e9f10a58cb7` -> integration `3aebc7375e854ce063ac0bcec0a46210473e061c7`.
- Combined lane CI `35501672504` passed.

### B19 — signed authority source proven; durable customer seam open

RED `ac6ce27b3c492649537d80788f7b02b86ec39e5e` / CI `35501924104`; GREEN `7ba2df83d848fd643bb510374b7da5a18ac749f1` / CI `35501983203`.

Canonical Review carries the exact versioned four-factor model `impact x reach x page value x confidence`, explanations and truthful unknowns. Repair leverage is not a substitute/fifth factor. Durable FixItem/card/export consumption remains open behind the Stage-1 reconciliation gate.

### B20 — signed authority review gate closed; durable customer seam open

CodeRabbit found a P1 where repair-local identity could replace trusted producer identity. RED `6f1e2cc3ae519bbb494cab599579758f9efe427a` / CI `35503985665`; fix `56a9362ceb9ec1b06b88e26a0fd7db8fff97e92c`; strengthened stale assertion `cbfd2b1f4a696c209dfab90e3981f42b0cbaa481`; exact CI `35504200573` passed. Fresh follow-up `5749166024` on stable head `fb9a22f1284e1381db04186733ebeb32bb4a7e93` reported no unresolved material issue.

Verified grouping requires trusted non-empty enclosing `scan_id == scan_run_id`; repair-local identity can only confirm that trust. Explicit versioned same-root-cause evidence is required; family similarity alone is insufficient. Durable customer projection remains open.

### B21 — signed authority review gate closed; durable customer seam open

Initial semantic RED `513a4438d5622d393bf3031cb2db17f29caa7ee5` / CI `35506946578` proved delivery absent. Subsequent integration and review found/fixed the known-zero vs unknown-score ordering defect. Regression `467fc4aaf184c2cf8ad99e41dc8baa8fd13ac0d2`; fix `2b952e14ac72f03c42be794540574bc06a2c55b7`; signed-authority regression `881430f0ccd1900535fe2d4483e7d217b382954e`. Exact-code CI `35512886836` passed; stable checkpoint `7236c36cd65fe441a9a90c6a52db9a6c2342125a` passed exact-head CI `35513093636`; focused CodeRabbit follow-up `5750062094` reported no unresolved material issue.

The signed Review carries truthful unique affected-page / observation / known-population / displayed-sample counts and ranks every eligible B19 candidate before presentation truncation. Numeric known scores, including exact `0.0`, sort before explicit unknown composites; impact cannot substitute across that boundary. Durable customer/card/export proof remains open.

### B22 — signed preview source + enclosing completion-Review privacy RED->GREEN; fresh re-review + durable entitlement route open

B22 has a real canonical Review -> completion-HMAC source path without creating/copying a V7 customer route or granting entitlement.

Original source integration:

- RED `29aea5f3ed958805ed21bd2ce75e393e7330ca8f`, FixList CI `35519071373`: scanner-api failed exactly because `stage3_private_preview_source` did not yet exist (1 failed / 2037 passed / 18 skipped), while lint/typecheck/contracts/frontend stayed green.
- Selector factoring `20849a58acc968a25bd29e72c24abb42626bcb17`.
- Initial GREEN `2f6eb233d89e68475030a18d2157fc3d08b95938`, CI `35519385104` passed both jobs.

First fresh CodeRabbit review identified a material P1 privacy problem in comment `5750750081`: arbitrary `coverage_assessment["text"]` could be copied into signed `coverage_qualification`, so producer/debug text or private URLs could cross into the customer-intended preview source. The same review exposed an exact B22 semantic gap: when there are no individually verified impact-4/5 findings, the approved spec requires **the best verified finding** singular, not up to two lower-impact fallbacks.

First correction evidence:

- Exact-fallback RED `ac2e1f0e3f1326073a6a37593071c00244338b11`, CI `35519832761`: scanner regression job failed intentionally while the independent lint/typecheck/contracts/frontend job passed.
- Correction implementation `d2709fb6c430c7bfc0443bd82bc60d43f84764b5`.
- Privacy regression expansion `ba31a4386bb8ac5bf2403048955238676451b756` injected a private coverage sentinel and private URL and required neither to survive in the nested source; unknown coverage could not create good-shape/customer qualification text.
- CI `35520342700` at the first implementation head still failed only because two older lane tests expected the now-rejected raw coverage text behavior (2 failed / 2039 passed / 18 skipped). The implementation was not weakened.
- Stale assertions aligned to the approved fail-closed semantics at `e7719996e5454f19d373dc04557792992590d834`.
- Corrected executable `e7719996e5454f19d373dc04557792992590d834` passed FixList CI `35520663236`; stable documentation head `31f2c579bca25de26cbe9a5aa52977ddf9e9d0b5` passed exact-head CI `35520925132`.

A fresh combined B22/B24 CodeRabbit follow-up, issue comment `5750887385`, then found a second material P1 at the **enclosing completion Review**. The nested preview source was safe, but `apply_canonical_repair_contract()` retained the original `site_fingerprint.coverage_assessment.text`, and `build_completion_envelope()` signed that complete Review. Private producer/debug prose could therefore bypass the safe B22 projection beside it.

Second correction evidence:

- **RED:** `db6432fcf7258e64736d7a3eabeadd28e4cb907f`, FixList CI `35521744377`. The strengthened regression serializes the entire signed Review and complete envelope. Root tests stayed green at 115; scanner-api failed exactly one assertion with 2040 passed / 18 skipped because `PRIVATE-COVERAGE-SENTINEL` and `https://private.example/internal?token=debug` remained under `envelope["review"]["site_fingerprint"]["coverage_assessment"]["text"]`. Lint/typecheck/generated-contract/frontend jobs remained green independently.
- **GREEN implementation:** `4d1575d92c6a3092661bcd290b7d8ef4ae883066`. `completion_review_payload()` now positive-allowlists the scanner-owned structured coverage-decision keys before completion HMAC signing: `coverage_authority_version`, `state`, `reasons`, `authoritative`, `score_is_provisional`, `release_gate_eligible`, `inventory`, `inventory_proof`, `thresholds`. Arbitrary `text` and unknown/future coverage-assessment fields fail closed. The producer Review is not mutated; the limited-result path remains unchanged because it already builds an explicit structured payload.
- **Exact executable GREEN:** FixList CI `35522106799` passed both jobs on `4d1575d92c6a3092661bcd290b7d8ef4ae883066`: 115 root tests; 2041 scanner-api passed / 18 skipped; B22 signed-preview integration 5 passed; synthetic Stage-1 corpus 14 cases / 55 assertions with provenance `synthetic` and `full_30_site_gate=not_assessed`; frozen revision `01ebe8e90df1e6bd`; scanner image `sha256:2f630706c1a594fe2d1ec22858e05bc74625bf5113bfc67052e275576748e592`; lint/typecheck/generated contracts/frontend contracts/build passed.

The corrected B22 source now requires exact trusted producer `scan_id == scan_run_id`; derives only from canonical reviewed repairs; allows only exact verified findings; if any verified impact-4/5 findings exist, selects only that preferred set and preserves the two-finding cap; otherwise emits exactly one best verified fallback. Finding projection remains allowlisted to `rule_id`, `title`, `impact`, `evidence_summary`. Arbitrary coverage text is never copied into the preview source or enclosing signed completion Review. Unknown/future `coverage_assessment` keys fail closed at completion signing. `good_shape` requires explicit normalized `coverage_assessment.state == "sufficient"` and uses only fixed controller-owned wording `Coverage was sufficient for the assessed scan scope.` Limited/unknown/absent coverage leaves qualification unknown and cannot create `good_shape`. `entitlement_state=requires_authenticated_customer_gate` remains an explicit non-entitlement boundary.

Detailed checkpoints:

- `docs/superpowers/plans/2026-09-20-stage3-b22-signed-preview-source.md`
- `docs/superpowers/plans/2026-09-20-stage3-b22-completion-review-privacy.md`

B22 remains **partial**. One fresh independent re-review of the second correction plus exact-head FixList CI on the final persisted documentation head remain open. After Stage-1 accepted-main reconciliation, the source must be consumed through the real V7 exact-owner/exact-scan entitlement, persistence/read/reload/history/preview/card/export path, retaining the high-impact two-finding cap, one-finding fallback, safe good-shape qualification, and no suppressed/operator/private leakage.

CI requested Node 20 but hosted setup resolved Node 20.20.2; this is not exact Node 20.19.5 evidence. Python was 3.12.14 on Ubuntu 24.04.5.

### B23 — signed authority source review gate closed; durable score consumption open

B23 has a real canonical Review -> completion-HMAC decision seam without rewriting the current customer-visible legacy `health_score` on this release-frozen branch.

- RED `c713baca3f65da28bd52616960fdcb30e8f52d49` / CI `35514082243`.
- Implementation sequence: `5d967faa32e6a0790cf5cae013717a35455ba9b4`, `addc071e2fcc2d4f2392eb1fa5586cb73dde352e`, `bdd7fc4e2794227997b181693b203b157304ba02`, `23d28ddee804e9c20db4136f06aab879685d1942`.
- Exact executable CI `35514416069` passed both jobs.
- Stable persisted head `4ee24691f46721ffe8112bb435f278e5dd810721` passed exact-head CI `35514613656`.
- Fresh focused CodeRabbit follow-up comment `5750230877` reported no unresolved material defect in the B23 signed health-score-cap seam. Repository CI above supplies execution proof; CodeRabbit itself did not execute tests.

Only versioned, explicit, verified B20 root-cause evidence can contribute a score cap. Cross-scan/unverified/conflicted evidence cannot. Existing stricter access/sample/incomplete ceilings remain authoritative; B23 can only keep/lower the already-final legacy score candidate. Customer-visible adjusted-score persistence/card/export remains open after Stage-1 accepted-main reconciliation.

Detailed checkpoint: `docs/superpowers/plans/2026-09-20-stage3-b23-signed-score-caps.md`.

### B24 — signed handoff-v2 source GREEN; fresh combined re-review + durable route open

RED `37b73a98e6b54db9c86f0de9eb921ff178a0201a` / CI `35515644839` proved the source absent. Implementation `5eb4b6751019e98f87afc3b329880fbd33e0fdd6`. A first fixture incorrectly expected missing `indexable_affected` to be inferred; that expectation was corrected rather than weakening unknown semantics. Corrected GREEN executable head `790ebdc7ddec86a5a4bbfe4dfa0cb3ee23e0a353` / CI `35516240329` passed both jobs.

The B24 source requires exact trusted producer scan identity; accepts root-cause identity only from exact-scan B20 verified groups; carries family IDs, B19 factors, B21 counts, explicitly evidenced indexable count, evidence refs, verification/dependency/vendor and the scanner user agent; excludes suppressed/operator-only data with `operator_authorized=False`; fails closed on ambiguous root-cause mapping; and is included before completion HMAC signing. Historical-v1 durable reader compatibility and real V7 persistence/customer/operator/export proof remain release-gated.

Fresh combined review `5750887385` statically confirmed the existing B24 exact-scan/root-cause/operator-suppression controls but found the enclosing B22 completion-Review leak described above. Therefore the combined review gate is not considered clean until one fresh follow-up reviews the corrected stable head.

Detailed checkpoint: `docs/superpowers/plans/2026-09-20-stage3-b24-signed-handoff-source.md`.

### Stage-3 overall state

- **B19 partial:** signed Review factors/explanations green; durable FixItem/card/export consumption open.
- **B20 partial:** signed Review corrected and independently review-clean; durable customer projection open.
- **B21 partial:** signed rank/count/truncation seam independently review-clean and CI green; durable persisted customer/card/export proof open.
- **B22 partial:** signed evidence-led preview source and full completion-Review privacy are RED->GREEN with exact executable CI; final stable-head CI, fresh independent re-review and real V7 owner/scan entitlement/persistence/preview/card/export proof remain open.
- **B23 partial:** signed score-cap decision independently review-clean; durable customer-visible adjusted-score persistence/card/export open.
- **B24 partial:** signed handoff-v2 source RED->GREEN; fresh combined re-review plus real V7 persistence/read/customer/operator/export proof remain open.

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

Run exact-head FixList CI on the final persisted documentation head containing the second B22 completion-Review privacy correction, then request one fresh focused independent CodeRabbit review of the corrected combined B22/B24 signed source/privacy boundary. Do not count the review request as a pass. Any material finding must be reproduced first, corrected minimally, and followed by fresh exact-head FixList CI.

Durable B19/B21/B22/B23/B24 persistence/card/export/preview work remains release-gated because this older-base integration branch must not recreate V7 while Stage-1 acceptance is pending. Once Stage-1 exact-source publication and fresh non-owner acceptance are recorded, reconcile onto accepted `main`, preserve V7/#308, run fresh integrated-head CI, then wire the already-authenticated Stage-3 source fields through the real V7 persistence/read/card/export/preview path with RED -> GREEN regressions and independent review.

Do not move production or begin Stage-4 release execution before those gates are genuinely satisfied.
