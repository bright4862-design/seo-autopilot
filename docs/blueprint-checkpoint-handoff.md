# Blueprint implementation checkpoint

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`. The approved spec controls over older paraphrases.

## Release boundary

- `main` remains `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad` with V7 runtime/public-build changes and #308.
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
- B21–B24 lane `a998b4e38a06d6c163ac8853c3e49e9f10a58cb7` -> `3aebc7375e854ce063ac8853c3e49e9f10a58cb7`.
- Combined lane CI `35501672504` passed.

### B19/B20 signed authority

B19/B20 canonical Review integration: RED `ac6ce27b3c492649537d80788f7b02b86ec39e5e` / CI `35501924104`; GREEN `7ba2df83d848fd643bb510374b7da5a18ac749f1` / CI `35501983203`.

B19 signs only the versioned four factors `impact x reach x page value x confidence` with truthful unknowns. B20 requires explicit evidenced same-root-cause evidence and trusted enclosing scan identity.

B20 P1 scan-isolation correction: RED `6f1e2cc3ae519bbb494cab599579758f9efe427a` / CI `35503985665`; fix `56a9362ceb9ec1b06b88e26a0fd7db8fff97e92c`; strengthened lane expectation `cbfd2b1f4a696c209dfab90e3981f42b0cbaa481`; exact CI `35504200573`. Fresh CodeRabbit follow-up `5749166024` on stable head `fb9a22f1284e1381db04186733ebeb32bb4a7e93` reported no unresolved material issue. B20 review is closed at the signed Review boundary; durable customer projection remains open.

### B21 signed authority — review gate closed

B21 real Review integration: semantic RED `513a4438d5622d393bf3031cb2db17f29caa7ee5` / CI `35506946578`; implementation `86cea88d8a90c62a686015fb9fc464fc0dddfd0d`; legacy-rank correction `d74240b751d9ac1fefe070036397d016a6d074aa`; B19-known fixture correction `e9aa3789b9b143a7b3b8dbdd0e52ad2edf953a0f` / CI `35507339178`.

Fresh CodeRabbit then found a P1 where explicit unknown B19 composite score could be sorted as zero plus impact and displace a genuinely known score `0.0` at the 36-item cap.

- Regression `467fc4aaf184c2cf8ad99e41dc8baa8fd13ac0d2` covers unknown-vs-known-zero.
- Fix `2b952e14ac72f03c42be794540574bc06a2c55b7` separates every numeric known B19 score, including exact zero, from explicit unknown composites. Known scores sort before unknowns; impact cannot substitute across that boundary.
- Signed-authority regression `881430f0ccd1900535fe2d4483e7d217b382954e` uses 37 valid repairs and proves the known-zero repair remains in the 36 displayed IDs, the high-impact unknown repair is omitted and the completion HMAC authenticates that exact Review.
- Exact-code CI `35512886836` passed; stable checkpoint `7236c36cd65fe441a9a90c6a52db9a6c2342125a` passed exact-head CI `35513093636`.
- Focused CodeRabbit follow-up `5750062094` on exact stable head reported no unresolved material issue.

The B21 independent-review gate is closed for the signed authority boundary; durable FixItem -> customer card/export proof remains open.

### B23 signed authority — review gate closed

B23 has a real canonical Review -> completion-HMAC decision seam, while the release-gated customer-visible legacy `health_score` remains intentionally unchanged.

- RED `c713baca3f65da28bd52616960fdcb30e8f52d49` / CI `35514082243`.
- Implementation sequence `5d967faa32e6a0790cf5cae013717a35455ba9b4`, `addc071e2fcc2d4f2392eb1fa5586cb73dde352e`, `bdd7fc4e2794227997b181693b203b157304ba02`, `23d28ddee804e9c20db4136f06aab879685d1942`.
- Exact executable CI `35514416069` passed both jobs.
- Stable persisted head `4ee24691f46721ffe8112bb435f278e5dd810721` passed exact-head CI `35514613656`.
- Focused CodeRabbit follow-up `5750230877` reported no unresolved material defect in the signed health-score-cap seam.

Only the same versioned explicit verified B20 root-cause evidence can contribute a B23 cap. Conflicted/unverified/cross-scan evidence fails closed. A root-cause cap cannot raise or replace a stricter existing access/sample/incomplete ceiling. Durable customer-visible adjusted-score persistence/read/card/export remains open after Stage-1 accepted-main reconciliation.

Detailed checkpoint: `docs/superpowers/plans/2026-09-20-stage3-b23-signed-score-caps.md`.

### B24 signed handoff-v2 source — GREEN; review open

A real shared B24 source seam now exists inside canonical Review before completion HMAC signing. It does **not** create/copy a V7 route or persist customer data.

- **RED:** `37b73a98e6b54db9c86f0de9eb921ff178a0201a`, FixList CI `35515644839`; Python scanner-api tests failed because `stage3_handoff_v2_source` did not exist, while lint/typecheck/contracts/frontend remained green.
- **Implementation:** `5eb4b6751019e98f87afc3b329880fbd33e0fdd6`.
- That first implementation preserved missing canonical `indexable_affected` as unknown. CI `35516002420` exposed that the regression had wrongly expected indexable count to be inferred from page shape.
- **Corrected GREEN executable head:** `790ebdc7ddec86a5a4bbfe4dfa0cb3ee23e0a353`; exact FixList CI `35516240329` passed both jobs.

The B24 source now requires exact trusted producer `scan_id == scan_run_id`; accepts root-cause identity only from B20 verified groups bound to that exact scan; carries verified family identity, B19 priority factors, B21 observation/population counts, explicitly evidenced canonical indexable count, evidence refs, verification/dependency/vendor fields and the real scanner user agent through the reviewed handoff-v2 serializer; excludes operator/debug suppressed findings with `operator_authorized=False`; and is HMAC-authenticated as part of the signed Review.

Missing count evidence remains unknown; it is not coerced to zero or inferred. If one legacy canonical action would require multiple different verified root-cause IDs in B24's singular field, the whole B24 source fails closed rather than guessing.

Detailed checkpoint: `docs/superpowers/plans/2026-09-20-stage3-b24-signed-handoff-source.md`.

Fresh independent review of this shared B24 source seam is still required. Durable V7 persistence/read/customer/operator/card/export consumption and historical-v1 compatibility proof remain release-gated behind Stage-1 reconciliation.

### B19–B24 requirement state

- **B19 partial:** signed Review factors/explanations green; durable FixItem/card/export consumption open.
- **B20 partial:** signed Review P1-corrected and independently review-clean; durable customer projection open.
- **B21 partial:** signed rank/count/truncation authority seam P1-corrected, independently review-clean and CI green; durable persisted customer/card/export proof open.
- **B22 partial:** authenticated private-preview/whitelist helper exists; actual entitlement/customer seam and no-leak proof unwired.
- **B23 partial:** signed Review cap decision independently review-clean; durable customer-visible adjusted-score consumption open.
- **B24 partial:** signed handoff-v2 source is RED->GREEN proven; independent review and real V7 persistence/read/customer/operator/export proof open.

Stage 3 remains **in progress**.

Node note: do not represent hosted CI as exact Node 20.19.5 evidence unless that exact runtime is independently proven.

## Stage 4

Reuse only existing isolated source `agent/stage4-b25-b28-compat-release-20260919` @ `d2ce905ff67410586f86e38bafd93ce4e998e4d1`, CI `35464436789`, after shared Stage-3 acceptance.

- **B25 incomplete:** real provenance-labelled 30-site baseline/candidate gate remains `not_assessed`; synthetic/historical evidence is not a pass.
- **B26 partial:** isolated own-site serving-defect work exists; shared acceptance not run.
- **B27 partial:** isolated GEO/historical HMAC/reader/tamper/privacy compatibility exists; shared acceptance not run.
- **B28 incomplete:** exact-source deployment/live acceptance, live identities, rollback proof and real customer submit -> persistence -> exact reload/history -> linked rescan remain outstanding.

## Exact next action

Request focused independent review of the exact shared B24 source seam. Any material finding must be reproduced first, corrected minimally and followed by fresh exact-head FixList CI.

Durable B19/B21/B23/B24 persistence/card/export and B22 private-preview routing remain release-gated until Stage-1 acceptance permits reconciliation onto V7 main. After that gate closes: reconcile onto accepted `main`, preserve V7/#308, run fresh integrated-head CI, then wire the already-authenticated Stage-3 source into the real V7 persistence/read/customer/card/export/preview path with RED -> GREEN regressions and independent review.

Do not move production or begin Stage-4 release execution before those gates are actually satisfied.
