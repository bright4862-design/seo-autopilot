# Blueprint implementation checkpoint

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`. The approved spec controls over older paraphrases.

## Release boundary

- `main` was refreshed during the B22 review-correction slice and remains `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad` with V7 runtime/public-build changes and #308.
- Current-main `docs/stage-one-evidence-acceptance.md` still records exact-source production publication and fresh non-owner production acceptance as pending.
- Stage-1 publication/promotion/live acceptance remains owned by the existing single release operator.
- Later-stage integration remains on `agent/full-blueprint-stage2-coverage-b06-20260919`, PR #303.
- Do not merge this branch to `main`, deploy/publish, promote worker traffic, mutate admission, submit a competing production scan, change schema/secrets or copy/recreate V7 persistence routes while Stage-1 acceptance is pending.
- After Stage-1 acceptance is recorded, reconcile onto the then-current accepted `main`, preserve V7/#308 and require fresh integrated-head CI before durable customer-path work.

## Stage 2

B06–B18 are complete for source integration, independent review and exact-head CI at stable corrected head `10f51529bf5bf64b7b24ab8424f3ae821de46b39`; FixList CI `35500580582` passed and CodeRabbit follow-up `5748778814` returned no actionable finding. This is not a production-release claim.

The proven Stage-2 invariants remain authoritative: one finite shared follow-up budget; Standard-150 assessed cap; truthful denominators; robots/DNS/SSRF/redirect/body/deadline protections; exact URL identity; blocked/challenged/429/incomplete as unknown; optional providers disconnected by default; historical compatibility; fail-closed page/aggregate projection.

## Stage 3 — current checkpoint

Reviewed lane sources integrated serially:

- B19/B20 lane `e74d87acd0cec2955402b96f635f13bc275f3a91` -> `c3f9d685e17b26c372a5a47403b478caec36ed2a`.
- B21–B24 lane `a998b4e38a06d6c163ac8853c3e49e9f10a58cb7` -> `3aebc7375e854ce063c0bcec0a46210473e061c7`.
- Combined lane CI `35501672504` passed.

### B19/B20 signed authority

B19/B20 canonical Review integration: RED `ac6ce27b3c492649537d80788f7b02b86ec39e5e` / CI `35501924104`; GREEN `7ba2df83d848fd643bb510374b7da5a18ac749f1` / CI `35501983203`.

B19 signs only the versioned four factors `impact x reach x page value x confidence` with truthful unknowns. B20 requires explicit evidenced same-root-cause evidence and trusted enclosing scan identity.

B20 P1 scan-isolation correction: RED `6f1e2cc3ae519bbb494cab599579758f9efe427a` / CI `35503985665`; fix `56a9362ceb9ec1b06b88e26a0fd7db8fff97e92c`; strengthened lane expectation `cbfd2b1f4a696c209dfab90e3981f42b0cbaa481`; exact CI `35504200573`. Fresh CodeRabbit follow-up `5749166024` on stable head `fb9a22f1284e1381db04186733ebeb32bb4a7e93` reported no unresolved material issue. B20 review is closed at the signed Review boundary; durable customer projection remains open.

### B21 signed authority — review gate closed

B21 signed rank/count/truncation integration is RED->GREEN and independently review-clean. Exact-code CI `35512886836` passed; stable checkpoint `7236c36cd65fe441a9a90c6a52db9a6c2342125a` passed exact-head CI `35513093636`; focused CodeRabbit follow-up `5750062094` reported no unresolved material issue.

Known numeric B19 scores, including exact `0.0`, rank ahead of explicit unknown scores; every eligible repair is ranked before the presentation cap. Signed counts preserve unique affected pages, observations, known population and displayed sample without inventing unknowns. Durable customer/card/export proof remains open.

### B22 signed private-preview source — P1 corrected; exact executable GREEN; follow-up review + durable route open

B22 has a real canonical Review -> completion-HMAC source seam without creating/copying a V7 route or granting entitlement.

Original source integration:

- RED `29aea5f3ed958805ed21bd2ce75e393e7330ca8f` / CI `35519071373`: scanner-api failed exactly on missing `stage3_private_preview_source` (1 failed / 2037 passed / 18 skipped) while lint/typecheck/contracts/frontend stayed green.
- Selector factoring `20849a58acc968a25bd29e72c24abb42626bcb17`.
- Initial GREEN `2f6eb233d89e68475030a18d2157fc3d08b95938` / CI `35519385104` passed both jobs.

Fresh CodeRabbit review then found a material P1 privacy problem in issue comment `5750750081`: arbitrary `coverage_assessment["text"]` could cross into signed `coverage_qualification`. The approved B22 wording also requires singular fallback semantics: if no individually verified impact-4/5 finding exists, emit **the best verified finding**, not up to two lower-impact findings.

Correction sequence:

- exact-fallback RED `ac2e1f0e3f1326073a6a37593071c00244338b11` / CI `35519832761` failed intentionally in scanner regressions while the independent lint/typecheck/contracts/frontend job passed;
- implementation `d2709fb6c430c7bfc0443bd82bc60d43f84764b5`;
- privacy regression expansion `ba31a4386bb8ac5bf2403048955238676451b756` proves private coverage text/URL sentinels cannot survive into source or signed completion envelope and unknown coverage cannot fabricate customer text;
- intermediate CI `35520342700` failed only because two older lane assertions expected the now-prohibited raw coverage text behavior (2 failed / 2039 passed / 18 skipped); implementation was not weakened;
- stale assertions aligned to fail-closed privacy semantics at `e7719996e5454f19d373dc04557792992590d834`.

Corrected executable GREEN at `e7719996e5454f19d373dc04557792992590d834`: FixList CI `35520663236` passed both jobs with 115 root tests, 2041 scanner-api passed / 18 skipped, 5 B22 signed-preview integration tests, 11 Stage-3 delivery contract tests, synthetic Stage-1 corpus 14 cases / 55 assertions with `full_30_site_gate=not_assessed`, frozen revision `01ebe8e90df1e6bd`, scanner image `sha256:2e7c8c8d71a29aa6a09562728189d41a337d1ab1b2e38486d429c6c3f0d4b0f2`, and green lint/typecheck/contracts/frontend build.

Corrected semantics:

- exact trusted producer `scan_id == scan_run_id` required;
- canonical reviewed exact-verified findings only;
- verified impact-4/5 findings are preferred and the existing two-finding cap applies only to that preferred set;
- if no verified impact-4/5 finding exists, exactly one best verified fallback is emitted;
- finding projection remains `rule_id`, `title`, `impact`, `evidence_summary` only;
- arbitrary producer coverage text is never copied/signed;
- `good_shape` requires explicit normalized coverage state `sufficient` and uses only fixed controller-safe wording `Coverage was sufficient for the assessed scan scope.`;
- limited/unknown/absent coverage yields no qualification/customer good-shape text;
- `entitlement_state=requires_authenticated_customer_gate` remains a signed source boundary, not an entitlement grant.

CI requested Node 20 but hosted setup resolved Node 20.20.2; do not represent this as exact Node 20.19.5 evidence. Python was 3.12.14 on Ubuntu 24.04.5.

Detailed checkpoint: `docs/superpowers/plans/2026-09-20-stage3-b22-signed-preview-source.md`.

B22 remains partial. Final stable documentation-head CI plus one fresh independent follow-up review of the corrected B22/B24 surface remain open. After Stage-1 accepted-main reconciliation, the source must flow through the real V7 exact-owner/exact-scan entitlement and persistence/read/preview/card/export path, proving reload/history privacy, high-impact two-item cap, one-item fallback, and safe good-shape qualification.

### B23 signed authority — review gate closed

B23 has a real canonical Review -> completion-HMAC decision seam while the release-gated customer-visible legacy `health_score` remains intentionally unchanged. RED `c713baca3f65da28bd52616960fdcb30e8f52d49` / CI `35514082243`; exact executable `23d28ddee804e9c20db4136f06aab879685d1942` / CI `35514416069`; stable `4ee24691f46721ffe8112bb435f278e5dd810721` / CI `35514613656`; focused CodeRabbit follow-up `5750230877` reported no unresolved material defect.

Only the same explicit versioned verified B20 root-cause evidence can contribute a cap; conflicted/unverified/cross-scan evidence fails closed and a B23 cap cannot undo a stricter existing ceiling. Durable customer-visible adjusted-score persistence/read/card/export remains open.

Detailed checkpoint: `docs/superpowers/plans/2026-09-20-stage3-b23-signed-score-caps.md`.

### B24 signed handoff-v2 source — GREEN; combined follow-up review + durable route open

B24 signed source RED `37b73a98e6b54db9c86f0de9eb921ff178a0201a` / CI `35515644839`; implementation `5eb4b6751019e98f87afc3b329880fbd33e0fdd6`; corrected GREEN executable `790ebdc7ddec86a5a4bbfe4dfa0cb3ee23e0a353` / CI `35516240329` passed both jobs.

The source requires exact trusted producer identity; accepts root cause only from exact-scan B20 verified groups; carries family IDs, B19 factors, B21 counts, explicitly evidenced indexable count, evidence refs, verification/dependency/vendor and real scanner user agent; excludes operator/debug suppressed data; fails closed on ambiguous root-cause mapping; and is HMAC-authenticated in Review. Missing counts stay unknown.

Detailed checkpoint: `docs/superpowers/plans/2026-09-20-stage3-b24-signed-handoff-source.md`.

A fresh independent follow-up review of the current corrected combined B22/B24 signed source/privacy surface remains required. Historical-v1 durable reader compatibility and real V7 persistence/read/customer/operator/export proof remain release-gated.

### B19–B24 requirement state

- **B19 partial:** signed Review factors/explanations green; durable FixItem/card/export consumption open.
- **B20 partial:** signed Review P1-corrected and independently review-clean; durable customer projection open.
- **B21 partial:** signed rank/count/truncation authority seam independently review-clean and CI green; durable persisted customer/card/export proof open.
- **B22 partial:** signed preview source P1-corrected with exact executable CI green; stable-head CI, fresh independent follow-up review and exact-owner/exact-scan V7 persistence/preview/card/export proof open.
- **B23 partial:** signed Review cap decision independently review-clean; durable customer-visible adjusted-score consumption open.
- **B24 partial:** signed handoff-v2 source GREEN; combined independent follow-up review and real V7 persistence/read/customer/operator/export proof open.

Stage 3 remains **in progress**.

## Stage 4

Reuse only existing isolated source `agent/stage4-b25-b28-compat-release-20260919` @ `d2ce905ff67410586f86e38bafd93ce4e998e4d1`, CI `35464436789`, after shared Stage-3 acceptance.

- **B25 incomplete:** real provenance-labelled 30-site baseline/candidate gate remains `not_assessed`; synthetic/historical evidence is not a pass.
- **B26 partial:** isolated own-site serving-defect work exists; shared acceptance not run.
- **B27 partial:** isolated GEO/historical HMAC/reader/tamper/privacy compatibility exists; shared acceptance not run.
- **B28 incomplete:** exact-source deployment/live acceptance, live identities, rollback proof and real customer submit -> persistence -> exact reload/history -> linked rescan remain outstanding.

## Exact next action

Run exact-head FixList CI on the final persisted B22 correction documentation head, then request one fresh focused independent CodeRabbit follow-up review of the corrected combined B22/B24 signed source/privacy boundary. Reproduce any material finding first, correct minimally, and run fresh exact-head CI.

Durable B19/B21/B22/B23/B24 persistence/card/export/preview work remains release-gated until Stage-1 acceptance permits reconciliation onto V7 main. After that gate closes: reconcile onto accepted `main`, preserve V7/#308, run fresh integrated-head CI, then wire the authenticated Stage-3 sources through the real V7 persistence/read/customer/card/export/preview path with RED -> GREEN regressions and independent review.

Do not move production or begin Stage-4 release execution before those gates are actually satisfied.
